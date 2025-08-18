"""
Web tools for fetching and searching web content.
Provides simple interfaces for the LLM to access web information.
"""

import aiohttp
import asyncio
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urlparse
from logging_config import logger
import json
from bs4 import BeautifulSoup

class WebTools:
    """Web tools for fetching and searching content."""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    @staticmethod
    def extract_urls(text: str) -> List[str]:
        """
        Extract URLs from text.
        
        Args:
            text: Text to search for URLs
            
        Returns:
            List of URLs found in the text
        """
        url_regex = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?'
        urls = re.findall(url_regex, text)
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        return unique_urls
    
    async def fetch_web_content(self, url: str, max_length: int = 5000) -> Optional[Dict[str, Any]]:
        """
        Fetch and extract content from a web page.
        
        Args:
            url: The URL to fetch
            max_length: Maximum content length to return
            
        Returns:
            Dictionary with title, description, and content, or None if failed
        """
        try:
            # Validate URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                logger.warning(f"Invalid URL format: {url}")
                return None
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch {url}: HTTP {response.status}")
                        return None
                    
                    # Get HTML content
                    html = await response.text()
                    
                    # Parse with BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract title
                    title = None
                    if soup.title:
                        title = soup.title.string.strip() if soup.title.string else None
                    if not title:
                        # Try meta property og:title
                        og_title = soup.find('meta', property='og:title')
                        if og_title and og_title.get('content'):
                            title = og_title['content'].strip()
                    
                    # Extract description
                    description = None
                    meta_desc = soup.find('meta', attrs={'name': 'description'})
                    if meta_desc and meta_desc.get('content'):
                        description = meta_desc['content'].strip()
                    if not description:
                        # Try og:description
                        og_desc = soup.find('meta', property='og:description')
                        if og_desc and og_desc.get('content'):
                            description = og_desc['content'].strip()
                    
                    # Extract main content
                    # Remove script and style elements
                    for script in soup(['script', 'style', 'nav', 'header', 'footer']):
                        script.decompose()
                    
                    # Try to find main content areas
                    main_content = None
                    for selector in ['main', 'article', '[role="main"]', '#content', '.content']:
                        content_elem = soup.select_one(selector)
                        if content_elem:
                            main_content = content_elem
                            break
                    
                    if not main_content:
                        main_content = soup.body if soup.body else soup
                    
                    # Get text content
                    text = main_content.get_text(separator='\n', strip=True)
                    
                    # Clean up text
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    text = '\n'.join(lines)
                    
                    # Truncate if too long
                    if len(text) > max_length:
                        text = text[:max_length] + '...'
                    
                    result = {
                        'url': url,
                        'title': title or 'No title',
                        'description': description,
                        'content': text,
                        'success': True
                    }
                    
                    logger.info(f"Successfully fetched content from {url} ({len(text)} chars)")
                    return result
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None
    
    async def web_search(self, query: str, num_results: int = 5) -> Optional[Dict[str, Any]]:
        """
        Perform a web search using DuckDuckGo or fallback APIs.
        
        Args:
            query: Search query
            num_results: Number of results to return
            
        Returns:
            Dictionary with search results or None if failed
        """
        # Use native search implementation
        result = await self._search_native(query, num_results)
        if result and result.get('success'):
            return result
        
        # Return empty results if native search failed
        logger.warning(f"Native search failed for '{query}'")
        return {
            'query': query,
            'results': [],
            'message': 'Search temporarily unavailable',
            'success': False
        }
    
    async def _search_native(self, query: str, num_results: int = 5) -> Optional[Dict[str, Any]]:
        """
        Native search by directly fetching from reliable sources.
        """
        try:
            # Simplify query for Wikipedia (first 2-3 words to avoid 404s)
            wiki_query = ' '.join(query.split()[:3])
            
            # Define target sites with search/content URLs
            search_targets = [
                f"https://www.google.com/search?q={quote(query)}",
                f"https://en.wikipedia.org/w/index.php?search={quote(wiki_query)}&title=Special%3ASearch",
                f"https://stackoverflow.com/search?q={quote(query)}",
                f"https://github.com/search?q={quote(query)}&type=repositories",
                f"https://www.reddit.com/search/?q={quote(query)}",
            ]
            
            results = []
            
            # Fetch content from targets concurrently
            tasks = []
            for url in search_targets[:num_results]:
                tasks.append(self._fetch_search_target(url, query))
            
            fetched_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            position = 1
            for result in fetched_results:
                if isinstance(result, dict) and result.get('success'):
                    results.append({
                        'position': position,
                        'title': result.get('title', 'No title'),
                        'url': result.get('url', ''),
                        'snippet': result.get('snippet', '')
                    })
                    position += 1
            
            if not results:
                logger.info(f"No results found for '{query}' from native sources")
                return {
                    'query': query,
                    'results': [],
                    'message': 'No results found from available sources',
                    'success': False
                }
            
            logger.info(f"Found {len(results)} native search results for '{query}'")
            
            return {
                'query': query,
                'results': results,
                'count': len(results),
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Native search error for '{query}': {str(e)}")
            return None
    
    async def _fetch_search_target(self, url: str, query: str) -> Optional[Dict[str, Any]]:
        """
        Fetch content from a specific search target URL.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=8) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Extract title
                        title = None
                        if soup.title:
                            title = soup.title.string.strip() if soup.title.string else None
                        
                        # Extract meaningful content
                        content = ""
                        
                        # Google search results extraction
                        if 'google.com' in url:
                            # Look for search result divs
                            search_results = soup.find_all('div', class_='g', limit=2)
                            if search_results:
                                for result in search_results:
                                    h3 = result.find('h3')
                                    if h3:
                                        content += f"{h3.get_text(strip=True)[:100]}. "
                        
                        # Wikipedia search page extraction  
                        elif 'wikipedia.org' in url and 'search=' in url:
                            # Look for search results on Wikipedia search page
                            search_results = soup.find_all('div', class_='mw-search-result-heading', limit=2)
                            if search_results:
                                for result in search_results:
                                    link = result.find('a')
                                    if link:
                                        content += f"{link.get_text(strip=True)[:100]}. "
                        
                        # Wikipedia direct article extraction
                        elif 'wikipedia.org' in url:
                            content_div = soup.find('div', {'id': 'mw-content-text'})
                            if content_div:
                                paragraphs = content_div.find_all('p', limit=2)
                                content = ' '.join([p.get_text(strip=True) for p in paragraphs])
                        
                        # GitHub specific extraction
                        elif 'github.com' in url:
                            # Look for repository items or code
                            repo_items = soup.find_all(['div', 'article'], class_=['Box-row', 'hx_hit-repo'], limit=3)
                            if repo_items:
                                content = ' '.join([item.get_text(strip=True)[:100] for item in repo_items])
                        
                        # StackOverflow specific extraction
                        elif 'stackoverflow.com' in url:
                            question_summaries = soup.find_all('div', class_='s-post-summary', limit=3)
                            if question_summaries:
                                content = ' '.join([div.get_text(strip=True)[:100] for div in question_summaries])
                        
                        # Reddit extraction
                        elif 'reddit.com' in url:
                            post_titles = soup.find_all('h3', limit=3)
                            if post_titles:
                                content = ' '.join([h3.get_text(strip=True)[:100] for h3 in post_titles])
                        
                        # Generic extraction fallback
                        if not content:
                            # Get first few paragraphs or div content
                            for tag in ['p', 'div']:
                                elements = soup.find_all(tag, limit=3)
                                text_content = ' '.join([elem.get_text(strip=True) for elem in elements])
                                if len(text_content) > 50:
                                    content = text_content
                                    break
                        
                        # Clean and limit content
                        content = content[:300] + '...' if len(content) > 300 else content
                        
                        return {
                            'success': True,
                            'title': title or f"Results for '{query}'",
                            'url': url,
                            'snippet': content or f"Information about '{query}' from {urlparse(url).netloc}"
                        }
                    
                    else:
                        # Don't log 404s as warnings since they're expected for some queries
                        if response.status != 404:
                            logger.debug(f"Failed to fetch {url}: HTTP {response.status}")
                        return {'success': False}
                        
        except asyncio.TimeoutError:
            logger.debug(f"Timeout fetching {url}")
            return {'success': False}
        except Exception as e:
            logger.debug(f"Error fetching {url}: {str(e)}")
            return {'success': False}
    
    async def search_and_fetch(self, query: str, num_results: int = 3, fetch_content: bool = True) -> Optional[Dict[str, Any]]:
        """
        Search and optionally fetch content from the top results.
        
        Args:
            query: Search query
            num_results: Number of results to fetch content from
            fetch_content: Whether to fetch full content from results
            
        Returns:
            Combined search and content results
        """
        try:
            # Perform search
            search_results = await self.web_search(query, num_results)
            if not search_results or not search_results.get('success'):
                return search_results
            
            # Optionally fetch content from top results
            if fetch_content and search_results.get('results'):
                for result in search_results['results'][:num_results]:
                    url = result.get('url')
                    if url:
                        content = await self.fetch_web_content(url, max_length=2000)
                        if content:
                            result['fetched_content'] = content.get('content', '')
                            result['fetched_title'] = content.get('title', '')
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error in search_and_fetch for '{query}': {str(e)}")
            return None


# Function tools for LLM to use
async def tool_web_fetch(url: str) -> str:
    """
    Fetch content from a URL.
    Tool for LLM to fetch web page content.
    
    Args:
        url: The URL to fetch
        
    Returns:
        Formatted string with the fetched content
    """
    tools = WebTools()
    result = await tools.fetch_web_content(url)
    
    if not result or not result.get('success'):
        return f"Failed to fetch content from {url}"
    
    response = f"**Fetched: {result['title']}**\n"
    if result.get('description'):
        response += f"*{result['description']}*\n\n"
    response += result['content']
    
    return response


async def tool_web_search(query: str, num_results: int = 5) -> str:
    """
    Search the web for information.
    Tool for LLM to search the web.
    
    Args:
        query: Search query
        num_results: Number of results to return
        
    Returns:
        Formatted string with search results
    """
    tools = WebTools()
    results = await tools.web_search(query, num_results)
    
    if not results or not results.get('success'):
        return f"Search failed for query: {query}"
    
    response = f"**Web search results for: {query}**\n\n"
    
    if results.get('results'):
        for result in results['results']:
            response += f"[{result['position']}] **{result['title']}**\n"
            response += f"   URL: {result['url']}\n"
            if result.get('snippet'):
                response += f"   {result['snippet']}\n"
            response += "\n"
    else:
        response += "No results found.\n"
    
    return response


async def tool_search_and_summarize(query: str, num_results: int = 3) -> str:
    """
    Search the web and fetch content from top results.
    Tool for LLM to get comprehensive information on a topic.
    
    Args:
        query: Search query
        num_results: Number of results to fetch content from
        
    Returns:
        Formatted string with search results and content
    """
    tools = WebTools()
    results = await tools.search_and_fetch(query, num_results, fetch_content=True)
    
    if not results or not results.get('success'):
        return f"Search failed for query: {query}"
    
    response = f"**Web search with content for: {query}**\n\n"
    
    if results.get('results'):
        for result in results['results']:
            response += f"[{result['position']}] **{result['title']}**\n"
            response += f"   URL: {result['url']}\n"
            
            if result.get('fetched_content'):
                content_preview = result['fetched_content'][:500]
                if len(result['fetched_content']) > 500:
                    content_preview += '...'
                response += f"   Content: {content_preview}\n"
            elif result.get('snippet'):
                response += f"   Snippet: {result['snippet']}\n"
            response += "\n"
    else:
        response += "No results found.\n"
    
    response += f"\n*Sources: {len(results.get('results', []))} results found*"
    
    return response


# Example of how to integrate with LLM
def format_for_llm_tools() -> List[Dict[str, Any]]:
    """
    Format web tools for LLM function calling.
    
    Returns:
        List of tool definitions for LLM
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "Fetch content from a specific URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to fetch content from"
                        }
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results to return",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_and_summarize",
                "description": "Search the web and get content from top results",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results to fetch content from",
                            "default": 3
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]
