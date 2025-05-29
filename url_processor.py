"""
URL processor module for the Discord bot.
Handles general URL processing logic.
"""

import asyncio
import json
import re
from typing import Optional
from logging_config import logger
from firecrawl_handler import scrape_url_content
from llm_handler import summarize_scraped_content
from twitter_handler import process_twitter_url
from apify_handler import is_twitter_url
import database


async def process_url(message_id: str, url: str) -> bool:
    """
    Process a URL found in a message by scraping its content, summarizing it,
    and updating the message in the database with the scraped data.

    Args:
        message_id (str): The ID of the message containing the URL
        url (str): The URL to process
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        logger.info(f"Processing URL {url} from message {message_id}")

        # Check if the URL is from Twitter/X.com
        if await is_twitter_url(url):
            return await process_twitter_url(message_id, url)
        else:
            return await _process_general_url(message_id, url)

    except Exception as e:
        logger.error(f"Error processing URL {url} from message {message_id}: {str(e)}", exc_info=True)
        return False


async def _process_general_url(message_id: str, url: str) -> bool:
    """
    Process a general (non-Twitter) URL.
    
    Args:
        message_id (str): The ID of the message containing the URL
        url (str): The URL to process
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        # For non-Twitter/X.com URLs, use Firecrawl
        scraped_result = await scrape_url_content(url)
        
        # Check if scraping was successful
        if not scraped_result:
            logger.warning(f"Failed to scrape content from URL: {url}")
            return False

        # Summarize the scraped content
        scraped_data = await summarize_scraped_content(scraped_result, url)
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
        logger.error(f"Error processing general URL {url}: {str(e)}", exc_info=True)
        return False


def extract_urls_from_message(content: str) -> list[str]:
    """
    Extract URLs from message content.
    
    Args:
        content (str): The message content
        
    Returns:
        list[str]: List of URLs found in the message
    """
    # URL regex pattern - capture the full URL including path and query parameters
    url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?'
    return re.findall(url_pattern, content)
