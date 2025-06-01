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

        # Define the blocking operations as a separate function
        def _scrape_url_blocking():
            try:
                # Initialize the Firecrawl client
                app = FirecrawlApp(api_key=config.firecrawl_api_key)

                # Perform the scraping
                scrape_result = app.scrape_url(
                    url,
                    formats=['markdown'],
                    page_options={'onlyMainContent': True}
                )

                return scrape_result
            except Exception as e:
                # Re-raise to be handled in the async context
                raise e

        # Execute all blocking operations in thread executor
        scrape_result = await asyncio.get_event_loop().run_in_executor(None, _scrape_url_blocking)

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
        # Ensure error handling doesn't block the event loop
        def _log_error():
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

        # Run error logging in thread executor to avoid blocking
        await asyncio.get_event_loop().run_in_executor(None, _log_error)
        return None
