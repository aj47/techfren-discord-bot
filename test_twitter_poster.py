#!/usr/bin/env python3
"""
Test suite for Twitter/X posting functionality.
Tests the twitter_poster module with proper mocking to avoid API dependencies.
"""

import pytest
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch, Mock

# Set up logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('test_twitter_poster')


class TestIsTwitterPostingEnabled:
    """Test the is_twitter_posting_enabled function."""

    @patch('twitter_poster.config')
    def test_disabled_when_auto_tweet_false(self, mock_config):
        """Test that posting is disabled when auto_tweet_enabled is False."""
        mock_config.twitter_auto_tweet_enabled = False
        mock_config.twitter_consumer_key = 'key'
        mock_config.twitter_consumer_secret = 'secret'
        mock_config.twitter_access_token = 'token'
        mock_config.twitter_access_token_secret = 'token_secret'
        
        # Reset the cached client
        import twitter_poster
        twitter_poster._twitter_client = None
        
        result = twitter_poster.is_twitter_posting_enabled()
        assert result is False

    @patch('twitter_poster.config')
    def test_disabled_when_credentials_missing(self, mock_config):
        """Test that posting is disabled when credentials are missing."""
        mock_config.twitter_auto_tweet_enabled = True
        mock_config.twitter_consumer_key = None
        mock_config.twitter_consumer_secret = None
        mock_config.twitter_access_token = None
        mock_config.twitter_access_token_secret = None
        
        import twitter_poster
        twitter_poster._twitter_client = None
        
        result = twitter_poster.is_twitter_posting_enabled()
        assert result is False

    @patch('twitter_poster.config')
    def test_disabled_when_partial_credentials(self, mock_config):
        """Test that posting is disabled when only some credentials are set."""
        mock_config.twitter_auto_tweet_enabled = True
        mock_config.twitter_consumer_key = 'key'
        mock_config.twitter_consumer_secret = None
        mock_config.twitter_access_token = 'token'
        mock_config.twitter_access_token_secret = None
        
        import twitter_poster
        twitter_poster._twitter_client = None
        
        result = twitter_poster.is_twitter_posting_enabled()
        assert result is False


class TestGetTwitterClient:
    """Test the _get_twitter_client function."""

    @patch('twitter_poster.config')
    def test_returns_none_when_no_credentials(self, mock_config):
        """Test that None is returned when credentials are not set."""
        mock_config.twitter_consumer_key = None
        mock_config.twitter_consumer_secret = None
        mock_config.twitter_access_token = None
        mock_config.twitter_access_token_secret = None
        
        import twitter_poster
        twitter_poster._twitter_client = None
        
        result = twitter_poster._get_twitter_client()
        assert result is None

    @patch('twitter_poster.config')
    @patch('tweepy.Client')
    def test_creates_client_with_credentials(self, mock_client_class, mock_config):
        """Test that client is created when credentials are provided."""
        mock_config.twitter_consumer_key = 'key'
        mock_config.twitter_consumer_secret = 'secret'
        mock_config.twitter_access_token = 'token'
        mock_config.twitter_access_token_secret = 'token_secret'
        
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        import twitter_poster
        twitter_poster._twitter_client = None
        
        result = twitter_poster._get_twitter_client()
        
        assert result is mock_client
        mock_client_class.assert_called_once_with(
            consumer_key='key',
            consumer_secret='secret',
            access_token='token',
            access_token_secret='token_secret'
        )


class TestPostTweet:
    """Test the post_tweet function."""

    @pytest.mark.asyncio
    @patch('twitter_poster._get_twitter_client')
    async def test_post_tweet_no_client(self, mock_get_client):
        """Test that post_tweet returns None when client is not available."""
        mock_get_client.return_value = None
        
        import twitter_poster
        result = await twitter_poster.post_tweet("Hello, world!")
        
        assert result is None

    @pytest.mark.asyncio
    @patch('twitter_poster._get_twitter_client')
    async def test_post_tweet_success(self, mock_get_client):
        """Test successful tweet posting."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = {'id': '123456789', 'text': 'Hello, world!'}
        mock_client.create_tweet.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        import twitter_poster
        result = await twitter_poster.post_tweet("Hello, world!")
        
        assert result is not None
        assert result['id'] == '123456789'
        assert result['text'] == 'Hello, world!'

    @pytest.mark.asyncio
    @patch('twitter_poster._get_twitter_client')
    async def test_post_tweet_truncates_long_text(self, mock_get_client):
        """Test that long tweets are truncated to 280 characters."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = {'id': '123', 'text': 'truncated'}
        mock_client.create_tweet.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        import twitter_poster
        long_text = "A" * 300  # 300 characters
        await twitter_poster.post_tweet(long_text)
        
        # Verify the text was truncated (277 chars + "...")
        call_args = mock_client.create_tweet.call_args
        text_arg = call_args[1]['text']
        assert len(text_arg) == 280
        assert text_arg.endswith("...")

