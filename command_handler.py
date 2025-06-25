import discord
import database
from logging_config import logger
from rate_limiter import check_rate_limit
from llm_handler import call_llm_api
from message_utils import split_long_message, get_message_context
from firecrawl_handler import scrape_url_content
import re
from typing import Optional, Union, cast

async def handle_bot_command(message: discord.Message, client_user: discord.ClientUser, bot_client: Optional[discord.Client] = None) -> None:
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

                response = await call_llm_api(query, message_context)
                message_parts = await split_long_message(response)

                # Send all response parts in the thread
                for part in message_parts:
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
            # Fallback: if thread creation failed, send response in main channel
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
            bot_response = await message.channel.send(error_msg, allowed_mentions=allowed_mentions)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
    except Exception as e:
        logger.error(f"Error sending error response in thread: {str(e)}", exc_info=True)
        # Ultimate fallback to channel response
        allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
        bot_response = await message.channel.send(error_msg, allowed_mentions=allowed_mentions)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)


async def _handle_bot_command_fallback(message: discord.Message, client_user: discord.ClientUser, query: str, bot_client: Optional[discord.Client] = None) -> None:
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

        for part in message_parts:
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
            bot_response = await message.channel.send(part, allowed_mentions=allowed_mentions)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, part)

        await processing_msg.delete()
        logger.info(f"Command executed successfully (fallback): mention - Response length: {len(response)} - Split into {len(message_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing mention command (fallback): {str(e)}", exc_info=True)
        import config
        error_msg = config.ERROR_MESSAGES['processing_error']
        allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
        bot_response = await message.channel.send(error_msg, allowed_mentions=allowed_mentions)
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
    bot_response = await message.channel.send(error_msg, allowed_mentions=allowed_mentions)
    await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)

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
    try:
        guild_id_str = str(guild.id) if guild else None
        guild_name_str = guild.name if guild else None
        # Ensure channel has an id attribute
        if hasattr(channel, 'id'):
            channel_id_str = str(channel.id)
        else:
            logger.error(f"Channel type {type(channel)} has no id attribute")
            return
        
        # Handle DM channel name with proper type checking
        if hasattr(channel, 'name') and channel.name is not None:
            channel_name_str = channel.name
        elif hasattr(channel, 'recipient'):
            channel_name_str = f"DM with {channel.recipient}"
        else:
            channel_name_str = "Unknown channel"


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


def check_firecrawl_permission(user_id: str) -> bool:
    """
    Check if a user has permission to use the !firecrawl command.
    
    Args:
        user_id (str): Discord user ID to check
        
    Returns:
        bool: True if user has permission, False otherwise
    """
    import config
    
    # Check if user is in the allowed list
    has_permission = user_id in config.firecrawl_allowed_users
    
    # Debug logging to track permission checks
    if has_permission:
        logger.debug(f"Permission check GRANTED for user ID {user_id} - User is in allowed list")
    else:
        logger.debug(f"Permission check DENIED for user ID {user_id} - User not in allowed list (allowed: {config.firecrawl_allowed_users})")
    
    return has_permission


