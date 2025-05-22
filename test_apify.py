#!/usr/bin/env python3
"""
Test script for the Apify handler.
Tests Twitter/X.com URL scraping using the Apify API.
"""

import asyncio
import logging
import sys
from pprint import pprint

# Import the apify_handler module
import apify_handler

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger('test_apify')

async def test_fetch_tweet():
    """Test the fetch_tweet function with a specific URL."""
    url = "https://x.com/cline/status/1925002086405832987"
    logger.info(f"Testing fetch_tweet with URL: {url}")
    
    # Call the fetch_tweet function
    tweet_data = await apify_handler.fetch_tweet(url)
    
    if tweet_data:
        logger.info("Successfully fetched tweet data!")
        # Print a summary of the tweet data
        print("\n--- Tweet Data Summary ---")
        if 'text' in tweet_data:
            print(f"Tweet Text: {tweet_data['text']}")
        if 'user' in tweet_data and 'name' in tweet_data['user']:
            print(f"Author: {tweet_data['user']['name']} (@{tweet_data['user'].get('screen_name', '')})")
        
        # Check for video
        video_url = apify_handler.extract_video_url(tweet_data)
        if video_url:
            print(f"Video URL: {video_url}")
        
        # Print the full data structure for debugging
        print("\n--- Full Tweet Data ---")
        pprint(tweet_data)
        
        return True
    else:
        logger.error("Failed to fetch tweet data.")
        return False

async def test_scrape_twitter_content():
    """Test the scrape_twitter_content function with a specific URL."""
    url = "https://x.com/cline/status/1925002086405832987"
    logger.info(f"Testing scrape_twitter_content with URL: {url}")
    
    # Call the scrape_twitter_content function
    content = await apify_handler.scrape_twitter_content(url)
    
    if content:
        logger.info("Successfully scraped Twitter content!")
        # Print the markdown content
        print("\n--- Markdown Content ---")
        print(content['markdown'])
        
        return True
    else:
        logger.error("Failed to scrape Twitter content.")
        return False

async def main():
    """Run the test functions."""
    logger.info("Starting Apify handler tests...")
    
    # Test fetch_tweet
    tweet_result = await test_fetch_tweet()
    
    # Test scrape_twitter_content if fetch_tweet was successful
    if tweet_result:
        await test_scrape_twitter_content()
    
    logger.info("Apify handler tests completed.")

if __name__ == "__main__":
    # Run the main function
    asyncio.run(main())
