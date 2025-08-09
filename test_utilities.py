"""
Test Utilities

This module provides centralized test utilities to eliminate code duplication
in mock object creation and test setup patterns across test files.
"""

import discord
from unittest.mock import MagicMock, AsyncMock, Mock
from datetime import datetime
from typing import Optional, Dict, Any, Union, List


class MockFactories:
    """
    Factory class for creating standardized mock objects for testing.
    
    This class provides static methods to create consistent mock Discord objects
    with sensible defaults that can be customized as needed for specific tests.
    """

    @staticmethod
    def create_mock_message(
        content: str = "Test message",
        message_id: Union[str, int] = "test_message_id",
        author: Optional[Mock] = None,
        channel: Optional[Mock] = None,
        guild: Optional[Mock] = None,
        created_at: Optional[datetime] = None,
        reference: Optional[Mock] = None,
        **kwargs
    ) -> Mock:
        """
        Create a standardized mock Discord message object.
        
        Args:
            content (str): Message content
            message_id (Union[str, int]): Message ID
            author (Optional[Mock]): Mock author object
            channel (Optional[Mock]): Mock channel object
            guild (Optional[Mock]): Mock guild object
            created_at (Optional[datetime]): Message creation timestamp
            reference (Optional[Mock]): Mock message reference for replies
            **kwargs: Additional attributes to set on the mock
            
        Returns:
            Mock: Configured mock message object
        """
        message = Mock(spec=discord.Message)
        message.id = message_id
        message.content = content
        message.created_at = created_at or datetime.now()
        message.reference = reference
        
        # Set up author
        if author is None:
            message.author = MockFactories.create_mock_user()
        else:
            message.author = author
            
        # Set up channel
        if channel is None:
            message.channel = MockFactories.create_mock_channel()
        else:
            message.channel = channel
            
        # Set up guild
        if guild is None:
            message.guild = MockFactories.create_mock_guild()
        else:
            message.guild = guild
            
        # Set any additional attributes
        for key, value in kwargs.items():
            setattr(message, key, value)
            
        return message

    @staticmethod
    def create_mock_user(
        user_id: Union[str, int] = "test_user_id",
        name: str = "TestUser",
        display_name: str = "Test User",
        is_bot: bool = False,
        **kwargs
    ) -> Mock:
        """
        Create a standardized mock Discord user object.
        
        Args:
            user_id (Union[str, int]): User ID
            name (str): Username
            display_name (str): Display name
            is_bot (bool): Whether the user is a bot
            **kwargs: Additional attributes to set on the mock
            
        Returns:
            Mock: Configured mock user object
        """
        user = Mock(spec=discord.User)
        user.id = user_id
        user.name = name
        user.display_name = display_name
        user.bot = is_bot
        user.__str__ = Mock(return_value=display_name)
        
        # Set any additional attributes
        for key, value in kwargs.items():
            setattr(user, key, value)
            
        return user

    @staticmethod
    def create_mock_client_user(
        user_id: Union[str, int] = "bot_user_id",
        name: str = "TestBot",
        **kwargs
    ) -> Mock:
        """
        Create a standardized mock Discord client user (bot) object.
        
        Args:
            user_id (Union[str, int]): Bot user ID
            name (str): Bot name
            **kwargs: Additional attributes to set on the mock
            
        Returns:
            Mock: Configured mock client user object
        """
        client_user = Mock(spec=discord.ClientUser)
        client_user.id = user_id
        client_user.name = name
        client_user.__str__ = Mock(return_value=name)
        
        # Set any additional attributes
        for key, value in kwargs.items():
            setattr(client_user, key, value)
            
        return client_user

    @staticmethod
    def create_mock_channel(
        channel_id: Union[str, int] = "test_channel_id",
        name: str = "test-channel",
        channel_type: str = "text",
        **kwargs
    ) -> Mock:
        """
        Create a standardized mock Discord channel object.
        
        Args:
            channel_id (Union[str, int]): Channel ID
            name (str): Channel name
            channel_type (str): Channel type ('text', 'dm', 'thread')
            **kwargs: Additional attributes to set on the mock
            
        Returns:
            Mock: Configured mock channel object
        """
        if channel_type == "text":
            channel = AsyncMock(spec=discord.TextChannel)
        elif channel_type == "dm":
            channel = AsyncMock(spec=discord.DMChannel)
            channel.recipient = MockFactories.create_mock_user(name="DMUser")
        elif channel_type == "thread":
            channel = AsyncMock(spec=discord.Thread)
        else:
            channel = AsyncMock()
            
        channel.id = channel_id
        channel.name = name
        channel.send = AsyncMock()
        
        # Set any additional attributes
        for key, value in kwargs.items():
            setattr(channel, key, value)
            
        return channel

    @staticmethod
    def create_mock_guild(
        guild_id: Union[str, int] = "test_guild_id",
        name: str = "Test Guild",
        **kwargs
    ) -> Mock:
        """
        Create a standardized mock Discord guild object.
        
        Args:
            guild_id (Union[str, int]): Guild ID
            name (str): Guild name
            **kwargs: Additional attributes to set on the mock
            
        Returns:
            Mock: Configured mock guild object
        """
        guild = Mock(spec=discord.Guild)
        guild.id = guild_id
        guild.name = name
        guild.get_channel = Mock()
        
        # Set any additional attributes
        for key, value in kwargs.items():
            setattr(guild, key, value)
            
        return guild

    @staticmethod
    def create_mock_thread(
        thread_id: Union[str, int] = "test_thread_id",
        name: str = "Test Thread",
        **kwargs
    ) -> Mock:
        """
        Create a standardized mock Discord thread object.
        
        Args:
            thread_id (Union[str, int]): Thread ID
            name (str): Thread name
            **kwargs: Additional attributes to set on the mock
            
        Returns:
            Mock: Configured mock thread object
        """
        thread = AsyncMock(spec=discord.Thread)
        thread.id = thread_id
        thread.name = name
        thread.send = AsyncMock()
        thread.mention = f"<#{thread_id}>"
        
        # Set any additional attributes
        for key, value in kwargs.items():
            setattr(thread, key, value)
            
        return thread

    @staticmethod
    def create_mock_message_reference(
        message_id: Union[str, int] = "referenced_message_id",
        channel_id: Union[str, int] = "test_channel_id",
        cached_message: Optional[Mock] = None,
        **kwargs
    ) -> Mock:
        """
        Create a standardized mock Discord message reference object.
        
        Args:
            message_id (Union[str, int]): Referenced message ID
            channel_id (Union[str, int]): Channel ID of referenced message
            cached_message (Optional[Mock]): Mock cached message object
            **kwargs: Additional attributes to set on the mock
            
        Returns:
            Mock: Configured mock message reference object
        """
        reference = Mock(spec=discord.MessageReference)
        reference.message_id = message_id
        reference.channel_id = channel_id
        reference.cached_message = cached_message
        
        # Set any additional attributes
        for key, value in kwargs.items():
            setattr(reference, key, value)
            
        return reference


