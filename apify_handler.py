"""
Apify handler module for the Discord bot.
Handles scraping Twitter/X.com content using the Apify API.
"""

import asyncio
from apify_client import ApifyClient
import logging
from typing import Optional, Dict, List, Any, Union
import re
import json

# Import config for API token
import config

# Set up logging
logger = logging.getLogger('discord_bot.apify_handler')

async def fetch_tweet(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a tweet using Apify's Twitter Scraper.

    Args:
        url (str): The Twitter/X.com URL to scrape

    Returns:
        Optional[Dict[str, Any]]: The tweet data or None if scraping failed
    """
    try:
        logger.info(f"Fetching tweet from URL: {url}")

        # Check if Apify API token exists
        if not hasattr(config, 'apify_api_token') or not config.apify_api_token:
            logger.error("Apify API token not found in config.py or is empty")
            return None

        # Initialize the Apify client
        client = ApifyClient(token=config.apify_api_token)

        # Extract tweet ID from URL
        tweet_id = extract_tweet_id(url)
        if not tweet_id:
            logger.error(f"Could not extract tweet ID from URL: {url}")
            return None

        # Prepare the input for the Twitter Scraper actor
        input_data = {
            "startUrls": [url],
            "tweetsDesired": 1,
            "addUserInfo": True,
            "proxyConfig": {
                "useApifyProxy": True
            }
        }

        # Use a separate thread for the blocking API call
        loop = asyncio.get_event_loop()
        run = await loop.run_in_executor(
            None,
            lambda: client.actor("u6ppkMWAx2E2MpEuF").call(input=input_data)
        )

        # Get the dataset items
        dataset_items = await loop.run_in_executor(
            None,
            lambda: client.dataset(run["defaultDatasetId"]).list_items().items
        )

        if not dataset_items:
            logger.warning(f"No tweet data found for URL: {url}")
            return None

        # Get the first (and should be only) item
        tweet_data = dataset_items[0]
        
        # Log success
        logger.info(f"Successfully fetched tweet from URL: {url}")
        
        return tweet_data

    except Exception as e:
        logger.error(f"Error fetching tweet from URL {url}: {str(e)}", exc_info=True)
        return None

async def fetch_tweet_replies(url: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch replies to a tweet using Apify's Twitter Replies Scraper.

    Args:
        url (str): The Twitter/X.com URL to scrape replies from

    Returns:
        Optional[List[Dict[str, Any]]]: List of reply data or None if scraping failed
    """
    try:
        logger.info(f"Fetching tweet replies from URL: {url}")

        # Check if Apify API token exists
        if not hasattr(config, 'apify_api_token') or not config.apify_api_token:
            logger.error("Apify API token not found in config.py or is empty")
            return None

        # Initialize the Apify client
        client = ApifyClient(token=config.apify_api_token)

        # Prepare the input for the Twitter Replies Scraper actor
        input_data = {
            "postUrls": [url],
            "resultsLimit": 30
        }

        # Use a separate thread for the blocking API call
        loop = asyncio.get_event_loop()
        run = await loop.run_in_executor(
            None,
            lambda: client.actor("qhybbvlFivx7AP0Oh").call(run_input=input_data)
        )

        # Get the dataset items
        dataset_items = await loop.run_in_executor(
            None,
            lambda: client.dataset(run["defaultDatasetId"]).list_items().items
        )

        if not dataset_items:
            logger.warning(f"No reply data found for URL: {url}")
            return []

        # Log success
        logger.info(f"Successfully fetched {len(dataset_items)} replies from URL: {url}")
        
        return dataset_items

    except Exception as e:
        logger.error(f"Error fetching tweet replies from URL {url}: {str(e)}", exc_info=True)
        return None

def extract_tweet_id(url: str) -> Optional[str]:
    """
    Extract the tweet ID from a Twitter/X.com URL.

    Args:
        url (str): The Twitter/X.com URL

    Returns:
        Optional[str]: The tweet ID or None if extraction failed
    """
    try:
        # Pattern to match tweet IDs in Twitter/X.com URLs
        pattern = r'(?:twitter\.com|x\.com)/\w+/status/(\d+)'
        match = re.search(pattern, url)
        
        if match:
            return match.group(1)
        
        return None
    except Exception as e:
        logger.error(f"Error extracting tweet ID from URL {url}: {str(e)}", exc_info=True)
        return None

def extract_video_url(tweet_data: Dict[str, Any]) -> Optional[str]:
    """
    Extract the video URL from tweet data if it exists.

    Args:
        tweet_data (Dict[str, Any]): The tweet data

    Returns:
        Optional[str]: The video URL or None if no video exists
    """
    try:
        # Check if video exists in the tweet data
        if 'video' in tweet_data and tweet_data['video'] and 'variants' in tweet_data['video']:
            variants = tweet_data['video']['variants']
            
            # Prefer MP4 format
            mp4_variants = [v for v in variants if v.get('type') == 'video/mp4']
            
            if mp4_variants:
                # Sort by bitrate if available, otherwise just take the first one
                if 'bitrate' in mp4_variants[0]:
                    mp4_variants.sort(key=lambda x: x.get('bitrate', 0), reverse=True)
                
                return mp4_variants[0].get('src')
            
            # If no MP4 variants, return the first variant's source
            if variants:
                return variants[0].get('src')
        
        # Check mediaDetails as an alternative
        if 'mediaDetails' in tweet_data:
            for media in tweet_data['mediaDetails']:
                if media.get('type') == 'video' and 'video_info' in media and 'variants' in media['video_info']:
                    variants = media['video_info']['variants']
                    
                    # Prefer MP4 format
                    mp4_variants = [v for v in variants if v.get('content_type') == 'video/mp4']
                    
                    if mp4_variants:
                        # Sort by bitrate if available
                        if 'bitrate' in mp4_variants[0]:
                            mp4_variants.sort(key=lambda x: x.get('bitrate', 0), reverse=True)
                        
                        return mp4_variants[0].get('url')
                    
                    # If no MP4 variants, return the first variant's URL
                    if variants:
                        return variants[0].get('url')
        
        return None
    except Exception as e:
        logger.error(f"Error extracting video URL from tweet data: {str(e)}", exc_info=True)
        return None

async def scrape_twitter_content(url: str) -> Optional[Dict[str, Any]]:
    """
    Scrape content from a Twitter/X.com URL using Apify API.
    This function orchestrates the fetching of the original tweet and its replies.

    Args:
        url (str): The Twitter/X.com URL to scrape

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing the scraped content or None if scraping failed
    """
    try:
        logger.info(f"Scraping Twitter/X.com URL: {url}")

        # Fetch the original tweet
        tweet_data = await fetch_tweet(url)
        if not tweet_data:
            logger.warning(f"Failed to fetch tweet from URL: {url}")
            return None
        
        # Extract the tweet text
        tweet_text = tweet_data.get('text', '')
        
        # Extract the video URL if it exists
        video_url = extract_video_url(tweet_data)
        
        # Extract the author information
        author = tweet_data.get('user', {})
        author_name = author.get('name', '')
        author_screen_name = author.get('screen_name', '')
        
        # Fetch the tweet replies
        replies_data = await fetch_tweet_replies(url)
        
        # Extract reply information
        replies = []
        if replies_data:
            for reply in replies_data:
                reply_text = reply.get('replyText', '')
                reply_author = reply.get('author', {})
                reply_author_name = reply_author.get('name', '')
                
                replies.append({
                    'author': reply_author_name,
                    'text': reply_text
                })
        
        # Compile the scraped content
        scraped_content = {
            'tweet': {
                'text': tweet_text,
                'author': author_name,
                'screen_name': author_screen_name,
                'video_url': video_url
            },
            'replies': replies
        }
        
        # Format the content as markdown for compatibility with the existing system
        markdown_content = format_as_markdown(scraped_content)
        
        return {
            'markdown': markdown_content,
            'raw_data': scraped_content
        }

    except Exception as e:
        logger.error(f"Error scraping Twitter/X.com URL {url}: {str(e)}", exc_info=True)
        return None

def format_as_markdown(scraped_content: Dict[str, Any]) -> str:
    """
    Format the scraped Twitter/X.com content as markdown.

    Args:
        scraped_content (Dict[str, Any]): The scraped content

    Returns:
        str: The formatted markdown content
    """
    try:
        tweet = scraped_content['tweet']
        replies = scraped_content['replies']
        
        # Format the tweet
        markdown = f"# Tweet by @{tweet['screen_name']} ({tweet['author']})\n\n"
        markdown += f"{tweet['text']}\n\n"
        
        # Add video URL if it exists
        if tweet['video_url']:
            markdown += f"**Video URL:** {tweet['video_url']}\n\n"
        
        # Format the replies
        if replies:
            markdown += "## Replies\n\n"
            
            for reply in replies:
                markdown += f"**{reply['author']}:** {reply['text']}\n\n"
        
        return markdown
    except Exception as e:
        logger.error(f"Error formatting scraped content as markdown: {str(e)}", exc_info=True)
        return "Error formatting Twitter/X.com content."

async def is_twitter_url(url: str) -> bool:
    """
    Check if a URL is from Twitter/X.com.

    Args:
        url (str): The URL to check

    Returns:
        bool: True if the URL is from Twitter/X.com, False otherwise
    """
    return bool(re.search(r'(?:twitter\.com|x\.com)', url))
