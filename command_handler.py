"""
Command handlers for bot commands including mention, sum-day, sum-hr, chart-day, and chart-hr.
"""

import re
import asyncio
from typing import Optional

import discord

import database
from logging_config import logger
from rate_limiter import check_rate_limit
from llm_handler import call_llm_api
from message_utils import split_long_message, get_message_context
from thread_memory import get_thread_context, store_thread_exchange, has_thread_memory


async def _validate_bot_command_input(message, client_user):
    """Validate input for bot command and return cleaned query."""
    bot_mention = f"<@{client_user.id}>"
    bot_mention_alt = f"<@!{client_user.id}>"
    query = (
        message.content.replace(bot_mention, "", 1)
        .replace(bot_mention_alt, "", 1)
        .strip()
    )

    if not query:
        import config

        error_msg = config.ERROR_MESSAGES["no_query"]
        await _send_error_response_thread(message, client_user, error_msg)
        return None

    return query


async def _check_bot_command_rate_limit(message, client_user):
    """Check rate limits for bot command."""
    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        import config

        if reason == "cooldown":
            error_msg = config.ERROR_MESSAGES["rate_limit_cooldown"].format(
                wait_time=wait_time
            )
        else:
            error_msg = config.ERROR_MESSAGES["rate_limit_exceeded"].format(
                wait_time=wait_time
            )

        await _send_error_response_thread(message, client_user, error_msg)
        logger.info(
            "Rate limited user %s (%s): wait time %.1fs",
            message.author,
            reason,
            wait_time
        )
        return False
    return True


async def _get_bot_command_context(message, bot_client):
    """Get thread and message context for bot command."""
    thread_context = ""
    thread_id = None
    message_context = None

    # Check if we're in a thread and get thread memory
    if hasattr(message.channel, "parent") and message.channel.parent is not None:
        thread_id = str(message.channel.id)
        if has_thread_memory(thread_id):
            thread_context = get_thread_context(thread_id, max_exchanges=4)
            logger.debug("Retrieved thread context for thread %s", thread_id)

    # Log attachment info for debugging
    if message.attachments:
        logger.info("Message has %d attachment(s): %s", len(message.attachments), [att.filename for att in message.attachments])

    # Get message context (referenced messages, linked messages, and current message)
    if bot_client and (message.reference or "discord.com/channels/" in message.content or message.attachments):
        try:
            message_context = await get_message_context(message, bot_client)
            logger.debug(
                "Retrieved message context: referenced=%s, linked_count=%d",
                message_context['referenced_message'] is not None,
                len(message_context['linked_messages'])
            )
        except Exception as e:
            logger.warning("Failed to get message context: %s", e)
    elif message.attachments:
        message_context = {
            "current_message": message,
            "referenced_message": None,
            "linked_messages": [],
        }
        logger.info("Created message context for current message with %d attachment(s)", len(message.attachments))

    return thread_context, thread_id, message_context


async def _combine_contexts(thread_context, message_context):
    """Combine thread and message contexts."""
    if thread_context and message_context:
        if "thread_context" not in message_context:
            message_context["thread_context"] = thread_context
    elif thread_context:
        message_context = {"thread_context": thread_context}
    return message_context


async def _store_thread_memory(
    message, thread_id, query, response, force_charts, chart_data
):
    """Store thread memory if in a thread."""
    if thread_id:
        try:
            store_thread_exchange(
                thread_id=thread_id,
                user_id=str(message.author.id),
                user_name=str(message.author),
                user_message=query,
                bot_response=response,
                guild_id=str(message.guild.id) if message.guild else None,
                channel_id=(
                    str(message.channel.parent.id)
                    if hasattr(message.channel, "parent") and message.channel.parent
                    else None
                ),
                is_chart_analysis=force_charts or bool(chart_data),
            )
            logger.debug("Stored thread exchange for thread %s", thread_id)
        except Exception as e:
            logger.warning("Failed to store thread exchange: %s", e)


async def _send_message_parts(thread_sender, parts, chart_data):
    """Send message parts with optional charts."""
    if chart_data and parts:
        await thread_sender.send_with_charts(parts[0], chart_data)
        if len(parts) > 1:
            await thread_sender.send_in_parts(parts[1:])
    else:
        await thread_sender.send_in_parts(parts)


