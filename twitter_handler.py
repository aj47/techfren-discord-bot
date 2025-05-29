"""
Twitter/X.com handler module for the Discord bot.
Handles all Twitter/X.com URL processing logic.
"""

import asyncio
import json
from typing import Optional, Dict, Any
from logging_config import logger
from apify_handler import scrape_twitter_content, is_twitter_url, extract_tweet_id
from firecrawl_handler import scrape_url_content
from llm_handler import summarize_scraped_content
import database
import config


async def process_twitter_url(message_id: str, url: str) -> bool:
    """
    Process a Twitter/X.com URL by scraping content and updating the database.
    
    Args:
        message_id (str): The ID of the message containing the URL
        url (str): The Twitter/X.com URL to process
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        logger.info(f"Processing Twitter/X.com URL {url} from message {message_id}")
        
        # Validate if the URL contains a tweet ID
        tweet_id = extract_tweet_id(url)
        if not tweet_id:
            logger.warning(f"URL appears to be Twitter/X.com but doesn't contain a valid tweet ID: {url}")
            scraped_result = await _handle_non_tweet_twitter_url(url)
        else:
            scraped_result = await _scrape_tweet_content(url)
        
        if not scraped_result:
            logger.warning(f"Failed to scrape content from Twitter/X.com URL: {url}")
            return False
            
        # Extract markdown content
        markdown_content = scraped_result.get('markdown') if isinstance(scraped_result, dict) else scraped_result
        
        # Summarize and update database
        return await _process_scraped_content(message_id, url, markdown_content)
        
    except Exception as e:
        logger.error(f"Error processing Twitter/X.com URL {url} from message {message_id}: {str(e)}", exc_info=True)
        return False


async def _handle_non_tweet_twitter_url(url: str) -> Optional[Dict[str, Any]]:
    """
    Handle Twitter/X.com URLs that don't contain a tweet ID.
    
    Args:
        url (str): The Twitter/X.com URL without a tweet ID
        
    Returns:
        Optional[Dict[str, Any]]: Scraped result or None if failed
    """
    # For base Twitter/X.com URLs, create a simple markdown response
    if url.lower() in ["https://x.com", "https://twitter.com", "http://x.com", "http://twitter.com"]:
        logger.info(f"Handling base Twitter/X.com URL with custom response: {url}")
        return {
            "markdown": f"# Twitter/X.com\n\nThis is the main page of Twitter/X.com: {url}"
        }
    else:
        # For other Twitter/X.com URLs without a tweet ID, try Firecrawl
        return await scrape_url_content(url)


async def _scrape_tweet_content(url: str) -> Optional[Dict[str, Any]]:
    """
    Scrape content from a Twitter/X.com URL with a tweet ID.
    
    Args:
        url (str): The Twitter/X.com URL with a tweet ID
        
    Returns:
        Optional[Dict[str, Any]]: Scraped result or None if failed
    """
    # Check if Apify API token is configured
    if not hasattr(config, 'apify_api_token') or not config.apify_api_token:
        logger.warning("Apify API token not found in config.py or is empty, falling back to Firecrawl")
        return await scrape_url_content(url)
    
    # Use Apify to scrape Twitter/X.com content
    scraped_result = await scrape_twitter_content(url)
    
    # If Apify scraping fails, fall back to Firecrawl
    if not scraped_result:
        logger.warning(f"Failed to scrape Twitter/X.com content with Apify, falling back to Firecrawl: {url}")
        return await scrape_url_content(url)
    else:
        logger.info(f"Successfully scraped Twitter/X.com content with Apify: {url}")
        return scraped_result


async def _process_scraped_content(message_id: str, url: str, markdown_content: str) -> bool:
    """
    Process scraped content by summarizing it and updating the database.
    
    Args:
        message_id (str): The ID of the message containing the URL
        url (str): The URL that was scraped
        markdown_content (str): The scraped content in markdown format
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        # Summarize the scraped content
        scraped_data = await summarize_scraped_content(markdown_content, url)
        if not scraped_data:
            logger.warning(f"Failed to summarize content from URL: {url}")
            return False

        # Convert key points to JSON string
        key_points_json = json.dumps(scraped_data.get('key_points', []))

        # Update the message in the database with the scraped data
        success = await database.update_message_with_scraped_data(
            message_id,
            url,
            scraped_data.get('summary', ''),
            key_points_json
        )

        if success:
            logger.info(f"Successfully processed URL {url} from message {message_id}")
            return True
        else:
            logger.warning(f"Failed to update message {message_id} with scraped data")
            return False
            
    except Exception as e:
        logger.error(f"Error processing scraped content for URL {url}: {str(e)}", exc_info=True)
        return False
