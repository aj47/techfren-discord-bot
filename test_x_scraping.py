#!/usr/bin/env python3
"""
Comprehensive test suite for X (Twitter) scraping functionality.
Tests the apify_handler module with proper mocking to avoid API dependencies.
"""

import pytest
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from typing import Dict, Any, Optional, List
import re

# Import the modules to test
import apify_handler
from apify_handler import (
    fetch_tweet,
    fetch_tweet_replies,
    extract_tweet_id,
    extract_video_url,
    scrape_twitter_content,
    format_as_markdown,
    is_twitter_url
)

# Set up logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('test_x_scraping')

class TestExtractTweetId:
    """Test the extract_tweet_id function."""

    def test_extract_tweet_id_valid_x_com(self):
        """Test extracting tweet ID from x.com URL."""
        url = "https://x.com/user/status/1234567890123456789"
        result = extract_tweet_id(url)
        assert result == "1234567890123456789"

    def test_extract_tweet_id_valid_twitter_com(self):
        """Test extracting tweet ID from twitter.com URL."""
        url = "https://twitter.com/user/status/9876543210987654321"
        result = extract_tweet_id(url)
        assert result == "9876543210987654321"

    def test_extract_tweet_id_with_query_params(self):
        """Test extracting tweet ID from URL with query parameters."""
        url = "https://x.com/user/status/1111111111111111111?s=20&t=abc123"
        result = extract_tweet_id(url)
        assert result == "1111111111111111111"

    def test_extract_tweet_id_no_status(self):
        """Test extracting tweet ID from URL without status."""
        url = "https://x.com/user"
        result = extract_tweet_id(url)
        assert result is None

    def test_extract_tweet_id_invalid_url(self):
        """Test extracting tweet ID from invalid URL."""
        url = "https://example.com/not/a/twitter/url"
        result = extract_tweet_id(url)
        assert result is None

    def test_extract_tweet_id_empty_string(self):
        """Test extracting tweet ID from empty string."""
        url = ""
        result = extract_tweet_id(url)
        assert result is None

    def test_extract_tweet_id_none(self):
        """Test extracting tweet ID from None."""
        # The function handles None gracefully and returns None
        result = extract_tweet_id(None)
        assert result is None

class TestIsTwitterUrl:
    """Test the is_twitter_url function."""

    @pytest.mark.asyncio
    async def test_is_twitter_url_x_com(self):
        """Test detecting x.com URLs."""
        url = "https://x.com/user/status/123"
        result = await is_twitter_url(url)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_twitter_url_twitter_com(self):
        """Test detecting twitter.com URLs."""
        url = "https://twitter.com/user/status/123"
        result = await is_twitter_url(url)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_twitter_url_with_www(self):
        """Test detecting URLs with www prefix."""
        url = "https://www.x.com/user/status/123"
        result = await is_twitter_url(url)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_twitter_url_non_twitter(self):
        """Test detecting non-Twitter URLs."""
        url = "https://example.com/some/path"
        result = await is_twitter_url(url)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_twitter_url_partial_match(self):
        """Test that partial matches don't trigger false positives."""
        url = "https://example.com/twitter.com/fake"
        result = await is_twitter_url(url)
        assert result is False

class TestExtractVideoUrl:
    """Test the extract_video_url function."""

    def test_extract_video_url_with_video(self):
        """Test extracting video URL from tweet data with video."""
        # Test with mediaDetails structure (actual implementation)
        tweet_data = {
            'mediaDetails': [
                {
                    'type': 'video',
                    'video_info': {
                        'variants': [
                            {'bitrate': 320000, 'url': 'https://video.twimg.com/low.mp4', 'content_type': 'video/mp4'},
                            {'bitrate': 832000, 'url': 'https://video.twimg.com/high.mp4', 'content_type': 'video/mp4'},
                            {'bitrate': 2176000, 'url': 'https://video.twimg.com/highest.mp4', 'content_type': 'video/mp4'}
                        ]
                    }
                }
            ]
        }
        result = extract_video_url(tweet_data)
        assert result == 'https://video.twimg.com/highest.mp4'

    def test_extract_video_url_no_video(self):
        """Test extracting video URL from tweet data without video."""
        tweet_data = {
            'text': 'Just a regular tweet without video'
        }
        result = extract_video_url(tweet_data)
        assert result is None

    def test_extract_video_url_empty_variants(self):
        """Test extracting video URL with empty variants."""
        tweet_data = {
            'mediaDetails': [
                {
                    'type': 'video',
                    'video_info': {
                        'variants': []
                    }
                }
            ]
        }
        result = extract_video_url(tweet_data)
        assert result is None

    def test_extract_video_url_no_extended_entities(self):
        """Test extracting video URL with no extended_entities."""
        tweet_data = {
            'text': 'Tweet without extended entities'
        }
        result = extract_video_url(tweet_data)
        assert result is None