async def _cleanup_processing_message(processing_msg):
    """Delete processing message if it exists."""
    if processing_msg:
        try:
            await processing_msg.delete()
        except Exception as e:
            logger.debug("Could not delete processing message: %s", e)


async def _handle_send_error(processing_msg):
    """Handle error when sending bot response."""
    if processing_msg:
        try:
            await processing_msg.edit(
                content="Sorry, there was an error processing your request."
            )
        except Exception as edit_e:
            logger.debug("Could not edit processing message: %s", edit_e)


async def _send_bot_response(thread_sender, response, chart_data, processing_msg):
    """Send bot response with charts if available."""
    try:
        parts = await split_long_message(response)
        await _send_message_parts(thread_sender, parts, chart_data)
        await _cleanup_processing_message(processing_msg)
    except Exception as e:
        logger.error("Error sending bot response: %s", e)
        await _handle_send_error(processing_msg)


async def _process_bot_command_in_thread(
    thread_sender, processing_msg, message, query, bot_client, thread_id
):
    """Process bot command within a thread."""
    try:
        # Check if this is a chart analysis request
        force_charts = _should_force_charts(query)

        # Get all context information
        thread_context, thread_id, message_context = await _get_bot_command_context(
            message, bot_client
        )

        # Combine contexts
        message_context = await _combine_contexts(thread_context, message_context)

        # Get LLM response
        response, chart_data = await call_llm_api(query, message_context, force_charts)
        logger.debug("Raw response length: %d characters", len(response))

        # Store thread memory
        await _store_thread_memory(
            message, thread_id, query, response, force_charts, chart_data
        )

        # Send response
        await _send_bot_response(thread_sender, response, chart_data, processing_msg)

        logger.info(
            "Command executed successfully: mention - Response length: %d - "
            "Posted in thread",
            len(response)
        )
    except Exception as e:
        logger.error("Error processing mention command: %s", str(e), exc_info=True)
        import config

        error_msg = config.ERROR_MESSAGES["processing_error"]
        await thread_sender.send(error_msg)
        try:
            if processing_msg:
                await processing_msg.delete()
        except discord.NotFound:
            pass


# Track processed commands to prevent duplicate handling at command level
_processed_commands = set()
_PROCESSED_COMMANDS_MAX_SIZE = 500
_command_lock = asyncio.Lock()  # Prevent race conditions

