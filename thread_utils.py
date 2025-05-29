"""
Thread utilities module for the Discord bot.
Handles thread creation with consistent error handling.
"""

import discord
from typing import Optional
from logging_config import logger


async def create_thread_with_fallback(channel, thread_name: str, message_parts: list, 
                                    bot_response_handler, client_user, guild) -> bool:
    """
    Create a thread with fallback to channel posting if thread creation fails.
    
    Args:
        channel: The Discord channel to create the thread in
        thread_name (str): Name for the thread
        message_parts (list): List of message parts to send
        bot_response_handler: Function to handle bot response storage
        client_user: The bot user object
        guild: The Discord guild object
        
    Returns:
        bool: True if messages were sent successfully, False otherwise
    """
    try:
        if guild:
            try:
                logger.info(f"Attempting to create thread '{thread_name}' in channel #{channel.name}")
                # Create a standalone thread without attaching to a message
                thread = await channel.create_thread(name=thread_name, type=discord.ChannelType.public_thread)
                logger.info(f"Thread created successfully with ID {thread.id}")
                
                # Send messages to the thread
                for part in message_parts:
                    bot_response = await thread.send(part, allowed_mentions=discord.AllowedMentions.none())
                    await bot_response_handler(bot_response, client_user, guild, thread, part)
                    
                return True
                
            except discord.Forbidden as e:
                logger.warning(f"Bot lacks permission to create threads, posting to channel instead: {str(e)}")
                return await _fallback_to_channel(channel, message_parts, bot_response_handler, client_user, guild)
                
            except discord.HTTPException as e:
                logger.error(f"Failed to create thread: {e}, posting to channel instead")
                return await _fallback_to_channel(channel, message_parts, bot_response_handler, client_user, guild)
        else:
            # For DMs, post directly to the channel since threads aren't available
            return await _fallback_to_channel(channel, message_parts, bot_response_handler, client_user, guild)
            
    except Exception as e:
        logger.error(f"Error in thread creation with fallback: {str(e)}", exc_info=True)
        return False


async def _fallback_to_channel(channel, message_parts: list, bot_response_handler, 
                             client_user, guild) -> bool:
    """
    Fallback to posting messages directly to the channel.
    
    Args:
        channel: The Discord channel
        message_parts (list): List of message parts to send
        bot_response_handler: Function to handle bot response storage
        client_user: The bot user object
        guild: The Discord guild object
        
    Returns:
        bool: True if messages were sent successfully, False otherwise
    """
    try:
        for part in message_parts:
            bot_response = await channel.send(part, allowed_mentions=discord.AllowedMentions.none())
            await bot_response_handler(bot_response, client_user, guild, channel, part)
        return True
    except Exception as e:
        logger.error(f"Error in fallback to channel: {str(e)}", exc_info=True)
        return False