class TestFormatAsMarkdown:
    """Test the format_as_markdown function."""

    def test_format_as_markdown_basic(self):
        """Test basic markdown formatting."""
        scraped_content = {
            'tweet': {
                'text': 'This is a test tweet',
                'author': 'Test User',
                'screen_name': 'testuser',
                'video_url': None
            },
            'replies': []
        }
        result = format_as_markdown(scraped_content)

        assert '# Tweet by @testuser (Test User)' in result
        assert 'This is a test tweet' in result

    def test_format_as_markdown_with_video(self):
        """Test markdown formatting with video."""
        scraped_content = {
            'tweet': {
                'text': 'Tweet with video',
                'author': 'Video User',
                'screen_name': 'videouser',
                'video_url': 'https://video.twimg.com/test.mp4'
            },
            'replies': []
        }
        result = format_as_markdown(scraped_content)

        assert 'Tweet with video' in result
        assert '# Tweet by @videouser (Video User)' in result
        assert 'https://video.twimg.com/test.mp4' in result

    def test_format_as_markdown_with_replies(self):
        """Test markdown formatting with replies."""
        scraped_content = {
            'tweet': {
                'text': 'Original tweet',
                'author': 'Original User',
                'screen_name': 'original',
                'video_url': None
            },
            'replies': [
                {
                    'text': 'First reply',
                    'author': 'Reply User 1'
                },
                {
                    'text': 'Second reply',
                    'author': 'Reply User 2'
                }
            ]
        }
        result = format_as_markdown(scraped_content)

        assert 'Original tweet' in result
        assert 'First reply' in result
        assert 'Second reply' in result
        assert 'Reply User 1:' in result
        assert 'Reply User 2:' in result

class TestFetchTweet:
    """Test the fetch_tweet function with mocked API calls."""

    @pytest.mark.asyncio
    @patch('apify_handler.config')
    @patch('apify_handler.ApifyClient')
    async def test_fetch_tweet_success(self, mock_apify_client, mock_config):
        """Test successful tweet fetching."""
        # Mock config
        mock_config.apify_api_token = "test_token"

        # Mock Apify client and response
        mock_client_instance = MagicMock()
        mock_apify_client.return_value = mock_client_instance

        # Mock the actor call chain
        mock_actor = MagicMock()
        mock_client_instance.actor.return_value = mock_actor

        # Mock run result
        mock_run = {"defaultDatasetId": "test_dataset_id"}
        mock_actor.call.return_value = mock_run

        # Mock dataset items
        mock_dataset = MagicMock()
        mock_client_instance.dataset.return_value = mock_dataset
        mock_dataset_items = MagicMock()
        mock_dataset_items.items = [
            {
                'text': 'Test tweet content',
                'user': {
                    'name': 'Test User',
                    'screen_name': 'testuser'
                },
                'id_str': '1234567890'
            }
        ]
        mock_dataset.list_items.return_value = mock_dataset_items

        # Test the function
        url = "https://x.com/testuser/status/1234567890"
        result = await fetch_tweet(url)

        # Assertions
        assert result is not None
        assert result['text'] == 'Test tweet content'
        assert result['user']['name'] == 'Test User'
        assert result['user']['screen_name'] == 'testuser'

        # Verify API calls
        mock_apify_client.assert_called_once_with(token="test_token")
        mock_client_instance.actor.assert_called_once_with("u6ppkMWAx2E2MpEuF")

    @pytest.mark.asyncio
    @patch('apify_handler.config')
    async def test_fetch_tweet_no_api_token(self, mock_config):
        """Test fetch_tweet with missing API token."""
        # Mock config without token
        mock_config.apify_api_token = None

        url = "https://x.com/testuser/status/1234567890"
        result = await fetch_tweet(url)

        assert result is None

    @pytest.mark.asyncio
    @patch('apify_handler.config')
    async def test_fetch_tweet_invalid_url(self, mock_config):
        """Test fetch_tweet with invalid URL (no tweet ID)."""
        # Mock config
        mock_config.apify_api_token = "test_token"

        url = "https://x.com/testuser"  # No status/tweet ID
        result = await fetch_tweet(url)

        assert result is None

    @pytest.mark.asyncio
    @patch('apify_handler.config')
    @patch('apify_handler.ApifyClient')
    async def test_fetch_tweet_no_data(self, mock_apify_client, mock_config):
        """Test fetch_tweet when no data is returned."""
        # Mock config
        mock_config.apify_api_token = "test_token"

        # Mock Apify client
        mock_client_instance = MagicMock()
        mock_apify_client.return_value = mock_client_instance

        # Mock empty dataset
        mock_actor = MagicMock()
        mock_client_instance.actor.return_value = mock_actor
        mock_run = {"defaultDatasetId": "test_dataset_id"}
        mock_actor.call.return_value = mock_run

        mock_dataset = MagicMock()
        mock_client_instance.dataset.return_value = mock_dataset
        mock_dataset_items = MagicMock()
        mock_dataset_items.items = []  # Empty result
        mock_dataset.list_items.return_value = mock_dataset_items

        url = "https://x.com/testuser/status/1234567890"
        result = await fetch_tweet(url)

        assert result is None

