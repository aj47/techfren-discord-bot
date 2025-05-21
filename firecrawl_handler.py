"""
Firecrawl handler module for the Discord bot.
Handles scraping URL content using the Firecrawl API.
"""

import asyncio
from firecrawl import FirecrawlApp
import logging
from typing import Optional

# Import config for API key
import config

# Set up logging
logger = logging.getLogger('discord_bot.firecrawl_handler')

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
                page_options={'onlyMainContent': True}
            )
        )

        # Check if scraping was successful
        if not scrape_result or 'markdown' not in scrape_result:
            logger.warning(f"Failed to scrape URL: {url} - No markdown content returned")
            return None

        markdown_content = scrape_result['markdown']
        
        # Log success (truncate content for logging)
        content_preview = markdown_content[:100] + ('...' if len(markdown_content) > 100 else '')
        logger.info(f"Successfully scraped URL: {url} - Content: {content_preview}")
        
        return markdown_content

    except Exception as e:
        logger.error(f"Error scraping URL {url}: {str(e)}", exc_info=True)
        return None
