"""
Firecrawl handler module for the Discord bot.
Handles scraping URL content using the Firecrawl API.
"""

import asyncio
from firecrawl import FirecrawlApp  # type: ignore
import logging
from typing import Optional

# Import config for API key
import config

# Set up logging
logger = logging.getLogger('discord_bot.firecrawl_handler')
logger.setLevel(logging.DEBUG)

async def scrape_url_content(url: str) -> Optional[str]:
    """
    Scrape content from a URL using Firecrawl API.

    Args:
        url (str): The URL to scrape

    Returns:
        Optional[str]: The scraped content as markdown, or None if scraping failed
    """
    try:
        logger.info(f"Scraping URL: {url}")

        # Check if Firecrawl API key exists
        if not hasattr(config, 'firecrawl_api_key') or not config.firecrawl_api_key:
            logger.error("Firecrawl API key not found in config.py or is empty")
            return None

        # Initialize the Firecrawl client
        app = FirecrawlApp(api_key=config.firecrawl_api_key)

        # Use a separate thread for the blocking API call
        loop = asyncio.get_event_loop()
        scrape_result = await loop.run_in_executor(
            None,
            lambda: app.scrape_url(
                url,
                formats=['markdown'],
                onlyMainContent=True
            )
        )

        # Debug: Log the actual response structure
        logger.debug(f"Firecrawl response for {url}: {type(scrape_result)} - Keys: {scrape_result.keys() if isinstance(scrape_result, dict) else 'Not a dict'}")
        
        # Check if scraping was successful
        if not scrape_result:
            logger.warning(f"Failed to scrape URL: {url} - No response returned")
            return None
            
        # Handle different response structures
        if isinstance(scrape_result, dict):
            if 'markdown' in scrape_result:
                markdown_content = scrape_result['markdown']
            elif 'data' in scrape_result and isinstance(scrape_result['data'], dict) and 'markdown' in scrape_result['data']:
                markdown_content = scrape_result['data']['markdown']
            elif 'content' in scrape_result:
                markdown_content = scrape_result['content']
            else:
                logger.warning(f"Failed to scrape URL: {url} - No markdown content found in response. Available keys: {list(scrape_result.keys())}")
                return None
        else:
            # If response is not a dict, assume it's the content directly
            markdown_content = str(scrape_result)
        
        # Check if content is empty or None
        if not markdown_content or markdown_content.strip() == "":
            logger.warning(f"Failed to scrape URL: {url} - Content is empty (possible bot blocking or private content)")
            return None
        
        # Log success (truncate content for logging)
        content_preview = markdown_content[:100] + ('...' if len(markdown_content) > 100 else '')
        logger.info(f"Successfully scraped URL: {url} - Content: {content_preview}")
        
        return markdown_content

    except Exception as e:
        # Provide more detailed error information
        error_message = str(e)
        if hasattr(e, 'response') and e.response:
            status_code = getattr(e.response, 'status_code', 'unknown')
            error_message = f"HTTP Error {status_code}: {error_message}"
            
            # Try to extract more details from the response if available
            try:
                response_text = e.response.text
                if response_text:
                    error_message += f" - Response: {response_text[:200]}"
            except:
                pass
                
        logger.error(f"Error scraping URL {url}: {error_message}", exc_info=True)
        return None
