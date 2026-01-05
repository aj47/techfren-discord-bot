"""
Web scraper module for the Discord bot.
Handles scraping URL content using Crawl4AI (open-source, no API key required).

Note: This file is named firecrawl_handler.py for backward compatibility,
but now uses Crawl4AI instead of Firecrawl.
"""

import asyncio
import logging
from typing import Optional

try:
    from crawl4ai import AsyncWebCrawler
    CRAWL4AI_AVAILABLE = True
except ImportError:
    AsyncWebCrawler = None  # type: ignore
    CRAWL4AI_AVAILABLE = False

# Set up logging
logger = logging.getLogger('discord_bot.web_scraper')

# Global crawler instance for reuse (connection pooling)
_crawler_instance: Optional["AsyncWebCrawler"] = None
_crawler_lock = asyncio.Lock()


async def _get_crawler() -> Optional["AsyncWebCrawler"]:
    """Get or create a shared crawler instance."""
    global _crawler_instance

    if not CRAWL4AI_AVAILABLE:
        return None

    async with _crawler_lock:
        if _crawler_instance is None:
            _crawler_instance = AsyncWebCrawler(verbose=False)
            await _crawler_instance.__aenter__()
        return _crawler_instance


async def scrape_url_content(url: str) -> Optional[str]:
    """
    Scrape content from a URL using Crawl4AI.

    Args:
        url (str): The URL to scrape

    Returns:
        Optional[str]: The scraped content as markdown, or None if scraping failed
    """
    try:
        logger.info(f"Scraping URL with Crawl4AI: {url}")

        if not CRAWL4AI_AVAILABLE:
            logger.error("Crawl4AI is not installed. Run: pip install crawl4ai && crawl4ai-setup")
            return None

        crawler = await _get_crawler()
        if crawler is None:
            logger.error("Failed to initialize Crawl4AI crawler")
            return None

        # Run the crawl with a timeout
        try:
            result = await asyncio.wait_for(
                crawler.arun(url=url),
                timeout=60.0  # 60 second timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Timeout while scraping URL: {url}")
            return None

        if not result:
            logger.warning(f"Failed to scrape URL: {url} - Empty response from Crawl4AI")
            return None

        # Extract markdown content from the result
        markdown_content: Optional[str] = None

        # Crawl4AI returns result with .markdown attribute
        if hasattr(result, 'markdown') and result.markdown:
            markdown_content = result.markdown
        elif hasattr(result, 'cleaned_html') and result.cleaned_html:
            # Fallback to cleaned HTML if markdown not available
            markdown_content = result.cleaned_html
        elif hasattr(result, 'html') and result.html:
            # Last resort: raw HTML
            markdown_content = result.html

        if not markdown_content:
            logger.warning(f"Failed to scrape URL: {url} - No content found in response")
            return None

        # Log success (truncate content for logging)
        content_preview = markdown_content[:100] + ('...' if len(markdown_content) > 100 else '')
        logger.info(f"Successfully scraped URL: {url} - Content: {content_preview}")

        return markdown_content

    except Exception as e:
        logger.error(f"Error scraping URL {url}: {str(e)}", exc_info=True)
        return None


async def cleanup_crawler():
    """Cleanup the global crawler instance. Call this on bot shutdown."""
    global _crawler_instance
    async with _crawler_lock:
        if _crawler_instance is not None:
            try:
                await _crawler_instance.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error cleaning up crawler: {e}")
            finally:
                _crawler_instance = None
