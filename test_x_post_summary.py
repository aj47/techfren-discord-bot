#!/usr/bin/env python3
"""
Test suite for X post summarization functionality in bot.py.
Tests the handle_x_post_summary function with proper mocking.
"""

import pytest
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import discord

# Set up logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('test_x_post_summary')


class MockMessage:
    """Mock Discord message for testing."""
    def __init__(self, content: str, message_id: str = "123456789"):
        self.content = content
        self.id = message_id
        self.author = MagicMock()
        self.author.id = "user123"
        self.author.bot = False
        self.channel = MagicMock()
        self.guild = MagicMock()
        self.reply = AsyncMock()


class MockProcessingMessage:
    """Mock processing message that can be edited."""
    def __init__(self):
        self.content = "🔄 Scraping and summarizing X post..."
        self.edit = AsyncMock()


@pytest.mark.asyncio
async def test_handle_x_post_summary_with_valid_x_url():
    """Test that handle_x_post_summary processes a valid X URL."""
    # Import the function to test
    from bot import handle_x_post_summary
    
    # Create a mock message with an X URL
    message = MockMessage("Check out this tweet: https://x.com/user/status/1234567890123456789")
    processing_msg = MockProcessingMessage()
    message.reply.return_value = processing_msg
    
    # Mock the dependencies
    with patch('bot.is_twitter_url', new_callable=AsyncMock) as mock_is_twitter:
        with patch('bot.scrape_twitter_content', new_callable=AsyncMock) as mock_scrape:
            with patch('bot.summarize_scraped_content', new_callable=AsyncMock) as mock_summarize:
                with patch('bot.database.update_message_with_scraped_data', new_callable=AsyncMock) as mock_db:
                    with patch('bot.config') as mock_config:
                        # Set up mocks
                        mock_is_twitter.return_value = True
                        mock_config.apify_api_token = "test_token"
                        
                        mock_scrape.return_value = {
                            'markdown': '# Test Tweet\n\nThis is a test tweet content.'
                        }
                        
                        mock_summarize.return_value = {
                            'summary': 'This is a summary of the tweet.',
                            'key_points': ['Point 1', 'Point 2', 'Point 3']
                        }
                        
                        mock_db.return_value = True
                        
                        # Call the function
                        result = await handle_x_post_summary(message)
                        
                        # Assertions
                        assert result is True
                        message.reply.assert_called_once_with("🔄 Scraping and summarizing X post...")
                        mock_scrape.assert_called_once()
                        mock_summarize.assert_called_once()
                        processing_msg.edit.assert_called_once()
                        
                        # Check that the edit was called with a summary
                        edit_call_args = processing_msg.edit.call_args
                        assert 'X Post Summary' in edit_call_args.kwargs['content']
                        assert 'This is a summary of the tweet.' in edit_call_args.kwargs['content']


@pytest.mark.asyncio
async def test_handle_x_post_summary_with_no_url():
    """Test that handle_x_post_summary returns False when no URL is present."""
    from bot import handle_x_post_summary
    
    message = MockMessage("This is a message without any URLs")
    
    result = await handle_x_post_summary(message)
    
    assert result is False
    message.reply.assert_not_called()


@pytest.mark.asyncio
async def test_handle_x_post_summary_with_non_x_url():
    """Test that handle_x_post_summary returns False when URL is not an X/Twitter URL."""
    from bot import handle_x_post_summary
    
    message = MockMessage("Check out this link: https://example.com/article")
    
    with patch('bot.is_twitter_url', new_callable=AsyncMock) as mock_is_twitter:
        mock_is_twitter.return_value = False
        
        result = await handle_x_post_summary(message)
        
        assert result is False
        message.reply.assert_not_called()


@pytest.mark.asyncio
async def test_handle_x_post_summary_with_invalid_tweet_id():
    """Test that handle_x_post_summary handles URLs without valid tweet IDs."""
    from bot import handle_x_post_summary
    
    message = MockMessage("Check out X: https://x.com")
    processing_msg = MockProcessingMessage()
    message.reply.return_value = processing_msg
    
    with patch('bot.is_twitter_url', new_callable=AsyncMock) as mock_is_twitter:
        with patch('apify_handler.extract_tweet_id') as mock_extract:
            mock_is_twitter.return_value = True
            mock_extract.return_value = None
            
            result = await handle_x_post_summary(message)
            
            assert result is True
            processing_msg.edit.assert_called_once()
            edit_call_args = processing_msg.edit.call_args
            assert "doesn't contain a valid tweet ID" in edit_call_args.kwargs['content']


@pytest.mark.asyncio
async def test_handle_x_post_summary_without_apify_token():
    """Test that handle_x_post_summary handles missing Apify API token."""
    from bot import handle_x_post_summary
    
    message = MockMessage("Check out this tweet: https://x.com/user/status/1234567890123456789")
    processing_msg = MockProcessingMessage()
    message.reply.return_value = processing_msg
    
    with patch('bot.is_twitter_url', new_callable=AsyncMock) as mock_is_twitter:
        with patch('bot.config') as mock_config:
            mock_is_twitter.return_value = True
            mock_config.apify_api_token = None
            
            result = await handle_x_post_summary(message)
            
            assert result is True
            processing_msg.edit.assert_called_once()
            edit_call_args = processing_msg.edit.call_args
            assert "Apify API token not configured" in edit_call_args.kwargs['content']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

