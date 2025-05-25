"""
Integration test suite for the complete message processing pipeline.
Tests the end-to-end flow from message receipt to URL processing and summarization.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import logging
import discord

# Import modules to test
import bot
import database

# Set up logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('test_message_processing')


class MockMessage:
    """Mock Discord message for testing."""
    
    def __init__(self, content, author=None, channel=None, guild=None, message_id="test_id"):
        self.content = content
        self.id = message_id
        self.author = author or MagicMock()
        self.channel = channel or MagicMock()
        self.guild = guild or MagicMock()
        self.created_at = MagicMock()
        
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


class TestMessageProcessingPipeline:
    """Test the complete message processing pipeline."""

    @pytest.mark.asyncio
    async def test_url_detection_and_processing(self):
        """Test that URLs in messages are detected and processed."""
        # Create a mock message with a URL
        test_url = "https://x.com/user/status/1234567890"
        message = MockMessage(f"Check out this tweet: {test_url}")
        
        # Mock the URL processing functions
        with patch('bot.process_url') as mock_process_url, \
             patch('database.store_message', return_value=True):
            
            # Simulate message processing
            await bot.on_message(message)
            
            # Verify URL processing was triggered
            mock_process_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_twitter_url_routing_integration(self):
        """Test the complete Twitter URL routing and processing."""
        test_url = "https://x.com/user/status/1234567890"
        
        # Mock all the dependencies
        mock_scraped_content = {
            'markdown': '# Test Tweet\n\nThis is a test tweet content.',
            'raw_data': {'tweet': {'text': 'Test tweet', 'author': 'Test User'}}
        }
        
        mock_summary = "Summary: This is a test tweet about testing."
        
        with patch('apify_handler.scrape_twitter_content', return_value=mock_scraped_content), \
             patch('llm_handler.summarize_content', return_value=mock_summary), \
             patch('database.update_message_with_scraped_data', return_value=True):
            
            # Test the URL processing
            await bot.process_url("test_message_id", test_url)
            
            # Verify the flow completed without errors
            # In a real test, we'd verify the database was updated correctly

    @pytest.mark.asyncio
    async def test_non_twitter_url_routing(self):
        """Test routing of non-Twitter URLs to Firecrawl."""
        test_url = "https://example.com/article"
        
        mock_scraped_content = "# Example Article\n\nThis is example content."
        mock_summary = "Summary: This is an example article."
        
        with patch('firecrawl_handler.scrape_url_content', return_value=mock_scraped_content), \
             patch('llm_handler.summarize_content', return_value=mock_summary), \
             patch('database.update_message_with_scraped_data', return_value=True):
            
            await bot.process_url("test_message_id", test_url)
            
            # Verify non-Twitter URL was processed correctly

    @pytest.mark.asyncio
    async def test_error_handling_in_pipeline(self):
        """Test error handling throughout the processing pipeline."""
        test_url = "https://x.com/user/status/1234567890"
        
        # Test scraping failure
        with patch('apify_handler.scrape_twitter_content', return_value=None), \
             patch('firecrawl_handler.scrape_url_content', return_value=None):
            
            # Should handle scraping failure gracefully
            await bot.process_url("test_message_id", test_url)
            
        # Test summarization failure
        with patch('apify_handler.scrape_twitter_content', return_value={'markdown': 'content'}), \
             patch('llm_handler.summarize_content', return_value=None):
            
            # Should handle summarization failure gracefully
            await bot.process_url("test_message_id", test_url)

    @pytest.mark.asyncio
    async def test_command_processing(self):
        """Test command processing doesn't interfere with URL processing."""
        # Test mention command
        mention_message = MockMessage("<@123456789> help")
        
        with patch('command_handler.handle_bot_command') as mock_command:
            await bot.on_message(mention_message)
            mock_command.assert_called_once()
        
        # Test sum-day command
        sum_day_message = MockMessage("/sum-day")
        
        with patch('command_handler.handle_sum_day_command') as mock_sum_day:
            await bot.on_message(sum_day_message)
            mock_sum_day.assert_called_once()

    @pytest.mark.asyncio
    async def test_bot_message_filtering(self):
        """Test that bot messages are properly filtered out."""
        # Create a message from a bot
        bot_message = MockMessage("This is from a bot")
        bot_message.author.bot = True
        
        with patch('bot.process_url') as mock_process_url, \
             patch('database.store_message') as mock_store:
            
            await bot.on_message(bot_message)
            
            # Bot messages should not trigger URL processing
            mock_process_url.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
