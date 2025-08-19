import discord
import database
from logging_config import logger
from rate_limiter import check_rate_limit
from llm_handler import call_llm_api
from message_utils import split_long_message, get_message_context
from mermaid_handler import process_mermaid_in_response
import re
from typing import Optional

async def handle_bot_command(message: discord.Message, client_user: discord.ClientUser, bot_client: discord.Client = None) -> None:
    """Handles the mention command with thread-based replies."""
    bot_mention = f'<@{client_user.id}>'
    bot_mention_alt = f'<@!{client_user.id}>'
    query = message.content.replace(bot_mention, '', 1).replace(bot_mention_alt, '', 1).strip()

    if not query:
        import config
        error_msg = config.ERROR_MESSAGES['no_query']
        await _send_error_response_thread(message, client_user, error_msg)
        return

    logger.info(f"Executing mention command - Requested by {message.author}")

    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        import config
        if reason == "cooldown":
            error_msg = config.ERROR_MESSAGES['rate_limit_cooldown'].format(wait_time=wait_time)
        else:
            error_msg = config.ERROR_MESSAGES['rate_limit_exceeded'].format(wait_time=wait_time)
        await _send_error_response_thread(message, client_user, error_msg)
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return

    # Create thread from the user's message for the bot response
    thread_name = f"Bot Response - {message.author.display_name}"

    try:
        from command_abstraction import ThreadManager, MessageResponseSender
        thread_manager = ThreadManager(message.channel, message.guild)

        # Create thread from the user's original message
        thread = await thread_manager.create_thread_from_message(message, thread_name)

        if thread:
            # Send processing message in the thread
            thread_sender = MessageResponseSender(thread)
            processing_msg = await thread_sender.send("Processing your request, please wait...")

            try:
                # Get message context (referenced messages and linked messages)
                message_context = None
                if bot_client and (message.reference or 'discord.com/channels/' in message.content):
                    try:
                        message_context = await get_message_context(message, bot_client)
                        logger.debug(f"Retrieved message context: referenced={message_context['referenced_message'] is not None}, linked_count={len(message_context['linked_messages'])}")
                    except Exception as e:
                        logger.warning(f"Failed to get message context: {e}")

                # Add Discord server context for better responses
                discord_context = {
                    'channel_id': str(message.channel.id),
                    'channel_name': message.channel.name if hasattr(message.channel, 'name') else 'DM',
                    'guild_id': str(message.guild.id) if message.guild else None,
                    'guild_name': message.guild.name if message.guild else None,
                    'author_id': str(message.author.id),
                    'author_name': message.author.display_name,
                    'query_type': query.lower()
                }
                
                # Always fetch Discord server context for better responses in guild channels
                query_lower = query.lower()
                server_context_keywords = ['summary', 'summarize', 'users', 'members', 'activity', 'messages', 'message', 'channel', 'server', 'guild', 'who', 'what happened', 'recent', 'chat', 'conversation', 'discussion', 'talked', 'said', 'posted', 'wrote', 'discord', 'here', 'this channel', 'channel content']
                needs_extensive_context = any(keyword in query_lower for keyword in server_context_keywords)
                
                # Debug log to track context requirements
                matched_keywords = [kw for kw in server_context_keywords if kw in query_lower]
                logger.info(f"Context check - Query: '{query}' | Extensive context: {needs_extensive_context} | Matched keywords: {matched_keywords}")
                
                # Always fetch recent messages for guild channels (smart context window sizing)
                recent_messages = []
                if message.guild:
                    try:
                        from datetime import datetime, timezone
                        current_time = datetime.now(timezone.utc)
                        
                        # Smart context window sizing
                        if needs_extensive_context:
                            context_hours = 24  # Full context for summary-related queries
                        else:
                            context_hours = 4   # Light context for general interactions
                        
                        # Get messages from the appropriate time window
                        recent_messages = database.get_channel_messages_for_hours(
                            str(message.channel.id), current_time, context_hours
                        )
                        logger.info(f"Fetched {len(recent_messages)} recent messages ({context_hours}h context) for channel #{message.channel.name}")
                        
                        # Also get active channels if asking about server-wide activity
                        if any(word in query_lower for word in ['server', 'guild', 'all channels', 'everywhere']):
                            active_channels = database.get_active_channels(24)
                            discord_context['active_channels'] = active_channels[:5]  # Limit to top 5
                            logger.info(f"Added {len(active_channels)} active channels to context")
                            
                    except Exception as e:
                        logger.warning(f"Failed to fetch server context: {e}")
                
                # Enhance message_context with Discord server context and recent messages
                if message_context is None:
                    message_context = {}
                message_context['discord_context'] = discord_context
                message_context['recent_messages'] = recent_messages

                response = await call_llm_api(query, message_context, bot_client)
                logger.debug(f"Raw response length: {len(response)} characters")
                logger.debug(f"Response ends with: ...{response[-100:] if len(response) > 100 else response}")
                
                # Process Mermaid diagrams in the response
                logger.info(f"Checking for Mermaid diagrams in response (length: {len(response)})")
                modified_response, mermaid_files = await process_mermaid_in_response(
                    response, str(message.author.id)
                )
                logger.info(f"Mermaid processing complete: {len(mermaid_files)} files generated")
                
                # If we have Mermaid diagrams, send text first, then diagrams at the end
                if mermaid_files:
                    logger.info(f"Detected {len(mermaid_files)} Mermaid diagram(s) in LLM response")
                    
                    # Split the modified response if needed (using 1900 to match summary commands)
                    if len(modified_response) > 1900:
                        logger.info(f"Splitting response of {len(modified_response)} chars into multiple parts")
                        message_parts = await split_long_message(modified_response, max_length=1900)
                    else:
                        message_parts = [modified_response]
                    
                    # Send all text parts first
                    for i, part in enumerate(message_parts, 1):
                        # Add continuation indicator if there are multiple parts
                        if len(message_parts) > 1 and i < len(message_parts):
                            part = part + "\n\n*(continued...)*"
                        bot_response = await thread_sender.send(part)
                        if bot_response:
                            await store_bot_response_db(bot_response, client_user, message.guild, thread, part)
                    
                    # Send each diagram separately for better visibility
                    logger.info(f"Sending {len(mermaid_files)} Mermaid diagram(s) as separate messages")
                    for idx, file in enumerate(mermaid_files):
                        if idx == 0:
                            diagram_message = "📊 **Flowchart Visualization:**"
                        else:
                            diagram_message = "📈 **Distribution Chart:**"
                        
                        bot_response = await thread.send(content=diagram_message, file=file)
                        if bot_response:
                            await store_bot_response_db(bot_response, client_user, message.guild, thread, diagram_message)
                else:
                    # No Mermaid diagrams, send response normally
                    # Force split if response is over 1900 chars to ensure it doesn't get cut off (matches summary commands)
                    if len(modified_response) > 1900:
                        logger.info(f"Splitting response of {len(modified_response)} chars into multiple parts")
                        message_parts = await split_long_message(modified_response, max_length=1900)
                    else:
                        message_parts = [modified_response]

                    # Send all response parts in the thread
                    for i, part in enumerate(message_parts, 1):
                        # Add continuation indicator if there are multiple parts
                        if len(message_parts) > 1 and i < len(message_parts):
                            part = part + "\n\n*(continued...)*"
                        bot_response = await thread_sender.send(part)
                        if bot_response:
                            await store_bot_response_db(bot_response, client_user, message.guild, thread, part)

                # Delete processing message
                if processing_msg:
                    await processing_msg.delete()

                logger.info(f"Command executed successfully: mention - Response length: {len(response)} - Split into {len(message_parts)} parts - Posted in thread")
            except Exception as e:
                logger.error(f"Error processing mention command: {str(e)}", exc_info=True)
                import config
                error_msg = config.ERROR_MESSAGES['processing_error']
                await thread_sender.send(error_msg)
                try:
                    if processing_msg:
                        await processing_msg.delete()
                except discord.NotFound:
                    pass
        else:
            # Fallback: if thread creation completely failed, send response in main channel
            logger.warning("Thread creation failed for bot command, falling back to channel response")
            await _handle_bot_command_fallback(message, client_user, query, bot_client)

    except Exception as e:
        logger.error(f"Error in thread-based bot command handling: {str(e)}", exc_info=True)
        # Fallback to original behavior
        await _handle_bot_command_fallback(message, client_user, query, bot_client)


