#!/usr/bin/env python3
"""
Test script to verify URL routing logic for X.com/Twitter URLs.
This script tests the URL detection and routing without requiring the full bot setup.
"""

import asyncio
import logging
import sys
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger('test_url_routing')

async def is_twitter_url(url: str) -> bool:
    """
    Check if a URL is from Twitter/X.com.
    This is a copy of the function from apify_handler.py to test independently.
    """
    # More specific pattern to match Twitter/X.com domains
    return bool(re.search(r'(?:^https?://(?:www\.)?(?:twitter\.com|x\.com))|(?://(?:www\.)?(?:twitter\.com|x\.com))', url))

def extract_tweet_id(url: str) -> str:
    """
    Extract the tweet ID from a Twitter/X.com URL.
    This is a copy of the function from apify_handler.py to test independently.
    """
    try:
        # Pattern to match tweet IDs in Twitter/X.com URLs
        pattern = r'(?:twitter\.com|x\.com)/\w+/status/(\d+)'
        match = re.search(pattern, url)
        
        if match:
            return match.group(1)
        
        return None
    except Exception as e:
        logger.error(f"Error extracting tweet ID from URL {url}: {str(e)}")
        return None

async def test_url_routing(url: str):
    """
    Test the URL routing logic for a given URL.
    """
    logger.info(f"Testing URL: {url}")
    
    # Check if the URL is from Twitter/X.com
    is_twitter = await is_twitter_url(url)
    logger.info(f"is_twitter_url result: {is_twitter}")
    
    if is_twitter:
        # Extract tweet ID
        tweet_id = extract_tweet_id(url)
        logger.info(f"extract_tweet_id result: {tweet_id}")
        
        if tweet_id:
            logger.info(f"✅ URL should be routed to APIFY: {url}")
            logger.info(f"   Tweet ID: {tweet_id}")
        else:
            logger.info(f"⚠️  URL should be routed to FIRECRAWL (no tweet ID): {url}")
    else:
        logger.info(f"ℹ️  URL should be routed to FIRECRAWL (not Twitter/X): {url}")
    
    return is_twitter, extract_tweet_id(url) if is_twitter else None

async def main():
    """Run the test function."""
    logger.info("Starting URL routing test...")
    
    # Test URLs
    test_urls = [
        "https://x.com/gumloop_ai/status/1926009793442885867?t=c0tWW2Jy_xF19WDr_UkvTA&s=19",
        "https://twitter.com/user/status/1234567890",
        "https://x.com/user/status/9876543210",
        "https://x.com/user",
        "https://twitter.com",
        "https://example.com/not/twitter",
        "https://google.com"
    ]
    
    for url in test_urls:
        await test_url_routing(url)
        print("-" * 80)
    
    logger.info("URL routing test completed.")

if __name__ == "__main__":
    # Run the main function
    asyncio.run(main())
