"""
URL Processor

This module provides centralized URL processing capabilities to eliminate 
code duplication in URL scraping logic across the codebase.
"""

from logging_config import logger
from typing import Optional, Dict, Any
import config


class URLProcessor:
    """
    Centralized processor for URL scraping with fallback logic.
    
    This class provides unified URL scraping functionality that:
    - Determines the appropriate scraper for different URL types
    - Implements fallback logic when primary scrapers fail
    - Standardizes the scraping process across the application
    """

    @staticmethod
    async def scrape_content(url: str) -> Optional[Dict[str, Any]]:
        """
        Unified URL scraping with intelligent fallback logic.
        
        This method:
        1. Determines the appropriate scraper based on URL type
        2. Attempts primary scraping method
        3. Falls back to Firecrawl if primary method fails
        4. Returns standardized result format
        
        Args:
            url (str): The URL to scrape
            
        Returns:
            Optional[Dict[str, Any]]: Dictionary containing scraped content or None if failed
        """
        try:
            logger.info(f"Processing URL: {url}")
            
            # Import handlers here to avoid circular imports
            from youtube_handler import is_youtube_url, scrape_youtube_content
            from firecrawl_handler import scrape_url_content
            from apify_handler import is_twitter_url, scrape_twitter_content, extract_tweet_id
            
            scraped_result = None
            markdown_content = None
            
            # Check if the URL is from YouTube
            if await is_youtube_url(url):
                logger.info(f"Detected YouTube URL: {url}")
                scraped_result = await scrape_youtube_content(url)
                
                if scraped_result:
                    logger.info(f"Successfully scraped YouTube content: {url}")
                    markdown_content = scraped_result.get('markdown')
                else:
                    logger.warning(f"Failed to scrape YouTube content, falling back to Firecrawl: {url}")
                    scraped_result = await scrape_url_content(url)
                    markdown_content = scraped_result if isinstance(scraped_result, str) else ''
                    
            # Check if the URL is from Twitter/X.com
            elif await is_twitter_url(url):
                logger.info(f"Detected Twitter/X.com URL: {url}")
                scraped_result = await URLProcessor._process_twitter_url(url)
                
                if isinstance(scraped_result, dict):
                    markdown_content = scraped_result.get('markdown', '')
                elif isinstance(scraped_result, str):
                    markdown_content = scraped_result
                else:
                    markdown_content = ''
                    
            else:
                # For non-Twitter/X.com and non-YouTube URLs, use Firecrawl
                logger.info(f"Processing URL with Firecrawl: {url}")
                scraped_result = await scrape_url_content(url)
                markdown_content = scraped_result if isinstance(scraped_result, str) else ''
            
            # Standardize return format
            if markdown_content:
                if isinstance(scraped_result, dict):
                    return scraped_result
                else:
                    return {"markdown": markdown_content}
            else:
                logger.warning(f"No content scraped for URL: {url}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing URL {url}: {str(e)}", exc_info=True)
            return None

    @staticmethod
    async def _process_twitter_url(url: str) -> Optional[Dict[str, Any]]:
        """
        Process Twitter/X.com URLs with specialized logic.
        
        Args:
            url (str): The Twitter/X.com URL to process
            
        Returns:
            Optional[Dict[str, Any]]: Scraped content or None if failed
        """
        try:
            from apify_handler import extract_tweet_id, scrape_twitter_content
            from firecrawl_handler import scrape_url_content
            
            # Validate if the URL contains a tweet ID (status)
            tweet_id = extract_tweet_id(url)
            if not tweet_id:
                logger.warning(f"URL appears to be Twitter/X.com but doesn't contain a valid tweet ID: {url}")
                
                # Handle base Twitter/X.com URLs
                if url.lower() in ["https://x.com", "https://twitter.com", "http://x.com", "http://twitter.com"]:
                    logger.info(f"Handling base Twitter/X.com URL with custom response: {url}")
                    return {
                        "markdown": f"# Twitter/X.com\n\nThis is the main page of Twitter/X.com: {url}"
                    }
                else:
                    # For other Twitter/X.com URLs without a tweet ID, try Firecrawl
                    return await scrape_url_content(url)
            
            # Check if Apify API token is configured
            # Configuration validation is handled by config_validator.py at startup
            # If apify_api_token is not configured, fall back to Firecrawl
            if not hasattr(config, 'apify_api_token') or not config.apify_api_token:
                logger.info("Apify API token not configured, using Firecrawl for Twitter/X.com content")
                return await scrape_url_content(url)
            
            # Use Apify to scrape Twitter/X.com content
            scraped_result = await scrape_twitter_content(url)
            
            if scraped_result:
                logger.info(f"Successfully scraped Twitter/X.com content with Apify: {url}")
                return scraped_result
            else:
                logger.warning(f"Failed to scrape Twitter/X.com content with Apify, falling back to Firecrawl: {url}")
                return await scrape_url_content(url)
                
        except Exception as e:
            logger.error(f"Error processing Twitter URL {url}: {str(e)}", exc_info=True)
            return None

    @staticmethod
    async def determine_scraper(url: str) -> str:
        """
        Determine the appropriate scraper for a given URL.
        
        Args:
            url (str): The URL to analyze
            
        Returns:
            str: The scraper type ('youtube', 'twitter', 'firecrawl')
        """
        try:
            # Import handlers here to avoid circular imports
            from youtube_handler import is_youtube_url
            from apify_handler import is_twitter_url
            
            if await is_youtube_url(url):
                return 'youtube'
            elif await is_twitter_url(url):
                return 'twitter'
            else:
                return 'firecrawl'
                
        except Exception as e:
            logger.error(f"Error determining scraper for URL {url}: {str(e)}", exc_info=True)
            return 'firecrawl'  # Default fallback

    @staticmethod
    async def scrape_content_on_demand(url: str) -> Optional[Dict[str, Any]]:
        """
        Scrape a URL on-demand and return summarized content.
        
        This is a convenience method that combines scraping with summarization
        for use in contexts where immediate processing is needed.
        
        Args:
            url (str): The URL to scrape
            
        Returns:
            Optional[Dict[str, Any]]: Dictionary containing summary and key_points, or None if failed
        """
        try:
            # Import here to avoid circular imports
            from llm_handler import summarize_scraped_content
            
            # First scrape the content
            scraped_result = await URLProcessor.scrape_content(url)
            if not scraped_result:
                logger.warning(f"No content scraped for on-demand URL: {url}")
                return None
            
            # Extract markdown content
            markdown_content = scraped_result.get('markdown', '')
            if not markdown_content:
                logger.warning(f"No markdown content found for URL: {url}")
                return None
            
            # Summarize the scraped content
            summarized_data = await summarize_scraped_content(markdown_content, url)
            if not summarized_data:
                logger.warning(f"Failed to summarize scraped content for URL: {url}")
                return None
            
            return {
                'summary': summarized_data.get('summary', ''),
                'key_points': summarized_data.get('key_points', [])
            }
            
        except Exception as e:
            logger.error(f"Error scraping URL on-demand {url}: {str(e)}", exc_info=True)
            return None