"""
Database Helpers

This module provides centralized database operation utilities to eliminate
code duplication in message storage and data extraction patterns across the codebase.
"""

import discord
from logging_config import logger
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
import database


class DatabaseHelpers:
    """
    Centralized helpers for database operations.
    
    This class provides utilities for:
    - Extracting standardized message data from Discord objects
    - Safe message storage with error handling
    - Batch operations for multiple messages
    - Consistent parameter mapping
    """

    @staticmethod
    def extract_message_data(
        message: discord.Message,
        is_command: bool = False,
        command_type: Optional[str] = None,
        scraped_url: Optional[str] = None,
        scraped_content_summary: Optional[str] = None,
        scraped_content_key_points: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract standard message data for database storage from a Discord message.
        
        Args:
            message (discord.Message): The Discord message object
            is_command (bool): Whether the message is a command
            command_type (Optional[str]): The type of command if applicable
            scraped_url (Optional[str]): URL that was scraped from the message
            scraped_content_summary (Optional[str]): Summary of scraped content
            scraped_content_key_points (Optional[str]): Key points from scraped content
            
        Returns:
            Dict[str, Any]: Dictionary with all parameters needed for database storage
        """
        try:
            # Handle DM channel name
            if hasattr(message.channel, 'name'):
                channel_name = message.channel.name
            elif hasattr(message.channel, 'recipient'):
                channel_name = f"DM with {message.channel.recipient}"
            else:
                channel_name = "Unknown Channel"

            return {
                'message_id': str(message.id),
                'author_id': str(message.author.id),
                'author_name': str(message.author),
                'channel_id': str(message.channel.id),
                'channel_name': channel_name,
                'content': message.content,
                'created_at': message.created_at,
                'guild_id': str(message.guild.id) if message.guild else None,
                'guild_name': message.guild.name if message.guild else None,
                'is_bot': message.author.bot,
                'is_command': is_command,
                'command_type': command_type,
                'scraped_url': scraped_url,
                'scraped_content_summary': scraped_content_summary,
                'scraped_content_key_points': scraped_content_key_points
            }
        except Exception as e:
            logger.error(f"Error extracting message data: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def extract_bot_response_data(
        bot_message: discord.Message,
        client_user: discord.ClientUser,
        guild: Optional[discord.Guild],
        channel: Union[discord.TextChannel, discord.Thread, discord.DMChannel],
        content: str
    ) -> Dict[str, Any]:
        """
        Extract data for bot response storage with proper parameter mapping.
        
        Args:
            bot_message (discord.Message): The bot's message object
            client_user (discord.ClientUser): The bot's user object
            guild (Optional[discord.Guild]): The guild where message was sent
            channel: The channel where message was sent
            content (str): The actual content to store
            
        Returns:
            Dict[str, Any]: Dictionary with all parameters needed for database storage
        """
        try:
            # Handle DM channel name
            if hasattr(channel, 'name'):
                channel_name = channel.name
            elif hasattr(channel, 'recipient'):
                channel_name = f"DM with {channel.recipient}"
            else:
                channel_name = "Unknown Channel"

            return {
                'message_id': str(bot_message.id),
                'author_id': str(client_user.id),
                'author_name': str(client_user),
                'channel_id': str(channel.id),
                'channel_name': channel_name,
                'content': content,
                'created_at': bot_message.created_at,
                'guild_id': str(guild.id) if guild else None,
                'guild_name': guild.name if guild else None,
                'is_bot': True,
                'is_command': False,  # Bot responses are not commands themselves
                'command_type': None,
                'scraped_url': None,
                'scraped_content_summary': None,
                'scraped_content_key_points': None
            }
        except Exception as e:
            logger.error(f"Error extracting bot response data: {str(e)}", exc_info=True)
            raise

    @staticmethod
    async def store_message_safely(
        message: discord.Message,
        is_command: bool = False,
        command_type: Optional[str] = None,
        scraped_url: Optional[str] = None,
        scraped_content_summary: Optional[str] = None,
        scraped_content_key_points: Optional[str] = None
    ) -> bool:
        """
        Safe message storage with error handling and standardized data extraction.
        
        Args:
            message (discord.Message): The Discord message to store
            is_command (bool): Whether the message is a command
            command_type (Optional[str]): The type of command if applicable
            scraped_url (Optional[str]): URL that was scraped from the message
            scraped_content_summary (Optional[str]): Summary of scraped content
            scraped_content_key_points (Optional[str]): Key points from scraped content
            
        Returns:
            bool: True if storage was successful, False otherwise
        """
        try:
            message_data = DatabaseHelpers.extract_message_data(
                message=message,
                is_command=is_command,
                command_type=command_type,
                scraped_url=scraped_url,
                scraped_content_summary=scraped_content_summary,
                scraped_content_key_points=scraped_content_key_points
            )
            
            success = database.store_message(**message_data)
            if not success:
                logger.warning(f"Failed to store message {message.id} in database")
            
            return success
            
        except Exception as e:
            logger.error(f"Error in safe message storage for message {message.id}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    async def store_bot_response_safely(
        bot_message: discord.Message,
        client_user: discord.ClientUser,
        guild: Optional[discord.Guild],
        channel: Union[discord.TextChannel, discord.Thread, discord.DMChannel],
        content: str
    ) -> bool:
        """
        Safe bot response storage with error handling and standardized data extraction.
        
        Args:
            bot_message (discord.Message): The bot's message object
            client_user (discord.ClientUser): The bot's user object
            guild (Optional[discord.Guild]): The guild where message was sent
            channel: The channel where message was sent
            content (str): The actual content to store
            
        Returns:
            bool: True if storage was successful, False otherwise
        """
        try:
            message_data = DatabaseHelpers.extract_bot_response_data(
                bot_message=bot_message,
                client_user=client_user,
                guild=guild,
                channel=channel,
                content=content
            )
            
            success = database.store_message(**message_data)
            if not success:
                logger.warning(f"Failed to store bot response {bot_message.id} in database")
            
            return success
            
        except Exception as e:
            logger.error(f"Error in safe bot response storage for message {bot_message.id}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def prepare_dm_response_batch(
        response_parts: List[str],
        user_id: int,
        channel_id: int,
        channel_name: Optional[str],
        bot_user: discord.ClientUser,
        base_timestamp: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Prepare batch data for DM response storage.
        
        Args:
            response_parts (List[str]): List of response content parts
            user_id (int): The user ID for the DM
            channel_id (int): The DM channel ID
            channel_name (Optional[str]): Name for the channel
            bot_user (discord.ClientUser): The bot's user object
            base_timestamp (Optional[datetime]): Base timestamp for messages
            
        Returns:
            List[Dict[str, Any]]: List of message data dictionaries for batch storage
        """
        try:
            if base_timestamp is None:
                base_timestamp = datetime.now()
            
            bot_user_id = str(bot_user.id)
            bot_user_name = str(bot_user)
            channel_name_str = channel_name or "DM"
            
            messages_to_store = []
            
            for i, part in enumerate(response_parts):
                # Generate a unique message ID for each part
                message_id = f"bot_dm_response_{user_id}_{base_timestamp.timestamp()}_{i}"
                
                messages_to_store.append({
                    'message_id': message_id,
                    'author_id': bot_user_id,
                    'author_name': bot_user_name,
                    'channel_id': str(channel_id),
                    'channel_name': channel_name_str,
                    'content': part,
                    'created_at': base_timestamp,
                    'guild_id': None,  # DMs don't have guilds
                    'guild_name': None,
                    'is_bot': True,
                    'is_command': False,
                    'command_type': None,
                    'scraped_url': None,
                    'scraped_content_summary': None,
                    'scraped_content_key_points': None
                })
            
            return messages_to_store
            
        except Exception as e:
            logger.error(f"Error preparing DM response batch: {str(e)}", exc_info=True)
            raise

    @staticmethod
    async def store_dm_responses_safely(
        response_parts: List[str],
        user_id: int,
        channel_id: int,
        channel_name: Optional[str],
        bot_user: discord.ClientUser,
        base_timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Safe storage of DM responses with error handling.
        
        Args:
            response_parts (List[str]): List of response content parts
            user_id (int): The user ID for the DM
            channel_id (int): The DM channel ID
            channel_name (Optional[str]): Name for the channel
            bot_user (discord.ClientUser): The bot's user object
            base_timestamp (Optional[datetime]): Base timestamp for messages
            
        Returns:
            bool: True if storage was successful, False otherwise
        """
        try:
            if not bot_user:
                logger.error("bot_user parameter is required for storing DM responses")
                return False
            
            messages_to_store = DatabaseHelpers.prepare_dm_response_batch(
                response_parts=response_parts,
                user_id=user_id,
                channel_id=channel_id,
                channel_name=channel_name,
                bot_user=bot_user,
                base_timestamp=base_timestamp
            )
            
            # Store all messages in a single batch transaction
            success = await database.store_messages_batch(messages_to_store)
            if not success:
                logger.warning(f"Failed to store DM response batch for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error in safe DM response storage: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def validate_message_data(message_data: Dict[str, Any]) -> bool:
        """
        Validate that message data contains all required fields.
        
        Args:
            message_data (Dict[str, Any]): The message data to validate
            
        Returns:
            bool: True if data is valid, False otherwise
        """
        required_fields = [
            'message_id', 'author_id', 'author_name', 
            'channel_id', 'channel_name', 'content', 'created_at'
        ]
        
        try:
            for field in required_fields:
                if field not in message_data:
                    logger.error(f"Missing required field '{field}' in message data")
                    return False
                
                if message_data[field] is None:
                    logger.error(f"Required field '{field}' cannot be None")
                    return False
                    
                if field != 'created_at' and not str(message_data[field]).strip():
                    logger.error(f"Required field '{field}' cannot be empty")
                    return False
            
            # Validate created_at is datetime
            if not isinstance(message_data['created_at'], datetime):
                logger.error("Field 'created_at' must be a datetime object")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating message data: {str(e)}", exc_info=True)
            return False