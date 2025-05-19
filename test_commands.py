"""
Test script for the Discord bot commands.
This script tests the bot's command handling functionality.
"""

import os
import sys
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from datetime import datetime
import bot
import database

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('test_commands')

class MockMessage:
    """Mock Discord message for testing"""
    def __init__(self, content, author=None, channel=None, guild=None, id="test_id"):
        self.content = content
        self.author = author or MagicMock()
        self.channel = channel or MagicMock()
        self.guild = guild or MagicMock()
        self.id = id
        self.created_at = datetime.now()

        # Set up author
        if isinstance(self.author, MagicMock):
            self.author.id = "test_author_id"
            self.author.name = "Test User"
            self.author.bot = False

        # Set up channel
        if isinstance(self.channel, MagicMock):
            self.channel.id = "test_channel_id"
            self.channel.name = "test-channel"
            self.channel.send = AsyncMock()

        # Set up guild
        if isinstance(self.guild, MagicMock):
            self.guild.id = "test_guild_id"
            self.guild.name = "Test Guild"

class TestBotCommands(unittest.TestCase):
    """Test case for bot commands"""

    def setUp(self):
        """Set up test environment"""
        # Initialize database
        try:
            database.init_database()
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            self.fail("Database initialization failed")

        # Mock client
        self.client = MagicMock()
        self.client.user = MagicMock()
        self.client.user.id = "test_bot_id"
        self.client.user.name = "Test Bot"

        # Store original client
        self.original_client = bot.client
        bot.client = self.client

        # Mock config
        self.config_patcher = patch('bot.config')
        self.mock_config = self.config_patcher.start()
        self.mock_config.token = "test_token"
        self.mock_config.openrouter = "test_openrouter_key"

        # Mock call_llm_api and call_llm_for_summary
        self.call_llm_api_patcher = patch('bot.call_llm_api')
        self.mock_call_llm_api = self.call_llm_api_patcher.start()
        self.mock_call_llm_api.return_value = "This is a test response from the LLM API."

        self.call_llm_for_summary_patcher = patch('bot.call_llm_for_summary')
        self.mock_call_llm_for_summary = self.call_llm_for_summary_patcher.start()
        self.mock_call_llm_for_summary.return_value = "This is a test summary from the LLM API."

        # Mock database functions
        self.store_message_patcher = patch('database.store_message')
        self.mock_store_message = self.store_message_patcher.start()
        self.mock_store_message.return_value = True

        self.get_channel_messages_for_day_patcher = patch('database.get_channel_messages_for_day')
        self.mock_get_channel_messages_for_day = self.get_channel_messages_for_day_patcher.start()
        self.mock_get_channel_messages_for_day.return_value = [
            {
                'author_name': 'Test User',
                'content': 'Test message 1',
                'created_at': datetime.now(),
                'is_bot': False,
                'is_command': False
            },
            {
                'author_name': 'Another User',
                'content': 'Test message 2',
                'created_at': datetime.now(),
                'is_bot': False,
                'is_command': False
            }
        ]

    def tearDown(self):
        """Clean up after tests"""
        # Restore original client
        bot.client = self.original_client

        # Stop patchers
        self.config_patcher.stop()
        self.call_llm_api_patcher.stop()
        self.call_llm_for_summary_patcher.stop()
        self.store_message_patcher.stop()
        self.get_channel_messages_for_day_patcher.stop()

    def test_bot_command_in_bot_talk_channel(self):
        """Test /bot command in bot-talk channel"""
        # Create mock message in bot-talk channel
        channel = MagicMock()
        channel.name = "bot-talk"
        channel.id = "bot_talk_channel_id"
        channel.send = AsyncMock()

        message = MockMessage(
            content="/bot test query",
            channel=channel
        )

        # Process the message
        import asyncio
        asyncio.run(bot.on_message(message))

        # Check if the bot responded
        channel.send.assert_called()
        self.mock_call_llm_api.assert_called_once_with("test query")

    def test_bot_command_in_other_channel(self):
        """Test /bot command in a channel other than bot-talk"""
        # Create mock message in another channel
        channel = MagicMock()
        channel.name = "general"
        channel.id = "general_channel_id"
        channel.send = AsyncMock()

        message = MockMessage(
            content="/bot test query",
            channel=channel
        )

        # Process the message
        import asyncio
        asyncio.run(bot.on_message(message))

        # Check that the bot did not respond
        channel.send.assert_not_called()
        self.mock_call_llm_api.assert_not_called()

    def test_sum_day_command_in_bot_talk_channel(self):
        """Test /sum-day command in bot-talk channel"""
        # Create mock message in bot-talk channel
        channel = MagicMock()
        channel.name = "bot-talk"
        channel.id = "bot_talk_channel_id"
        channel.send = AsyncMock()

        message = MockMessage(
            content="/sum-day",
            channel=channel
        )

        # Process the message
        import asyncio
        asyncio.run(bot.on_message(message))

        # Check if the bot responded
        channel.send.assert_called()
        self.mock_call_llm_for_summary.assert_called_once()

    def test_sum_day_command_in_other_channel(self):
        """Test /sum-day command in a channel other than bot-talk"""
        # Create mock message in another channel
        channel = MagicMock()
        channel.name = "general"
        channel.id = "general_channel_id"
        channel.send = AsyncMock()

        message = MockMessage(
            content="/sum-day",
            channel=channel
        )

        # Process the message
        import asyncio
        asyncio.run(bot.on_message(message))

        # Check if the bot responded (should respond in any channel)
        channel.send.assert_called()
        self.mock_call_llm_for_summary.assert_called_once()

def main():
    """Run all tests"""
    logger.info("Starting command tests...")
    import asyncio

    # Create a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run the tests
    unittest.main()

if __name__ == "__main__":
    main()