async def handle_bot_command(
    message: discord.Message,
    client_user: discord.ClientUser,
    bot_client: discord.Client = None,
) -> None:
    """Handles the mention command with thread-based replies."""
    # Check for duplicate command processing with async lock to prevent race conditions
    async with _command_lock:
        command_key = (message.id, message.author.id)
        if command_key in _processed_commands:
            logger.warning("⚠️ DUPLICATE COMMAND: Already processing/processed message %s, skipping", message.id)
            return

        # Add to processed commands
        _processed_commands.add(command_key)
        if len(_processed_commands) > _PROCESSED_COMMANDS_MAX_SIZE:
            to_remove = list(_processed_commands)[:_PROCESSED_COMMANDS_MAX_SIZE // 2]
            for key in to_remove:
                _processed_commands.discard(key)

    # Validate input and check rate limits
    query = await _validate_bot_command_input(message, client_user)
    if not query:
        return

    logger.info("🟢 Executing mention command - Requested by %s - Message ID: %s", message.author, message.id)

    if not await _check_bot_command_rate_limit(message, client_user):
        return

    try:
        from command_abstraction import ThreadManager, MessageResponseSender

        # Check if message is already in a thread (Discord auto-created from media)
        if isinstance(message.channel, discord.Thread):
            logger.info("✅ PATH 1: Message is already in thread '%s', using it for response", message.channel.name)
            thread = message.channel
            thread_sender = MessageResponseSender(thread)
            processing_msg = await thread_sender.send(
                "Processing your request, please wait..."
            )
            await _process_bot_command_in_thread(
                thread_sender, processing_msg, message, query, bot_client, thread.id
            )
            return

        # Log to debug which path we're taking
        logger.debug("Message channel type: %s, has %d attachment(s)", type(message.channel).__name__, len(message.attachments))

        # If message has attachments, try to use Discord's auto-created thread first
        if message.attachments:
            import asyncio
            logger.info("Message has %d attachment(s), checking for Discord auto-thread", len(message.attachments))

            # Wait for Discord's auto-created thread with exponential backoff
            attempt = 0
            wait_time = 0.2  # Start with 200ms
            max_wait = 2.0   # Cap at 2 seconds between attempts
            total_waited = 0
            max_total_wait = 5  # Wait up to 5 seconds for Discord auto-thread

            while total_waited < max_total_wait:
                attempt += 1
                await asyncio.sleep(wait_time)
                total_waited += wait_time

                try:
                    existing_thread = await message.fetch_thread()
                    if existing_thread:
                        logger.info(
                            "✅ PATH 2A: Found Discord auto-thread '%s' after %.1fs "
                            "(attempt %d)",
                            existing_thread.name,
                            total_waited,
                            attempt
                        )
                        thread_sender = MessageResponseSender(existing_thread)
                        processing_msg = await thread_sender.send(
                            "Processing your request, please wait..."
                        )
                        await _process_bot_command_in_thread(
                            thread_sender, processing_msg, message, query, bot_client, existing_thread.id
                        )
                        logger.debug("PATH 2A completed successfully, returning from handle_bot_command")
                        return
                except discord.NotFound:
                    logger.debug(
                        "Discord thread not found yet after %.1fs (attempt %d), "
                        "waiting %.1fs...",
                        total_waited,
                        attempt,
                        wait_time
                    )
                    # Exponential backoff: increase wait time for next attempt
                    wait_time = min(wait_time * 1.5, max_wait)
                    continue
                except Exception as e:
                    logger.warning("Error checking for auto-created thread: %s", e)
                    break

            # If no Discord auto-thread found, create our own bot thread
            logger.info("No Discord auto-thread found after %.1fs, creating bot thread for attachment message", total_waited)

        # Create bot thread (for messages with or without attachments)
        logger.info("Creating bot thread")
        thread_name = f"Bot Response - {message.author.display_name}"
        thread_manager = ThreadManager(message.channel, message.guild)
        thread = await thread_manager.create_thread_from_message(message, thread_name)

        if thread:
            # Process command in thread
            logger.info("✅ PATH 2B: Created bot thread '%s'", thread.name)
            thread_sender = MessageResponseSender(thread)
            processing_msg = await thread_sender.send(
                "Processing your request, please wait..."
            )
            await _process_bot_command_in_thread(
                thread_sender, processing_msg, message, query, bot_client, thread.id
            )
            logger.debug("PATH 2B completed successfully, returning from handle_bot_command")
            return

        # Fallback to channel response
        if isinstance(message.channel, discord.DMChannel):
            logger.debug(
                "Thread creation not supported in DMs, using channel response"
            )
        else:
            logger.error(
                "Thread creation FAILED - No fallback available: %s", type(message.channel).__name__
            )
            error_msg = await message.channel.send(
                f"❌ **Thread Creation Failed**: Unable to create thread in {type(message.channel).__name__}\n\n"
                "This command requires thread support. Please check server permissions and try again."
            )
    except Exception as e:
        logger.error("Error in handle_bot_command: %s", str(e), exc_info=True)
        # No fallback - just log the error


async def _send_error_response_thread(
    message: discord.Message, client_user: discord.ClientUser, error_msg: str
) -> None:
    """Send error response in a thread attached to the user's message."""
    try:
        from command_abstraction import ThreadManager, MessageResponseSender

        thread_manager = ThreadManager(message.channel, message.guild)
        thread_name = f"Bot Response - {message.author.display_name}"

        # Try to create thread from the user's message
        thread = await thread_manager.create_thread_from_message(message, thread_name)

        if thread:
            thread_sender = MessageResponseSender(thread)
            bot_response = await thread_sender.send(error_msg)
            if bot_response:
                await store_bot_response_db(
                    bot_response, client_user, message.guild, thread, error_msg
                )
        else:
            # Fallback to channel response (expected for DMs and unsupported channel
            # types)
            allowed_mentions = discord.AllowedMentions(
                everyone=False, roles=False, users=True
            )
            bot_response = await message.channel.send(
                error_msg, allowed_mentions=allowed_mentions, suppress_embeds=True
            )
            await store_bot_response_db(
                bot_response, client_user, message.guild, message.channel, error_msg
            )
    except Exception as e:
        logger.error("Error sending error response in thread: %s", str(e), exc_info=True)
        # Ultimate fallback to channel response
        allowed_mentions = discord.AllowedMentions(
            everyone=False, roles=False, users=True
        )
        bot_response = await message.channel.send(
            error_msg, allowed_mentions=allowed_mentions, suppress_embeds=True
        )
        await store_bot_response_db(
            bot_response, client_user, message.guild, message.channel, error_msg
        )


# REMOVED: All fallback handler functions - No fallbacks available
# _get_fallback_message_context - REMOVED
# _send_fallback_response_with_charts - REMOVED
# _send_fallback_response_text - REMOVED
# _handle_fallback_error - REMOVED
# The system now fails explicitly instead of falling back to channel responses.


# Helper functions for parameter validation


# REMOVED: _handle_bot_command_fallback - No fallbacks available
# The system now fails explicitly when thread creation fails instead of falling back.


# Helper functions for parameter validation
def _parse_and_validate_hours(content: str) -> Optional[int]:
    """Parse hours parameter from message content."""
    # Support both regular and chart commands
    patterns = [r"/sum-hr\s+(\d+)", r"/chart-hr\s+(\d+)", r"/sum-hr-chart\s+(\d+)"]

    for pattern in patterns:
        match = re.match(pattern, content.strip())
        if match:
            hours = int(match.group(1))
            return hours if hours > 0 else None

    return None


def _validate_hours_range(hours: int) -> bool:
    """Validate that hours is within acceptable range."""
    import config

    return 1 <= hours <= config.MAX_SUMMARY_HOURS  # Max 7 days


# Helper function for error responses
async def _send_error_response(
    message: discord.Message, client_user: discord.ClientUser, error_msg: str
) -> None:
    """Send error response and store in database."""
    allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
    bot_response = await message.channel.send(
        error_msg, allowed_mentions=allowed_mentions, suppress_embeds=True
    )
    await store_bot_response_db(
        bot_response, client_user, message.guild, message.channel, error_msg
    )


# Helper function for message command handling
async def _handle_message_command_wrapper(
    message: discord.Message,
    client_user: discord.ClientUser,
    command_name: str,
    hours: int = 24,
    force_charts: bool = False,
) -> None:
    """Unified wrapper for message command handling with error management."""
    try:
        from command_abstraction import (
            create_context_from_message,
            create_response_sender,
            create_thread_manager,
            handle_summary_command,
        )

        context = create_context_from_message(message)
        response_sender = create_response_sender(message)
        thread_manager = create_thread_manager(message)

        await handle_summary_command(
            context,
            response_sender,
            thread_manager,
            hours=hours,
            bot_user=client_user,
            force_charts=force_charts,
        )

    except Exception as e:
        logger.error("Error in handle_%s_command: %s", command_name, str(e), exc_info=True)
        import config

        error_msg = config.ERROR_MESSAGES["summary_error"]
        await _send_error_response(message, client_user, error_msg)


async def handle_sum_day_command(
    message: discord.Message, client_user: discord.ClientUser
) -> None:
    """Handles the /sum-day command using the abstraction layer."""
    force_charts = "/sum-day-chart" in message.content or "/chart" in message.content
    await _handle_message_command_wrapper(
        message, client_user, "sum_day", hours=24, force_charts=force_charts
    )


async def handle_sum_hr_command(
    message: discord.Message, client_user: discord.ClientUser
) -> None:
    """Handles the /sum-hr <num_hours> command using the abstraction layer."""
    # Parse and validate hours parameter
    import config

    hours = _parse_and_validate_hours(message.content)
    if hours is None:
        await _send_error_response(
            message, client_user, config.ERROR_MESSAGES["invalid_hours_format"]
        )
        return

    if not _validate_hours_range(hours):
        await _send_error_response(
            message, client_user, config.ERROR_MESSAGES["invalid_hours_range"]
        )
        return

    # Warn for large summaries that may take longer
    if hours > config.LARGE_SUMMARY_THRESHOLD:
        warning_msg = config.ERROR_MESSAGES["large_summary_warning"].format(hours=hours)
        await message.channel.send(warning_msg)

    # Check if this is a chart analysis request
    force_charts = "/sum-hr-chart" in message.content or "/chart" in message.content
    await _handle_message_command_wrapper(
        message, client_user, "sum_hr", hours=hours, force_charts=force_charts
    )


async def handle_chart_day_command(
    message: discord.Message, client_user: discord.ClientUser
) -> None:
    """Handles the /chart-day command for chart-focused daily analysis."""
    await _handle_message_command_wrapper(
        message, client_user, "chart_day", hours=24, force_charts=True
    )


async def handle_chart_hr_command(
    message: discord.Message, client_user: discord.ClientUser
) -> None:
    """Handles the /chart-hr <num_hours> command for chart-focused hourly analysis."""
    # Parse and validate hours parameter
    import config

    hours = _parse_and_validate_hours(message.content.replace("/chart-hr", "/sum-hr"))
    if hours is None:
        await _send_error_response(
            message, client_user, config.ERROR_MESSAGES["invalid_hours_format"]
        )
        return

    if not _validate_hours_range(hours):
        await _send_error_response(
            message, client_user, config.ERROR_MESSAGES["invalid_hours_range"]
        )
        return

    # Warn for large summaries that may take longer
    if hours > config.LARGE_SUMMARY_THRESHOLD:
        warning_msg = config.ERROR_MESSAGES["large_summary_warning"].format(hours=hours)
        await message.channel.send(warning_msg)

    await _handle_message_command_wrapper(
        message, client_user, "chart_hr", hours=hours, force_charts=True
    )


async def store_bot_response_db(
    bot_msg_obj: discord.Message,
    client_user: discord.ClientUser,
    guild: Optional[discord.Guild],
    channel: discord.abc.Messageable,
    content_to_store: str,
) -> None:
    """Helper function to store bot's own messages in the database."""
    try:
        guild_id_str = str(guild.id) if guild else None
        guild_name_str = guild.name if guild else None
        channel_id_str = str(channel.id)
        # Handle DM channel name
        channel_name_str = (
            channel.name if hasattr(channel, "name") else f"DM with {channel.recipient}"
        )

        success = await database.store_message(
            message_id=str(bot_msg_obj.id),
            author_id=str(client_user.id),
            author_name=str(client_user),
            channel_id=channel_id_str,
            channel_name=channel_name_str,
            content=content_to_store,
            created_at=bot_msg_obj.created_at,
            guild_id=guild_id_str,
            guild_name=guild_name_str,
            is_bot=True,
            is_command=False,  # Bot responses are not commands themselves
            command_type=None,
        )
        if not success:
            logger.warning("Failed to store bot response %s in database", bot_msg_obj.id)
    except Exception as e:
        logger.error("Error storing bot response in database: %s", str(e), exc_info=True)


def _should_force_charts(query: str) -> bool:
    """
    Determine if the query should force chart analysis mode.

    Args:
        query: User's query text

    Returns:
        bool: True if chart analysis should be forced
    """
    # Explicit chart command patterns
    chart_commands = [
        "/chart",
        "/analyze",
        "/data",
        "/stats",
        "/metrics",
        "chart analysis",
        "data analysis",
        "show charts",
        "visualize data",
    ]

    # Strong chart request indicators
    chart_indicators = [
        "create a chart",
        "show me data",
        "breakdown of",
        "activity analysis",
        "user statistics",
        "time analysis",
        "usage patterns",
        "frequency analysis",
        "top users",
        "most active",
        "activity by time",
        "distribution of",
    ]

    query_lower = query.lower().strip()

    # Check for explicit commands
    for command in chart_commands:
        if query_lower.startswith(command) or command in query_lower:
            return True

    # Check for strong indicators
    for indicator in chart_indicators:
        if indicator in query_lower:
            return True

    # Check for quantitative question patterns
    quantitative_patterns = [
        "how many",
        "how much",
        "what percentage",
        "count of",
        "number of",
        "total",
        "average",
        "compare",
    ]

    for pattern in quantitative_patterns:
        if pattern in query_lower:
            return True

    return False