async def _send_error_response_thread(message: discord.Message, client_user: discord.ClientUser, error_msg: str) -> None:
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
                await store_bot_response_db(bot_response, client_user, message.guild, thread, error_msg)
        else:
            # Fallback to channel response
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
            bot_response = await message.channel.send(error_msg, allowed_mentions=allowed_mentions, suppress_embeds=True)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
    except Exception as e:
        logger.error(f"Error sending error response in thread: {str(e)}", exc_info=True)
        # Ultimate fallback to channel response
        allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
        bot_response = await message.channel.send(error_msg, allowed_mentions=allowed_mentions, suppress_embeds=True)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)


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
        
        # Add Discord server context for better responses (fallback)
        discord_context = {
            'channel_id': str(message.channel.id),
            'channel_name': message.channel.name if hasattr(message.channel, 'name') else 'DM',
            'guild_id': str(message.guild.id) if message.guild else None,
            'guild_name': message.guild.name if message.guild else None,
            'author_id': str(message.author.id),
            'author_name': message.author.display_name,
            'query_type': query.lower()
        }
        
        # Always fetch Discord server context for better responses in guild channels (fallback)
        query_lower = query.lower()
        server_context_keywords = ['summary', 'summarize', 'users', 'members', 'activity', 'messages', 'message', 'channel', 'server', 'guild', 'who', 'what happened', 'recent', 'chat', 'conversation', 'discussion', 'talked', 'said', 'posted', 'wrote', 'discord', 'here', 'this channel', 'channel content']
        needs_extensive_context = any(keyword in query_lower for keyword in server_context_keywords)
        
        # Debug log to track context requirements (fallback)
        matched_keywords = [kw for kw in server_context_keywords if kw in query_lower]
        logger.info(f"Context check (fallback) - Query: '{query}' | Extensive context: {needs_extensive_context} | Matched keywords: {matched_keywords}")
        
        # Always fetch recent messages for guild channels (fallback path)
        recent_messages = []
        if message.guild:
            try:
                from datetime import datetime, timezone
                current_time = datetime.now(timezone.utc)
                
                # Smart context window sizing (fallback)
                if needs_extensive_context:
                    context_hours = 24  # Full context for summary-related queries
                else:
                    context_hours = 4   # Light context for general interactions
                
                # Get messages from the appropriate time window
                recent_messages = database.get_channel_messages_for_hours(
                    str(message.channel.id), current_time, context_hours
                )
                logger.info(f"Fetched {len(recent_messages)} recent messages ({context_hours}h context) for channel #{message.channel.name} (fallback)")
                
                # Also get active channels if asking about server-wide activity
                if any(word in query_lower for word in ['server', 'guild', 'all channels', 'everywhere']):
                    active_channels = database.get_active_channels(24)
                    discord_context['active_channels'] = active_channels[:5]  # Limit to top 5
                    logger.info(f"Added {len(active_channels)} active channels to context (fallback)")
                    
            except Exception as e:
                logger.warning(f"Failed to fetch server context in fallback: {e}")
        
        # Enhance message_context with Discord server context and recent messages (fallback)
        if message_context is None:
            message_context = {}
        message_context['discord_context'] = discord_context
        message_context['recent_messages'] = recent_messages

        response = await call_llm_api(query, message_context, bot_client)
        
        # Process Mermaid diagrams in the response
        modified_response, mermaid_files = await process_mermaid_in_response(
            response, str(message.author.id)
        )
        
        # If we have Mermaid diagrams, send text first, then diagrams at the end
        if mermaid_files:
            logger.info(f"Detected {len(mermaid_files)} Mermaid diagram(s) in LLM response (fallback)")
            
            # Split the modified response if needed
            if len(modified_response) > 1900:
                message_parts = await split_long_message(modified_response, max_length=1900)
            else:
                message_parts = [modified_response]
            
            # Send all text parts first
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
            for i, part in enumerate(message_parts, 1):
                # Add continuation indicator if there are multiple parts
                if len(message_parts) > 1 and i < len(message_parts):
                    part = part + "\n\n*(continued...)*"
                bot_response = await message.channel.send(part, allowed_mentions=allowed_mentions, suppress_embeds=True)
                if bot_response:
                    await store_bot_response_db(bot_response, client_user, message.guild, message.channel, part)
            
            # Send each diagram separately for better visibility
            logger.info(f"Sending {len(mermaid_files)} Mermaid diagram(s) as separate messages")
            for idx, file in enumerate(mermaid_files):
                if idx == 0:
                    diagram_message = "📊 **Flowchart Visualization:**"
                else:
                    diagram_message = "📈 **Distribution Chart:**"
                
                bot_response = await message.channel.send(
                    content=diagram_message,
                    file=file,
                    allowed_mentions=allowed_mentions,
                    suppress_embeds=True
                )
                if bot_response:
                    await store_bot_response_db(bot_response, client_user, message.guild, message.channel, diagram_message)
        else:
            # No Mermaid diagrams, send response normally
            if len(modified_response) > 1900:
                message_parts = await split_long_message(modified_response, max_length=1900)
            else:
                message_parts = [modified_response]

            for i, part in enumerate(message_parts, 1):
                # Add continuation indicator if there are multiple parts
                if len(message_parts) > 1 and i < len(message_parts):
                    part = part + "\n\n*(continued...)*"
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                bot_response = await message.channel.send(part, allowed_mentions=allowed_mentions, suppress_embeds=True)
                await store_bot_response_db(bot_response, client_user, message.guild, message.channel, part)

        await processing_msg.delete()
        logger.info(f"Command executed successfully (fallback): mention - Response length: {len(response)} - Split into {len(message_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing mention command (fallback): {str(e)}", exc_info=True)
        import config
        error_msg = config.ERROR_MESSAGES['processing_error']
        allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
        bot_response = await message.channel.send(error_msg, allowed_mentions=allowed_mentions, suppress_embeds=True)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
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
    allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
    bot_response = await message.channel.send(error_msg, allowed_mentions=allowed_mentions, suppress_embeds=True)
    await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)

