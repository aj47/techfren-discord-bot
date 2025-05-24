#!/usr/bin/env python3
"""
Automated test suite for URL routing logic in the Discord bot.
Tests the routing decisions for X.com/Twitter URLs vs other URLs.
This test suite is designed to run in CI/CD without external API dependencies.
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import patch, MagicMock

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the modules to test
from apify_handler import is_twitter_url, extract_tweet_id


class TestURLRouting:
    """Test URL routing logic for determining which scraping service to use."""

    @pytest.mark.asyncio
    async def test_problematic_url_from_issue(self):
        """Test the specific URL that was causing issues in the original bug report."""
        problematic_url = "https://x.com/gumloop_ai/status/1926009793442885867?t=c0tWW2Jy_xF19WDr_UkvTA&s=19"
        
        # This should be detected as Twitter/X URL
        is_twitter = await is_twitter_url(problematic_url)
        assert is_twitter is True, f"Failed to detect {problematic_url} as Twitter/X URL"
        
        # This should extract the tweet ID
        tweet_id = extract_tweet_id(problematic_url)
        assert tweet_id == "1926009793442885867", f"Failed to extract correct tweet ID from {problematic_url}"

    @pytest.mark.asyncio
    async def test_x_com_url_routing_decisions(self):
        """Test routing decisions for various X.com URL formats."""
        test_cases = [
            # Format: (url, should_be_twitter, expected_tweet_id, expected_service)
            
            # X.com URLs with tweet IDs - should route to Apify
            ("https://x.com/user/status/1234567890", True, "1234567890", "apify"),
            ("https://x.com/user/status/1234567890?s=20", True, "1234567890", "apify"),
            ("https://x.com/user/status/1234567890?t=abc&s=19", True, "1234567890", "apify"),
            ("https://x.com/elonmusk/status/1234567890123456789", True, "1234567890123456789", "apify"),
            
            # Twitter.com URLs with tweet IDs - should route to Apify  
            ("https://twitter.com/user/status/9876543210", True, "9876543210", "apify"),
            ("https://twitter.com/user/status/9876543210?ref_src=twsrc", True, "9876543210", "apify"),
            ("https://twitter.com/openai/status/1111111111111111111", True, "1111111111111111111", "apify"),
            
            # X.com URLs without tweet IDs - should route to Firecrawl
            ("https://x.com/user", True, None, "firecrawl"),
            ("https://x.com/user/followers", True, None, "firecrawl"),
            ("https://x.com/user/following", True, None, "firecrawl"),
            ("https://x.com", True, None, "firecrawl"),
            ("https://x.com/explore", True, None, "firecrawl"),
            
            # Twitter.com URLs without tweet IDs - should route to Firecrawl
            ("https://twitter.com/user", True, None, "firecrawl"),
            ("https://twitter.com", True, None, "firecrawl"),
            
            # Non-Twitter URLs - should route to Firecrawl
            ("https://example.com", False, None, "firecrawl"),
            ("https://github.com/user/repo", False, None, "firecrawl"),
            ("https://google.com", False, None, "firecrawl"),
            ("https://stackoverflow.com/questions/123", False, None, "firecrawl"),
            ("https://reddit.com/r/programming", False, None, "firecrawl"),
        ]
        
        for url, should_be_twitter, expected_tweet_id, expected_service in test_cases:
            # Test URL detection
            is_twitter = await is_twitter_url(url)
            assert is_twitter == should_be_twitter, f"URL detection failed for {url}"
            
            # Test tweet ID extraction
            tweet_id = extract_tweet_id(url)
            assert tweet_id == expected_tweet_id, f"Tweet ID extraction failed for {url}. Expected {expected_tweet_id}, got {tweet_id}"
            
            # Test routing logic
            if should_be_twitter and tweet_id:
                # Should route to Apify
                assert expected_service == "apify", f"URL {url} should route to Apify but expected {expected_service}"
            else:
                # Should route to Firecrawl
                assert expected_service == "firecrawl", f"URL {url} should route to Firecrawl but expected {expected_service}"

    @pytest.mark.asyncio
    async def test_edge_case_urls(self):
        """Test edge cases and malformed URLs."""
        edge_cases = [
            # Malformed URLs
            ("", False, None),
            ("not-a-url", False, None),
            ("https://", False, None),
            
            # URLs with x.com or twitter.com in path but not domain
            ("https://example.com/x.com/user/status/123", False, None),
            ("https://example.com/twitter.com/user/status/123", False, None),
            
            # URLs with similar domains
            ("https://x.co/user/status/123", False, None),
            ("https://twitter.co/user/status/123", False, None),
            ("https://x-com.example.com/user/status/123", False, None),
            
            # Case sensitivity
            ("https://X.COM/user/status/123", True, "123"),
            ("https://TWITTER.COM/user/status/123", True, "123"),
        ]
        
        for url, should_be_twitter, expected_tweet_id in edge_cases:
            is_twitter = await is_twitter_url(url)
            assert is_twitter == should_be_twitter, f"Edge case URL detection failed for {url}"
            
            tweet_id = extract_tweet_id(url)
            assert tweet_id == expected_tweet_id, f"Edge case tweet ID extraction failed for {url}"

    @pytest.mark.asyncio
    async def test_config_based_routing_logic(self):
        """Test routing logic based on configuration availability."""
        test_url = "https://x.com/user/status/1234567890"
        
        # Scenario 1: Both tokens available - should prefer Apify for X.com URLs
        with patch('config.apify_api_token', 'valid_apify_token'), \
             patch('config.firecrawl_api_key', 'valid_firecrawl_key'):
            
            is_twitter = await is_twitter_url(test_url)
            tweet_id = extract_tweet_id(test_url)
            
            assert is_twitter is True
            assert tweet_id == "1234567890"
            # With both tokens available and valid tweet ID, should route to Apify
            
        # Scenario 2: No Apify token - should fall back to Firecrawl
        with patch('config.apify_api_token', None), \
             patch('config.firecrawl_api_key', 'valid_firecrawl_key'):
            
            is_twitter = await is_twitter_url(test_url)
            tweet_id = extract_tweet_id(test_url)
            
            assert is_twitter is True
            assert tweet_id == "1234567890"
            # Without Apify token, should fall back to Firecrawl
            
        # Scenario 3: Empty Apify token - should fall back to Firecrawl
        with patch('config.apify_api_token', ''), \
             patch('config.firecrawl_api_key', 'valid_firecrawl_key'):
            
            is_twitter = await is_twitter_url(test_url)
            tweet_id = extract_tweet_id(test_url)
            
            assert is_twitter is True
            assert tweet_id == "1234567890"
            # With empty Apify token, should fall back to Firecrawl

    def test_tweet_id_extraction_patterns(self):
        """Test tweet ID extraction with various URL patterns."""
        test_patterns = [
            # Standard patterns
            ("https://x.com/user/status/1234567890", "1234567890"),
            ("https://twitter.com/user/status/9876543210", "9876543210"),
            
            # With query parameters
            ("https://x.com/user/status/1234567890?s=20", "1234567890"),
            ("https://x.com/user/status/1234567890?t=abc&s=19", "1234567890"),
            ("https://twitter.com/user/status/9876543210?ref_src=twsrc%5Etfw", "9876543210"),
            
            # With fragments
            ("https://x.com/user/status/1234567890#reply", "1234567890"),
            
            # Long tweet IDs
            ("https://x.com/user/status/1234567890123456789", "1234567890123456789"),
            
            # URLs without status - should return None
            ("https://x.com/user", None),
            ("https://x.com/user/followers", None),
            ("https://x.com", None),
            
            # Invalid patterns
            ("https://x.com/user/status/", None),
            ("https://x.com/user/status/abc", None),
            ("https://example.com/status/123", None),
        ]
        
        for url, expected_id in test_patterns:
            tweet_id = extract_tweet_id(url)
            assert tweet_id == expected_id, f"Tweet ID extraction failed for {url}. Expected {expected_id}, got {tweet_id}"


class TestURLRoutingRegression:
    """Regression tests to prevent the original issue from reoccurring."""
    
    @pytest.mark.asyncio
    async def test_original_issue_regression(self):
        """Ensure the original issue with X.com URLs is fixed and doesn't regress."""
        # The original problematic URL
        original_url = "https://x.com/gumloop_ai/status/1926009793442885867?t=c0tWW2Jy_xF19WDr_UkvTA&s=19"
        
        # This URL should be correctly identified and routed
        is_twitter = await is_twitter_url(original_url)
        tweet_id = extract_tweet_id(original_url)
        
        # Assertions that would have failed before the fix
        assert is_twitter is True, "X.com URL should be detected as Twitter/X URL"
        assert tweet_id == "1926009793442885867", "Tweet ID should be correctly extracted"
        assert tweet_id is not None, "Tweet ID should not be None for valid status URLs"
        
        # This URL should route to Apify (when token is available)
        # The routing logic should prefer Apify for X.com URLs with tweet IDs


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
