"""
Firecrawl handler module for the Discord bot.
Handles scraping URL content using the Firecrawl API.
"""

import asyncio
import logging
from typing import Optional

try:
    from firecrawl import Firecrawl  # type: ignore
except Exception:
    Firecrawl = None  # type: ignore

try:
    from firecrawl import FirecrawlApp  # type: ignore
except Exception:
    FirecrawlApp = None  # type: ignore

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

        # Initialize the Firecrawl client (supporting both new and legacy SDKs)
        client = None
        if 'Firecrawl' in globals() and Firecrawl is not None:  # type: ignore[name-defined]
            client = Firecrawl(api_key=config.firecrawl_api_key)  # type: ignore[call-arg]
        elif 'FirecrawlApp' in globals() and FirecrawlApp is not None:  # type: ignore[name-defined]
            client = FirecrawlApp(api_key=config.firecrawl_api_key)  # type: ignore[call-arg]
        else:
            logger.error("Firecrawl SDK is not installed or incompatible")
            return None

        # Use a separate thread for the blocking API call
        loop = asyncio.get_event_loop()

        def _do_scrape():
            # Preferred: new Firecrawl client with .scrape (v2)
            if hasattr(client, "scrape"):
                return client.scrape(url, formats=["markdown"], timeout=config.firecrawl_timeout_ms)  # type: ignore[call-arg]
            # Legacy clients: use .scrape_url (v1)
            if hasattr(client, "scrape_url"):
                return client.scrape_url(url, formats=["markdown"], timeout=config.firecrawl_timeout_ms)  # type: ignore[call-arg]
            # v1 compatibility shim on newer client
            v1_client = getattr(client, "v1", None)
            if v1_client is not None and hasattr(v1_client, "scrape_url"):
                return v1_client.scrape_url(url, formats=["markdown"], timeout=config.firecrawl_timeout_ms)  # type: ignore[call-arg]
            raise RuntimeError("Firecrawl client does not support scrape APIs")

        scrape_result = await loop.run_in_executor(None, _do_scrape)

        # Extract markdown-like content from the response
        if not scrape_result:
            logger.warning(f"Failed to scrape URL: {url} - Empty response from Firecrawl")
            return None

        markdown_content: Optional[str] = None

        try:
            # Case 1: dict responses (common for older SDKs and some HTTP clients)
            if isinstance(scrape_result, dict):
                # Newer SDKs: markdown at the top level
                if isinstance(scrape_result.get("markdown"), str):
                    markdown_content = scrape_result["markdown"]
                # Some versions nest content under 'data'
                elif isinstance(scrape_result.get("data"), dict):
                    data = scrape_result["data"]
                    if isinstance(data.get("markdown"), str):
                        markdown_content = data["markdown"]
                    elif isinstance(data.get("content"), str):
                        markdown_content = data["content"]
                # Older responses may use 'content' at the top level
                elif isinstance(scrape_result.get("content"), str):
                    markdown_content = scrape_result["content"]

            # Case 2: object-style responses (e.g. Pydantic models from Firecrawl SDK)
            if markdown_content is None and hasattr(scrape_result, "markdown"):
                attr_markdown = getattr(scrape_result, "markdown", None)
                if isinstance(attr_markdown, str):
                    markdown_content = attr_markdown

            # Case 3: list/sequence responses – use the first element if present
            if markdown_content is None and isinstance(scrape_result, (list, tuple)) and scrape_result:
                first = scrape_result[0]
                if isinstance(first, dict):
                    if isinstance(first.get("markdown"), str):
                        markdown_content = first["markdown"]
                    elif isinstance(first.get("content"), str):
                        markdown_content = first["content"]
                elif hasattr(first, "markdown"):
                    first_markdown = getattr(first, "markdown", None)
                    if isinstance(first_markdown, str):
                        markdown_content = first_markdown
        except Exception as parse_error:
            logger.warning(f"Error parsing Firecrawl response for URL {url}: {parse_error}")

        if not markdown_content:
            # Log a compact preview of the response for debugging
            preview = str(scrape_result)
            if len(preview) > 300:
                preview = preview[:300] + "..."
            logger.warning(
                f"Failed to scrape URL: {url} - No markdown-like content found in response: {preview}"
            )
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
