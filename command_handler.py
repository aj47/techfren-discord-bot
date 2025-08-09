import discord
import database
from logging_config import logger
from rate_limiter import check_rate_limit
from llm_handler import call_llm_api
from message_utils import split_long_message, get_message_context
from response_manager import ResponseManager
import re
from typing import Optional

async def handle_bot_command(message: discord.Message, client_user: discord.ClientUser, bot_client: discord.Client = None) -> None:
    """Handles the mention command with thread-based replies."""
    bot_mention = f'<@{client_user.id}>'
    bot_mention_alt = f'<@!{client_user.id}>'
    
    # Check for @tbot alias
    content = message.content
    if '@tbot' in content.lower():
        content = content.replace('@tbot', bot_mention, 1)
    
    query = content.replace(bot_mention, '', 1).replace(bot_mention_alt, '', 1).strip()

    # Handle help command
    if query in ['--help', '-h', 'help']:
        help_text = """**TechFren Bot Help**

**Commands:**
• `@techfren-bot <question>` or `@tbot <question>` - Ask me anything! I can help with:
  - Technical questions and programming help
  - Code reviews and debugging
  - Explaining concepts and documentation
  - General conversation and assistance

• `/sum-day` - Generate a summary of today's messages in this channel
• `/sum-hr <hours>` - Generate a summary of messages from the past N hours (1-168 max)

**Features:**
• I automatically process shared links and can answer questions about them
• Reference messages by replying to them or including Discord message links
• I work in threads to keep conversations organized

**Tips:**
• Use `@tbot` as a shorter alias for `@techfren-bot`
• Add `--help` after mentioning me to see this message again
• Ask specific questions for better responses"""
        
        await ResponseManager.create_thread_response(
            message=message,
            content=help_text,
            thread_name=f"Bot Help - {message.author.display_name}",
            client_user=client_user
        )
        return

    if not query:
        import config
        error_msg = config.ERROR_MESSAGES['no_query']
        await ResponseManager.create_thread_response(
            message=message,
            content=error_msg,
            thread_name=f"Bot Response - {message.author.display_name}",
            client_user=client_user
        )
        return

    logger.info(f"Executing mention command - Requested by {message.author}")

    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        import config
        if reason == "cooldown":
            error_msg = config.ERROR_MESSAGES['rate_limit_cooldown'].format(wait_time=wait_time)
        else:
            error_msg = config.ERROR_MESSAGES['rate_limit_exceeded'].format(wait_time=wait_time)
        await ResponseManager.create_thread_response(
            message=message,
            content=error_msg,
            thread_name=f"Bot Response - {message.author.display_name}",
            client_user=client_user
        )
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return

    # Create thread from the user's message for the bot response
    thread_name = f"Bot Response - {message.author.display_name}"

    try:
        # Send processing message
        processing_msg = await ResponseManager.send_processing_message(
            message=message,
            create_thread=True,
            thread_name=thread_name
        )

        try:
            # Get message context (referenced messages and linked messages)
            message_context = None
            if bot_client and (message.reference or 'discord.com/channels/' in message.content):
                try:
                    message_context = await get_message_context(message, bot_client)
                    logger.debug(f"Retrieved message context: referenced={message_context['referenced_message'] is not None}, linked_count={len(message_context['linked_messages'])}")
                except Exception as e:
                    logger.warning(f"Failed to get message context: {e}")

            response = await call_llm_api(query, message_context)
            message_parts = await split_long_message(response)

            # Send all response parts using the response manager
            sent_messages = await ResponseManager.send_response_parts(
                message=message,
                content_parts=message_parts,
                client_user=client_user,
                create_thread=True,
                thread_name=thread_name
            )

            # Delete processing message
            if processing_msg:
                await processing_msg.delete()

            logger.info(f"Command executed successfully: mention - Response length: {len(response)} - Split into {len(message_parts)} parts - Posted in thread")
        
        except Exception as e:
            logger.error(f"Error processing mention command: {str(e)}", exc_info=True)
            import config
            error_msg = config.ERROR_MESSAGES['processing_error']
            
            # Send error message using response manager
            await ResponseManager.send_response(
                message=message,
                content=error_msg,
                client_user=client_user,
                create_thread=True,
                thread_name=thread_name
            )
            
            try:
                if processing_msg:
                    await processing_msg.delete()
            except discord.NotFound:
                pass

    except Exception as e:
        logger.error(f"Error in thread-based bot command handling: {str(e)}", exc_info=True)
        # Fallback to original behavior
        await _handle_bot_command_fallback(message, client_user, query, bot_client)