# Helper function for message command handling
async def _handle_message_command_wrapper(message: discord.Message, client_user: discord.ClientUser, command_name: str, hours: int = 24, bot_client: discord.Client = None) -> None:
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

        await handle_summary_command(context, response_sender, thread_manager, hours=hours, bot_user=client_user, bot_client=bot_client)

    except Exception as e:
        logger.error(f"Error in handle_{command_name}_command: {str(e)}", exc_info=True)
        import config
        error_msg = config.ERROR_MESSAGES['summary_error']
        await _send_error_response(message, client_user, error_msg)

async def handle_sum_day_command(message: discord.Message, client_user: discord.ClientUser, bot_client: discord.Client = None) -> None:
    """Handles the /sum-day command using the abstraction layer."""
    await _handle_message_command_wrapper(message, client_user, "sum_day", hours=24, bot_client=bot_client)

async def handle_sum_hr_command(message: discord.Message, client_user: discord.ClientUser, bot_client: discord.Client = None) -> None:
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

    await _handle_message_command_wrapper(message, client_user, "sum_hr", hours=hours, bot_client=bot_client)

async def store_bot_response_db(bot_msg_obj: discord.Message, client_user: discord.ClientUser, guild: Optional[discord.Guild], channel: discord.abc.Messageable, content_to_store: str) -> None:
    """Helper function to store bot's own messages in the database."""
    try:
        guild_id_str = str(guild.id) if guild else None
        guild_name_str = guild.name if guild else None
        channel_id_str = str(channel.id)
        # Handle DM channel name
        channel_name_str = channel.name if hasattr(channel, 'name') else f"DM with {channel.recipient}"


        success = database.store_message(
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
            is_command=False, # Bot responses are not commands themselves
            command_type=None
        )
        if not success:
            logger.warning(f"Failed to store bot response {bot_msg_obj.id} in database")
    except Exception as e:
        logger.error(f"Error storing bot response in database: {str(e)}", exc_info=True)