class TestFetchTweetReplies:
    """Test the fetch_tweet_replies function with mocked API calls."""

    @pytest.mark.asyncio
    @patch('apify_handler.config')
    @patch('apify_handler.ApifyClient')
    async def test_fetch_tweet_replies_success(self, mock_apify_client, mock_config):
        """Test successful tweet replies fetching."""
        # Mock config
        mock_config.apify_api_token = "test_token"

        # Mock Apify client
        mock_client_instance = MagicMock()
        mock_apify_client.return_value = mock_client_instance

        # Mock the actor call chain for replies
        mock_actor = MagicMock()
        mock_client_instance.actor.return_value = mock_actor

        mock_run = {"defaultDatasetId": "test_dataset_id"}
        mock_actor.call.return_value = mock_run

        # Mock dataset with replies
        mock_dataset = MagicMock()
        mock_client_instance.dataset.return_value = mock_dataset
        mock_dataset_items = MagicMock()
        mock_dataset_items.items = [
            {
                'text': 'First reply',
                'user': {'name': 'Reply User 1', 'screen_name': 'reply1'}
            },
            {
                'text': 'Second reply',
                'user': {'name': 'Reply User 2', 'screen_name': 'reply2'}
            }
        ]
        mock_dataset.list_items.return_value = mock_dataset_items

        url = "https://x.com/testuser/status/1234567890"
        result = await fetch_tweet_replies(url)

        # Assertions
        assert result is not None
        assert len(result) == 2
        assert result[0]['text'] == 'First reply'
        assert result[1]['text'] == 'Second reply'

        # Verify correct actor is called for replies
        mock_client_instance.actor.assert_called_once_with("qhybbvlFivx7AP0Oh")

    @pytest.mark.asyncio
    @patch('apify_handler.config')
    async def test_fetch_tweet_replies_no_token(self, mock_config):
        """Test fetch_tweet_replies with missing API token."""
        mock_config.apify_api_token = None

        url = "https://x.com/testuser/status/1234567890"
        result = await fetch_tweet_replies(url)

        assert result is None