async def _handle_bot_command_fallback(message: discord.Message, client_user: discord.ClientUser, query: str, bot_client: discord.Client = None) -> None:
    """Fallback handler for bot commands when thread creation fails."""
    processing_msg = await message.channel.send("Processing your request, please wait...")
    try:
        # Get message context (referenced messages and linked messages)
        message_context = None
        if bot_client and (message.reference or 'discord.com/channels/' in message.content):
            try:
                message_context = await get_message_context(message, bot_client)
                logger.debug(f"Retrieved message context in fallback: referenced={message_context['referenced_message'] is not None}, linked_count={len(message_context['linked_messages'])}")
            except Exception as e:
                logger.warning(f"Failed to get message context in fallback: {e}")

        response = await call_llm_api(query, message_context)
        message_parts = await split_long_message(response)

        # Send response parts using response manager (without thread creation)
        await ResponseManager.send_response_parts(
            message=message,
            content_parts=message_parts,
            client_user=client_user,
            create_thread=False
        )

        await processing_msg.delete()
        logger.info(f"Command executed successfully (fallback): mention - Response length: {len(response)} - Split into {len(message_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing mention command (fallback): {str(e)}", exc_info=True)
        import config
        error_msg = config.ERROR_MESSAGES['processing_error']
        
        # Send error using response manager
        await ResponseManager.send_response(
            message=message,
            content=error_msg,
            client_user=client_user,
            create_thread=False
        )
        
        try:
            await processing_msg.delete()
        except discord.NotFound:
            pass


# Helper functions for parameter validation
def _parse_and_validate_hours(content: str) -> Optional[int]:
    """Parse hours parameter from message content."""
    match = re.match(r'/sum-hr\s+(\d+)', content.strip())
    if not match:
        return None

    hours = int(match.group(1))
    return hours if hours > 0 else None

def _validate_hours_range(hours: int) -> bool:
    """Validate that hours is within acceptable range."""
    import config
    return 1 <= hours <= config.MAX_SUMMARY_HOURS  # Max 7 days

# Helper function for error responses
async def _send_error_response(message: discord.Message, client_user: discord.ClientUser, error_msg: str) -> None:
    """Send error response and store in database."""
    await ResponseManager.send_response(
        message=message,
        content=error_msg,
        client_user=client_user,
        create_thread=False
    )

# Helper function for message command handling
async def _handle_message_command_wrapper(message: discord.Message, client_user: discord.ClientUser, command_name: str, hours: int = 24) -> None:
    """Unified wrapper for message command handling with error management."""
    try:
        from command_abstraction import (
            create_context_from_message,
            create_response_sender,
            create_thread_manager,
            handle_summary_command
        )

        context = create_context_from_message(message)
        response_sender = create_response_sender(message)
        thread_manager = create_thread_manager(message)

        await handle_summary_command(context, response_sender, thread_manager, hours=hours, bot_user=client_user)

    except Exception as e:
        logger.error(f"Error in handle_{command_name}_command: {str(e)}", exc_info=True)
        import config
        error_msg = config.ERROR_MESSAGES['summary_error']
        await _send_error_response(message, client_user, error_msg)

async def handle_sum_day_command(message: discord.Message, client_user: discord.ClientUser) -> None:
    """Handles the /sum-day command using the abstraction layer."""
    await _handle_message_command_wrapper(message, client_user, "sum_day", hours=24)

async def handle_sum_hr_command(message: discord.Message, client_user: discord.ClientUser) -> None:
    """Handles the /sum-hr <num_hours> command using the abstraction layer."""
    # Parse and validate hours parameter
    import config
    hours = _parse_and_validate_hours(message.content)
    if hours is None:
        await _send_error_response(
            message, client_user,
            config.ERROR_MESSAGES['invalid_hours_format']
        )
        return

    if not _validate_hours_range(hours):
        await _send_error_response(
            message, client_user,
            config.ERROR_MESSAGES['invalid_hours_range']
        )
        return

    # Warn for large summaries that may take longer
    if hours > config.LARGE_SUMMARY_THRESHOLD:
        warning_msg = config.ERROR_MESSAGES['large_summary_warning'].format(hours=hours)
        await message.channel.send(warning_msg)

    await _handle_message_command_wrapper(message, client_user, "sum_hr", hours=hours)

async def store_bot_response_db(bot_msg_obj: discord.Message, client_user: discord.ClientUser, guild: Optional[discord.Guild], channel: discord.abc.Messageable, content_to_store: str) -> None:
    """Helper function to store bot's own messages in the database."""
    from database_helpers import DatabaseHelpers
    
    success = await DatabaseHelpers.store_bot_response_safely(
        bot_message=bot_msg_obj,
        client_user=client_user,
        guild=guild,
        channel=channel,
        content=content_to_store
    )
    
    if not success:
        logger.warning(f"Failed to store bot response {bot_msg_obj.id} in database")




