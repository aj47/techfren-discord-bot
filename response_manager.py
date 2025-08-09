"""
Response Manager

This module provides centralized response management capabilities to eliminate 
code duplication in thread creation and message sending logic across the codebase.
"""

import discord
from logging_config import logger
from typing import Optional, List, Union
from command_abstraction import ThreadManager, MessageResponseSender


class ResponseManager:
    """
    Centralized manager for Discord response operations.
    
    This class provides unified response management that:
    - Creates threads attached to user messages
    - Handles fallback to channel responses when thread creation fails
    - Manages message splitting and multi-part responses
    - Provides consistent error handling across response types
    """

    @staticmethod
    async def send_response(
        message: discord.Message, 
        content: str, 
        client_user: discord.ClientUser,
        create_thread: bool = False,
        thread_name: Optional[str] = None,
        store_in_db: bool = True
    ) -> Optional[discord.Message]:
        """
        Send a response with optional thread creation and database storage.
        
        Args:
            message (discord.Message): The original message to respond to
            content (str): The content to send
            client_user (discord.ClientUser): The bot's user for database storage
            create_thread (bool): Whether to create a thread for the response
            thread_name (Optional[str]): Name for the thread (auto-generated if None)
            store_in_db (bool): Whether to store the response in database
            
        Returns:
            Optional[discord.Message]: The sent message or None if failed
        """
        try:
            if create_thread and message.guild:
                return await ResponseManager._send_thread_response(
                    message, content, client_user, thread_name, store_in_db
                )
            else:
                return await ResponseManager._send_channel_response(
                    message, content, client_user, store_in_db
                )
        except Exception as e:
            logger.error(f"Error sending response: {str(e)}", exc_info=True)
            return None

    @staticmethod
    async def send_response_parts(
        message: discord.Message,
        content_parts: List[str],
        client_user: discord.ClientUser,
        create_thread: bool = False,
        thread_name: Optional[str] = None,
        store_in_db: bool = True
    ) -> List[discord.Message]:
        """
        Send multiple response parts with optional thread creation and database storage.
        
        Args:
            message (discord.Message): The original message to respond to
            content_parts (List[str]): List of content parts to send
            client_user (discord.ClientUser): The bot's user for database storage
            create_thread (bool): Whether to create a thread for responses
            thread_name (Optional[str]): Name for the thread (auto-generated if None)
            store_in_db (bool): Whether to store responses in database
            
        Returns:
            List[discord.Message]: List of sent messages
        """
        sent_messages = []
        try:
            if create_thread and message.guild:
                sent_messages = await ResponseManager._send_thread_response_parts(
                    message, content_parts, client_user, thread_name, store_in_db
                )
            else:
                sent_messages = await ResponseManager._send_channel_response_parts(
                    message, content_parts, client_user, store_in_db
                )
        except Exception as e:
            logger.error(f"Error sending response parts: {str(e)}", exc_info=True)
        
        return sent_messages

    @staticmethod
    async def create_thread_response(
        message: discord.Message,
        content: str,
        thread_name: str,
        client_user: discord.ClientUser,
        store_in_db: bool = True
    ) -> Optional[discord.Message]:
        """
        Create a thread and send response content in it.
        
        Args:
            message (discord.Message): The message to create thread from
            content (str): Content to send in the thread
            thread_name (str): Name for the thread
            client_user (discord.ClientUser): The bot's user for database storage
            store_in_db (bool): Whether to store the response in database
            
        Returns:
            Optional[discord.Message]: The sent message or None if failed
        """
        return await ResponseManager._send_thread_response(
            message, content, client_user, thread_name, store_in_db
        )

    @staticmethod
    async def _send_thread_response(
        message: discord.Message,
        content: str,
        client_user: discord.ClientUser,
        thread_name: Optional[str] = None,
        store_in_db: bool = True
    ) -> Optional[discord.Message]:
        """Internal method to send response in a thread with fallback."""
        try:
            # Generate thread name if not provided
            if thread_name is None:
                thread_name = f"Bot Response - {message.author.display_name}"

            # Create thread manager and attempt thread creation
            thread_manager = ThreadManager(message.channel, message.guild)
            thread = await thread_manager.create_thread_from_message(message, thread_name)

            if thread:
                # Send response in thread
                thread_sender = MessageResponseSender(thread)
                bot_response = await thread_sender.send(content)
                
                if bot_response and store_in_db:
                    await ResponseManager._store_bot_response(
                        bot_response, client_user, message.guild, thread, content
                    )
                
                logger.debug(f"Response sent successfully in thread: {thread_name}")
                return bot_response
            else:
                # Fallback to channel response
                logger.warning("Thread creation failed, falling back to channel response")
                return await ResponseManager._send_channel_response(
                    message, content, client_user, store_in_db
                )

        except Exception as e:
            logger.error(f"Error sending thread response: {str(e)}", exc_info=True)
            # Fallback to channel response
            return await ResponseManager._send_channel_response(
                message, content, client_user, store_in_db
            )

    @staticmethod
    async def _send_thread_response_parts(
        message: discord.Message,
        content_parts: List[str],
        client_user: discord.ClientUser,
        thread_name: Optional[str] = None,
        store_in_db: bool = True
    ) -> List[discord.Message]:
        """Internal method to send multiple response parts in a thread with fallback."""
        sent_messages = []
        try:
            # Generate thread name if not provided
            if thread_name is None:
                thread_name = f"Bot Response - {message.author.display_name}"

            # Create thread manager and attempt thread creation
            thread_manager = ThreadManager(message.channel, message.guild)
            thread = await thread_manager.create_thread_from_message(message, thread_name)

            if thread:
                # Send all parts in thread
                thread_sender = MessageResponseSender(thread)
                for part in content_parts:
                    bot_response = await thread_sender.send(part)
                    if bot_response:
                        sent_messages.append(bot_response)
                        if store_in_db:
                            await ResponseManager._store_bot_response(
                                bot_response, client_user, message.guild, thread, part
                            )
                
                logger.debug(f"Response parts sent successfully in thread: {thread_name} ({len(sent_messages)} parts)")
            else:
                # Fallback to channel response
                logger.warning("Thread creation failed, falling back to channel response")
                sent_messages = await ResponseManager._send_channel_response_parts(
                    message, content_parts, client_user, store_in_db
                )

        except Exception as e:
            logger.error(f"Error sending thread response parts: {str(e)}", exc_info=True)
            # Fallback to channel response
            sent_messages = await ResponseManager._send_channel_response_parts(
                message, content_parts, client_user, store_in_db
            )
        
        return sent_messages

    @staticmethod
    async def _send_channel_response(
        message: discord.Message,
        content: str,
        client_user: discord.ClientUser,
        store_in_db: bool = True
    ) -> Optional[discord.Message]:
        """Internal method to send response in channel."""
        try:
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
            bot_response = await message.channel.send(
                content, 
                allowed_mentions=allowed_mentions, 
                suppress_embeds=True
            )
            
            if bot_response and store_in_db:
                await ResponseManager._store_bot_response(
                    bot_response, client_user, message.guild, message.channel, content
                )
            
            logger.debug("Response sent successfully in channel")
            return bot_response

        except Exception as e:
            logger.error(f"Error sending channel response: {str(e)}", exc_info=True)
            return None

    @staticmethod
    async def _send_channel_response_parts(
        message: discord.Message,
        content_parts: List[str],
        client_user: discord.ClientUser,
        store_in_db: bool = True
    ) -> List[discord.Message]:
        """Internal method to send multiple response parts in channel."""
        sent_messages = []
        try:
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
            
            for part in content_parts:
                bot_response = await message.channel.send(
                    part, 
                    allowed_mentions=allowed_mentions, 
                    suppress_embeds=True
                )
                
                if bot_response:
                    sent_messages.append(bot_response)
                    if store_in_db:
                        await ResponseManager._store_bot_response(
                            bot_response, client_user, message.guild, message.channel, part
                        )
            
            logger.debug(f"Response parts sent successfully in channel ({len(sent_messages)} parts)")

        except Exception as e:
            logger.error(f"Error sending channel response parts: {str(e)}", exc_info=True)
        
        return sent_messages

    @staticmethod
    async def send_processing_message(
        message: discord.Message,
        processing_text: str = "Processing your request, please wait...",
        create_thread: bool = False,
        thread_name: Optional[str] = None
    ) -> Optional[discord.Message]:
        """
        Send a processing message that can be deleted later.
        
        Args:
            message (discord.Message): The original message to respond to
            processing_text (str): Text for the processing message
            create_thread (bool): Whether to create a thread for the processing message
            thread_name (Optional[str]): Name for the thread
            
        Returns:
            Optional[discord.Message]: The processing message that can be deleted
        """
        try:
            if create_thread and message.guild:
                # Generate thread name if not provided
                if thread_name is None:
                    thread_name = f"Bot Response - {message.author.display_name}"

                # Create thread and send processing message
                thread_manager = ThreadManager(message.channel, message.guild)
                thread = await thread_manager.create_thread_from_message(message, thread_name)

                if thread:
                    thread_sender = MessageResponseSender(thread)
                    return await thread_sender.send(processing_text)
                else:
                    # Fallback to channel
                    return await message.channel.send(processing_text)
            else:
                return await message.channel.send(processing_text)

        except Exception as e:
            logger.error(f"Error sending processing message: {str(e)}", exc_info=True)
            return None

    @staticmethod
    async def _store_bot_response(
        bot_response: discord.Message,
        client_user: discord.ClientUser,
        guild: Optional[discord.Guild],
        channel: Union[discord.TextChannel, discord.Thread],
        content: str
    ) -> None:
        """Internal method to store bot responses in database."""
        try:
            # Import here to avoid circular imports
            from database_helpers import DatabaseHelpers
            success = await DatabaseHelpers.store_bot_response_safely(
                bot_message=bot_response,
                client_user=client_user,
                guild=guild,
                channel=channel,
                content=content
            )
            if not success:
                logger.warning(f"Failed to store bot response {bot_response.id} in database")
        except Exception as e:
            logger.error(f"Error storing bot response in database: {str(e)}", exc_info=True)