class TestScrapeTwitterContent:
    """Test the main scrape_twitter_content function."""

    @pytest.mark.asyncio
    @patch('apify_handler.fetch_tweet_replies')
    @patch('apify_handler.fetch_tweet')
    async def test_scrape_twitter_content_success(self, mock_fetch_tweet, mock_fetch_replies):
        """Test successful Twitter content scraping."""
        # Mock tweet data
        mock_tweet_data = {
            'text': 'This is a test tweet with great content!',
            'user': {
                'name': 'Test User',
                'screen_name': 'testuser'
            },
            'mediaDetails': [
                {
                    'type': 'video',
                    'video_info': {
                        'variants': [
                            {'bitrate': 2176000, 'url': 'https://video.twimg.com/test.mp4', 'content_type': 'video/mp4'}
                        ]
                    }
                }
            ]
        }
        mock_fetch_tweet.return_value = mock_tweet_data

        # Mock replies data (using correct structure)
        mock_replies_data = [
            {
                'replyText': 'Great tweet!',
                'author': {'name': 'Reply User'}
            }
        ]
        mock_fetch_replies.return_value = mock_replies_data

        url = "https://x.com/testuser/status/1234567890"
        result = await scrape_twitter_content(url)

        # Assertions
        assert result is not None
        assert 'markdown' in result
        assert 'raw_data' in result
        assert 'This is a test tweet with great content!' in result['markdown']
        assert '# Tweet by @testuser (Test User)' in result['markdown']
        assert 'Great tweet!' in result['markdown']
        assert result['raw_data']['tweet']['text'] == 'This is a test tweet with great content!'
        assert result['raw_data']['tweet']['video_url'] == 'https://video.twimg.com/test.mp4'

    @pytest.mark.asyncio
    @patch('apify_handler.fetch_tweet')
    async def test_scrape_twitter_content_no_tweet(self, mock_fetch_tweet):
        """Test scraping when tweet fetch fails."""
        mock_fetch_tweet.return_value = None

        url = "https://x.com/testuser/status/1234567890"
        result = await scrape_twitter_content(url)

        assert result is None

    @pytest.mark.asyncio
    @patch('apify_handler.fetch_tweet_replies')
    @patch('apify_handler.fetch_tweet')
    async def test_scrape_twitter_content_no_replies(self, mock_fetch_tweet, mock_fetch_replies):
        """Test scraping when replies fetch fails."""
        # Mock tweet data
        mock_tweet_data = {
            'text': 'Tweet without replies',
            'user': {'name': 'Test User', 'screen_name': 'testuser'}
        }
        mock_fetch_tweet.return_value = mock_tweet_data
        mock_fetch_replies.return_value = None  # No replies

        url = "https://x.com/testuser/status/1234567890"
        result = await scrape_twitter_content(url)

        # Should still work with just the tweet
        assert result is not None
        assert 'markdown' in result
        assert 'Tweet without replies' in result['markdown']
        assert result['raw_data']['replies'] == []

# Integration test class
class TestXScrapingIntegration:
    """Integration tests for X scraping workflow."""

    @pytest.mark.asyncio
    async def test_url_detection_and_id_extraction_workflow(self):
        """Test the complete workflow of URL detection and ID extraction."""
        test_urls = [
            ("https://x.com/user/status/1234567890", True, "1234567890"),
            ("https://twitter.com/user/status/9876543210", True, "9876543210"),
            ("https://x.com/user/status/1111111111?s=20", True, "1111111111"),
            ("https://x.com/user", True, None),
            ("https://example.com/not/twitter", False, None),
        ]

        for url, should_be_twitter, expected_id in test_urls:
            # Test URL detection
            is_twitter = await is_twitter_url(url)
            assert is_twitter == should_be_twitter, f"URL detection failed for {url}"

            # Test ID extraction
            tweet_id = extract_tweet_id(url)
            assert tweet_id == expected_id, f"ID extraction failed for {url}"

    def test_video_extraction_edge_cases(self):
        """Test video extraction with various edge cases."""
        test_cases = [
            # No mediaDetails
            ({}, None),
            # Empty mediaDetails
            ({'mediaDetails': []}, None),
            # Non-video media
            ({'mediaDetails': [{'type': 'photo'}]}, None),
            # Video with no video_info
            ({'mediaDetails': [{'type': 'video'}]}, None),
            # Video with empty variants
            ({'mediaDetails': [{'type': 'video', 'video_info': {'variants': []}}]}, None),
            # Video with single variant (correct structure)
            ({'mediaDetails': [{'type': 'video', 'video_info': {'variants': [{'bitrate': 1000, 'url': 'test.mp4', 'content_type': 'video/mp4'}]}}]}, 'test.mp4'),
        ]

        for tweet_data, expected_url in test_cases:
            result = extract_video_url(tweet_data)
            assert result == expected_url, f"Video extraction failed for {tweet_data}"

if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