async def handle_firecrawl_command(message: discord.Message, client_user: discord.ClientUser) -> None:
    """Handles the !firecrawl <url> command with user permission checks."""
    import config
    
    # Check user permission
    if not check_firecrawl_permission(str(message.author.id)):
        error_msg = config.ERROR_MESSAGES['firecrawl_permission_denied']
        await _send_error_response_thread(message, client_user, error_msg)
        logger.info(f"Firecrawl command denied for user {message.author} (ID: {message.author.id})")
        return
    
    # Parse URL from command
    content = message.content.strip()
    match = re.match(r'!firecrawl\s+(.+)', content)
    
    if not match:
        error_msg = config.ERROR_MESSAGES['firecrawl_missing_url']
        await _send_error_response_thread(message, client_user, error_msg)
        return
    
    url = match.group(1).strip()
    
    # Basic URL validation
    if not (url.startswith('http://') or url.startswith('https://')):
        error_msg = config.ERROR_MESSAGES['firecrawl_invalid_url']
        await _send_error_response_thread(message, client_user, error_msg)
        return
    
    logger.info(f"Executing firecrawl command - URL: {url} - Requested by {message.author}")
    
    # Check rate limits
    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        if reason == "cooldown":
            error_msg = config.ERROR_MESSAGES['rate_limit_cooldown'].format(wait_time=wait_time)
        else:
            error_msg = config.ERROR_MESSAGES['rate_limit_exceeded'].format(wait_time=wait_time)
        await _send_error_response_thread(message, client_user, error_msg)
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return
    
    # Create thread for response
    thread_name = f"Firecrawl - {message.author.display_name}"
    
    try:
        from command_abstraction import ThreadManager, MessageResponseSender
        thread_manager = ThreadManager(message.channel, message.guild)
        
        # Create thread from the user's original message
        thread = await thread_manager.create_thread_from_message(message, thread_name)
        
        if thread:
            # Send processing message in the thread
            thread_sender = MessageResponseSender(thread)
            processing_msg = await thread_sender.send(f"Scraping URL: {url}\nPlease wait...")
            
            try:
                # Scrape the URL using Firecrawl
                scraped_content = await scrape_url_content(url)
                
                if scraped_content:
                    # Split long content into multiple messages
                    message_parts = await split_long_message(scraped_content)
                    
                    # Send all response parts in the thread
                    for part in message_parts:
                        bot_response = await thread_sender.send(part)
                        if bot_response:
                            await store_bot_response_db(bot_response, client_user, message.guild, thread, part)
                    
                    logger.info(f"Firecrawl command executed successfully - URL: {url} - Response length: {len(scraped_content)} - Split into {len(message_parts)} parts")
                else:
                    error_msg = config.ERROR_MESSAGES['firecrawl_error']
                    await thread_sender.send(error_msg)
                
                # Delete processing message
                if processing_msg:
                    await processing_msg.delete()
                    
            except Exception as e:
                logger.error(f"Error scraping URL {url}: {str(e)}", exc_info=True)
                error_msg = config.ERROR_MESSAGES['firecrawl_error']
                await thread_sender.send(error_msg)
                try:
                    if processing_msg:
                        await processing_msg.delete()
                except discord.NotFound:
                    pass
        else:
            # Fallback: if thread creation failed, send response in main channel
            logger.warning("Thread creation failed for firecrawl command, falling back to channel response")
            await _handle_firecrawl_command_fallback(message, client_user, url)
            
    except Exception as e:
        logger.error(f"Error in thread-based firecrawl command handling: {str(e)}", exc_info=True)
        # Fallback to original behavior
        await _handle_firecrawl_command_fallback(message, client_user, url)


async def _handle_firecrawl_command_fallback(message: discord.Message, client_user: discord.ClientUser, url: str) -> None:
    """Fallback handler for firecrawl command when thread creation fails."""
    import config
    
    processing_msg = await message.channel.send(f"Scraping URL: {url}\nPlease wait...")
    try:
        # Scrape the URL using Firecrawl
        scraped_content = await scrape_url_content(url)
        
        if scraped_content:
            # Split long content into multiple messages
            message_parts = await split_long_message(scraped_content)
            
            for part in message_parts:
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                bot_response = await message.channel.send(part, allowed_mentions=allowed_mentions)
                await store_bot_response_db(bot_response, client_user, message.guild, message.channel, part)
            
            logger.info(f"Firecrawl command executed successfully (fallback) - URL: {url} - Response length: {len(scraped_content)} - Split into {len(message_parts)} parts")
        else:
            error_msg = config.ERROR_MESSAGES['firecrawl_error']
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
            bot_response = await message.channel.send(error_msg, allowed_mentions=allowed_mentions)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        
        await processing_msg.delete()
    except Exception as e:
        logger.error(f"Error processing firecrawl command (fallback): {str(e)}", exc_info=True)
        error_msg = config.ERROR_MESSAGES['firecrawl_error']
        allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
        bot_response = await message.channel.send(error_msg, allowed_mentions=allowed_mentions)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        try:
            await processing_msg.delete()
        except discord.NotFound:
            pass


