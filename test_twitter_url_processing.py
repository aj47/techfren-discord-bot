#!/usr/bin/env python3
"""
Test script for Twitter/X.com URL processing in the Discord bot.
This script tests the entire flow from URL detection to content scraping.
"""

import asyncio
import logging
import sys
from pprint import pprint

# Import the necessary modules from the bot
from apify_handler import scrape_twitter_content, is_twitter_url
from firecrawl_handler import scrape_url_content
import config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger('test_twitter_url_processing')

async def test_process_url(url: str):
    """
    Test the URL processing flow similar to how it's done in the bot.
    
    Args:
        url (str): The URL to process
    """
    try:
        logger.info(f"Processing URL: {url}")
        
        # Check if the URL is from Twitter/X.com
        if await is_twitter_url(url):
            logger.info(f"Detected Twitter/X.com URL: {url}")
            
            # Validate if the URL contains a tweet ID (status)
            from apify_handler import extract_tweet_id
            tweet_id = extract_tweet_id(url)
            if not tweet_id:
                logger.warning(f"URL appears to be Twitter/X.com but doesn't contain a valid tweet ID: {url}")
                
                # For base Twitter/X.com URLs without a tweet ID, create a simple markdown response
                if url.lower() in ["https://x.com", "https://twitter.com", "http://x.com", "http://twitter.com"]:
                    logger.info(f"Handling base Twitter/X.com URL with custom response: {url}")
                    scraped_result = {
                        "markdown": f"# Twitter/X.com\n\nThis is the main page of Twitter/X.com: {url}"
                    }
                else:
                    # For other Twitter/X.com URLs without a tweet ID, try Firecrawl
                    logger.info(f"URL without tweet ID, using Firecrawl: {url}")
                    scraped_result = await scrape_url_content(url)
            else:
                # Check if Apify API token is configured
                if not hasattr(config, 'apify_api_token') or not config.apify_api_token:
                    logger.warning("Apify API token not found in config.py or is empty, falling back to Firecrawl")
                    scraped_result = await scrape_url_content(url)
                else:
                    # Use Apify to scrape Twitter/X.com content
                    logger.info(f"Using Apify to scrape Twitter/X.com content: {url}")
                    scraped_result = await scrape_twitter_content(url)
                    
                    # If Apify scraping fails, fall back to Firecrawl
                    if not scraped_result:
                        logger.warning(f"Failed to scrape Twitter/X.com content with Apify, falling back to Firecrawl: {url}")
                        scraped_result = await scrape_url_content(url)
                    else:
                        logger.info(f"Successfully scraped Twitter/X.com content with Apify: {url}")
                        # Extract markdown content from the scraped result
                        markdown_content = scraped_result.get('markdown')
                        
                        # Print the markdown content
                        print("\n--- Markdown Content ---")
                        print(markdown_content)
                        
                        return True
        else:
            # For non-Twitter/X.com URLs, use Firecrawl
            logger.info(f"Non-Twitter/X.com URL, using Firecrawl: {url}")
            scraped_result = await scrape_url_content(url)
            
        # Check if scraping was successful
        if not scraped_result:
            logger.warning(f"Failed to scrape content from URL: {url}")
            return False
            
        return True
            
    except Exception as e:
        logger.error(f"Error processing URL {url}: {str(e)}", exc_info=True)
        return False

async def main():
    """Run the test function."""
    logger.info("Starting Twitter/X.com URL processing test...")
    
    # Test URL
    url = "https://x.com/cline/status/1925002086405832987"
    
    # Process the URL
    success = await test_process_url(url)
    
    if success:
        logger.info("Test completed successfully!")
    else:
        logger.error("Test failed!")
    
    logger.info("Twitter/X.com URL processing test completed.")

if __name__ == "__main__":
    # Run the main function
    asyncio.run(main())
