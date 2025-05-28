import aiohttp
import urllib.parse
from logging_config import logger
from typing import Optional, Dict, Any

async def search_web(query: str) -> Optional[Dict[str, Any]]:
    """
    Search the web using the Pollinations API with the searchgpt model.
    
    Args:
        query (str): The search query
        
    Returns:
        Optional[Dict[str, Any]]: The search results or None if an error occurred
    """
    try:
        logger.info(f"Searching web with Pollinations API for query: {query[:50]}{'...' if len(query) > 50 else ''}")
        
        # According to APIDOCS.md, we can use direct requests without an API key
        # with the URL-based API endpoint
        encoded_query = urllib.parse.quote(query)
        url = f"https://text.pollinations.ai/{encoded_query}?model=searchgpt"
        
        # Prepare the headers with referrer information
        headers = {
            "Content-Type": "application/json",
            "Referer": "https://techfren.net",  # The referrer for the request
            "User-Agent": "TechFren Discord Bot"
        }
        
        # No payload needed for the GET request
        
        # Make the API request (GET instead of POST)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=60) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Pollinations API error: {response.status} - {error_text}")
                    return None
                
                # The response is directly the text, not JSON
                response_text = await response.text()
                logger.info(f"Pollinations API search successful")
                
                # We format the response into a dict to be consistent with the original format
                result = {
                    "text": response_text,
                    "query": query,
                    "model": "searchgpt"
                }
                return result
                
    except Exception as e:
        logger.error(f"Error searching web with Pollinations API: {str(e)}", exc_info=True)
        return None