class TestDataFactories:
    """
    Factory class for creating test data structures.
    
    This class provides methods to create standardized test data that matches
    the expected formats used throughout the application.
    """

    @staticmethod
    def create_message_data(
        message_id: str = "test_message_id",
        author_name: str = "TestUser",
        content: str = "Test message content",
        created_at: Optional[datetime] = None,
        is_bot: bool = False,
        is_command: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create standardized message data dictionary for database testing.
        
        Args:
            message_id (str): Message ID
            author_name (str): Author name
            content (str): Message content
            created_at (Optional[datetime]): Creation timestamp
            is_bot (bool): Whether message is from bot
            is_command (bool): Whether message is a command
            **kwargs: Additional fields to include
            
        Returns:
            Dict[str, Any]: Message data dictionary
        """
        data = {
            'id': message_id,
            'author_name': author_name,
            'content': content,
            'created_at': created_at or datetime.now(),
            'is_bot': is_bot,
            'is_command': is_command,
            'scraped_url': None,
            'scraped_content_summary': None,
            'scraped_content_key_points': None,
            'guild_id': 'test_guild_id',
            'channel_id': 'test_channel_id'
        }
        
        # Merge in any additional fields
        data.update(kwargs)
        return data

    @staticmethod
    def create_message_batch(count: int = 3, **base_kwargs) -> List[Dict[str, Any]]:
        """
        Create a batch of test message data.
        
        Args:
            count (int): Number of messages to create
            **base_kwargs: Base arguments for all messages
            
        Returns:
            List[Dict[str, Any]]: List of message data dictionaries
        """
        messages = []
        base_time = datetime.now()
        
        for i in range(count):
            message_data = TestDataFactories.create_message_data(
                message_id=f"test_message_{i}",
                author_name=f"TestUser{i}",
                content=f"Test message {i}",
                created_at=base_time,
                **base_kwargs
            )
            messages.append(message_data)
            
        return messages


class MockHelpers:
    """
    Helper methods for common test setup and assertion patterns.
    """

    @staticmethod
    def setup_mock_datetime(mock_obj: Mock, datetime_str: str = "2024-01-01 12:00:00 UTC") -> None:
        """
        Set up a mock datetime object with strftime method.
        
        Args:
            mock_obj (Mock): Mock object to configure
            datetime_str (str): String to return from strftime
        """
        mock_obj.strftime = Mock(return_value=datetime_str)

    @staticmethod
    def create_async_mock_with_return(return_value: Any = None) -> AsyncMock:
        """
        Create an AsyncMock with a specified return value.
        
        Args:
            return_value (Any): Value to return from the async mock
            
        Returns:
            AsyncMock: Configured async mock
        """
        async_mock = AsyncMock()
        async_mock.return_value = return_value
        return async_mock

    @staticmethod
    def create_context_dict(
        original_message: Optional[Mock] = None,
        referenced_message: Optional[Mock] = None,
        linked_messages: Optional[List[Mock]] = None
    ) -> Dict[str, Any]:
        """
        Create a standardized message context dictionary for testing.
        
        Args:
            original_message (Optional[Mock]): Original message mock
            referenced_message (Optional[Mock]): Referenced message mock
            linked_messages (Optional[List[Mock]]): List of linked message mocks
            
        Returns:
            Dict[str, Any]: Context dictionary
        """
        return {
            'original_message': original_message,
            'referenced_message': referenced_message,
            'linked_messages': linked_messages or []
        }

    @staticmethod
    def setup_llm_completion_mock(mock_client: Mock, response_content: str = "Test LLM response") -> Mock:
        """
        Set up a mock LLM completion response.
        
        Args:
            mock_client (Mock): Mock OpenAI client
            response_content (str): Content to return from completion
            
        Returns:
            Mock: Configured completion mock
        """
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message = Mock()
        mock_completion.choices[0].message.content = response_content
        
        mock_client.chat.completions.create.return_value = mock_completion
        return mock_completion


# Legacy compatibility - provide the old MockMessage class for existing tests
class MockMessage:
    """Legacy MockMessage class for backward compatibility."""
    
    def __init__(self, content, author=None, channel=None, guild=None, id="test_id"):
        mock_message = MockFactories.create_mock_message(
            content=content,
            message_id=id,
            author=author,
            channel=channel,
            guild=guild
        )
        
        # Copy all attributes from mock to this instance
        for attr_name in dir(mock_message):
            if not attr_name.startswith('_'):
                setattr(self, attr_name, getattr(mock_message, attr_name))