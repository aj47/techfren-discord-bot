import aiohttp
import json
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
        
        # Gemäß der APIDOCS.md können wir direkte Anfragen ohne API-Key nutzen
        # mit dem URL-basierten API-Endpunkt
        encoded_query = urllib.parse.quote(query)
        url = f"https://text.pollinations.ai/{encoded_query}?model=searchgpt"
        
        # Prepare the headers with referrer information
        headers = {
            "Content-Type": "application/json",
            "Referer": "https://techfren.net",  # Der Referrer für die Anfrage
            "User-Agent": "TechFren Discord Bot"
        }
        
        # Keine Payload nötig für die GET-Anfrage
        
        # Make the API request (GET statt POST)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=60) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Pollinations API error: {response.status} - {error_text}")
                    return None
                
                # Die Antwort ist direkt der Text, kein JSON
                response_text = await response.text()
                logger.info(f"Pollinations API search successful")
                
                # Wir formatieren die Antwort in ein Dict, um konsistent mit dem ursprünglichen Format zu sein
                result = {
                    "text": response_text,
                    "query": query,
                    "model": "searchgpt"
                }
                return result
                
    except Exception as e:
        logger.error(f"Error searching web with Pollinations API: {str(e)}", exc_info=True)
        return None
