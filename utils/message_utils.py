"""
Shared utilities for message handling, thread creation, and bot responses.
"""
import logging
import discord
from typing import List, Optional, Union

logger = logging.getLogger('discord_bot')

async def safe_delete_message(message: discord.Message) -> bool:
    """
    Safely delete a message with error handling.
    
    Args:
        message: Discord message to delete
        
    Returns:
        bool: True if successfully deleted, False otherwise
    """
    try:
        await message.delete()
        return True
    except Exception as e:
        logger.warning(f"Could not delete message: {e}")
        return False

async def send_and_store_response(
    channel: Union[discord.TextChannel, discord.Thread], 
    content: str, 
    client_user: discord.User, 
    guild: Optional[discord.Guild]
) -> discord.Message:
    """
    Send a message and store it in the database.
    
    Args:
        channel: Channel or thread to send message to
        content: Message content
        client_user: Bot user for database storage
        guild: Guild for database storage
        
    Returns:
        discord.Message: The sent message
    """
    # Import here to avoid circular imports
    from command_handler import store_bot_response_db
    
    response = await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
    await store_bot_response_db(response, client_user, guild, channel, content)
    return response

async def create_thread_with_fallback(
    channel: discord.TextChannel, 
    thread_name: str, 
    messages: List[str], 
    client_user: discord.User, 
    guild: Optional[discord.Guild]
) -> Union[discord.Thread, discord.TextChannel]:
    """
    Create a thread and send messages to it, with fallback to channel if thread creation fails.
    
    Args:
        channel: Channel to create thread in
        thread_name: Name for the thread
        messages: List of messages to send
        client_user: Bot user for database storage
        guild: Guild for database storage
        
    Returns:
        Union[discord.Thread, discord.TextChannel]: The thread if successful, channel if fallback
    """
    try:
        logger.info(f"Attempting to create thread '{thread_name}' in channel #{channel.name}")
        thread = await channel.create_thread(name=thread_name, type=discord.ChannelType.public_thread)
        logger.info(f"Thread created successfully with ID {thread.id}")
        
        # Send messages to thread
        for message_content in messages:
            await send_and_store_response(thread, message_content, client_user, guild)
        
        return thread
        
    except discord.Forbidden as e:
        logger.warning(f"Bot lacks permission to create threads, posting to channel instead: {str(e)}")
        # Fallback to posting in channel
        for message_content in messages:
            await send_and_store_response(channel, message_content, client_user, guild)
        return channel
        
    except discord.HTTPException as e:
        logger.error(f"Failed to create thread: {e}, posting to channel instead")
        # Fallback to posting in channel
        for message_content in messages:
            await send_and_store_response(channel, message_content, client_user, guild)
        return channel

async def send_processing_message(
    channel: Union[discord.TextChannel, discord.Thread], 
    message: str = "Processing your request..."
) -> Optional[discord.Message]:
    """
    Send a processing message that can be deleted later.
    
    Args:
        channel: Channel to send message to
        message: Processing message content
        
    Returns:
        Optional[discord.Message]: The sent message or None if failed
    """
    try:
        return await channel.send(message)
    except Exception as e:
        logger.warning(f"Failed to send processing message: {e}")
        return None

async def handle_command_error(
    channel: Union[discord.TextChannel, discord.Thread],
    error_message: str,
    client_user: discord.User,
    guild: Optional[discord.Guild],
    processing_msg: Optional[discord.Message] = None
) -> None:
    """
    Handle command errors by sending error message and cleaning up processing message.
    
    Args:
        channel: Channel to send error message to
        error_message: Error message to send
        client_user: Bot user for database storage
        guild: Guild for database storage
        processing_msg: Optional processing message to delete
    """
    try:
        await send_and_store_response(channel, error_message, client_user, guild)
    except Exception as e:
        logger.error(f"Failed to send error message: {e}")
    
    if processing_msg:
        await safe_delete_message(processing_msg)

def validate_hours_parameter(hours: int) -> tuple[bool, Optional[str]]:
    """
    Validate the hours parameter for summary commands.
    
    Args:
        hours: Number of hours to validate
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not isinstance(hours, int):
        return False, "Hours parameter must be a number."
    
    if hours <= 0:
        return False, "Number of hours must be greater than 0."
    
    if hours > 168:  # 7 days
        return False, "Number of hours cannot exceed 168 (7 days). For longer periods, please use multiple smaller summaries."
    
    return True, None