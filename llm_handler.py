from openai import AsyncOpenAI
from logging_config import logger
import config # Assuming config.py is in the same directory or accessible
import json
from typing import Optional, Dict, Any
import asyncio
import re
from message_utils import generate_discord_message_link
from database import get_scraped_content_by_url
from discord_formatter import DiscordFormatter
from web_tools import WebTools, tool_web_fetch, tool_web_search, tool_search_and_summarize

def extract_urls_from_text(text: str) -> list[str]:
    """
    Extract URLs from text using regex.
    
    Args:
        text (str): Text to search for URLs
        
    Returns:
        list[str]: List of URLs found in the text
    """
    url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?'
    return re.findall(url_pattern, text)

def should_force_web_tools(query: str, has_discord_context: bool = False) -> bool:
    """
    Determine if a query should force the use of web tools.
    
    Args:
        query (str): The user's query
        has_discord_context (bool): Whether Discord server context is available
        
    Returns:
        bool: True if web tools should be forced
    """
    query_lower = query.lower()
    
    # Don't force web tools for Discord-specific queries when we have context
    discord_keywords = ['chat', 'conversation', 'messages', 'channel', 'server', 'guild', 'discord', 'here', 'this channel']
    if has_discord_context and any(keyword in query_lower for keyword in discord_keywords):
        return False
    
    # Force web tools for queries that clearly need current information
    force_keywords = [
        'news', 'latest', 'current', 'today', 'recent', 'update', 'price', 'stock',
        'weather', 'trending', 'breaking', 'new release', 'announcement',
        'what is', 'tell me about', 'explain', 'how to', 'tutorial',
        'compare', 'vs', 'versus', 'difference between', 'best', 'top',
        'review', 'rating', 'opinion', 'facts about', 'information about'
    ]
    
    return any(keyword in query_lower for keyword in force_keywords)

async def validate_channel_exists(bot_client, guild_id: str, channel_id: str) -> bool:
    """
    Check if a Discord channel/thread still exists.
    
    Args:
        bot_client: Discord bot client
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        
    Returns:
        bool: True if channel exists, False otherwise
    """
    if not bot_client or not guild_id or not channel_id:
        return False
    
    try:
        guild = bot_client.get_guild(int(guild_id))
        if not guild:
            return False
            
        # Check if it's a regular channel
        channel = guild.get_channel(int(channel_id))
        if channel:
            return True
            
        # Check if it's a thread in any text channel
        for text_channel in guild.text_channels:
            if hasattr(text_channel, 'threads'):
                for thread in text_channel.threads:
                    if thread.id == int(channel_id):
                        return True
        
        return False
    except Exception as e:
        logger.debug(f"Channel validation failed for {guild_id}/{channel_id}: {e}")
        return False

async def extract_discord_sources_from_context(message_context: Optional[Dict[str, Any]], bot_client=None) -> list[Dict[str, Any]]:
    """
    Extract and validate Discord message links from the message context.
    
    Args:
        message_context: The message context containing recent messages
        bot_client: Discord bot client for validation
        
    Returns:
        list[Dict[str, Any]]: List of Discord source objects with validation status
    """
    discord_sources = []
    
    if not message_context:
        return discord_sources
    
    # Extract from recent messages
    recent_messages = message_context.get('recent_messages', [])
    for msg in recent_messages:
        message_id = msg.get('id', '')
        guild_id = msg.get('guild_id', '')
        channel_id = msg.get('channel_id', '')
        author_name = msg.get('author_name', 'Unknown')
        created_at = msg.get('created_at', '')
        
        if message_id and channel_id:
            # Check if channel still exists (if bot_client available)
            channel_exists = True  # Default assumption
            if bot_client and guild_id:
                try:
                    channel_exists = await validate_channel_exists(bot_client, guild_id, channel_id)
                except Exception as e:
                    logger.debug(f"Channel validation error: {e}")
                    channel_exists = True  # Assume exists on error
            
            if channel_exists:
                # Channel exists, create normal link
                if guild_id:
                    link = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
                else:
                    link = f"https://discord.com/channels/@me/{channel_id}/{message_id}"
                
                discord_sources.append({
                    'link': link,
                    'valid': True,
                    'author': author_name,
                    'time': created_at,
                    'channel_id': channel_id
                })
            else:
                # Channel doesn't exist, store metadata instead
                discord_sources.append({
                    'link': None,
                    'valid': False,
                    'author': author_name,
                    'time': created_at,
                    'channel_id': channel_id
                })
    
    return discord_sources

def extract_web_sources_from_tool_results(tool_results: list) -> list[str]:
    """
    Extract web URLs from tool results.
    
    Args:
        tool_results: List of tool result dictionaries
        
    Returns:
        list[str]: List of web source URLs
    """
    web_sources = []
    
    for tool_result in tool_results:
        output = tool_result.get('output', '')
        
        # Extract URLs from tool output using regex
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?'
        urls = re.findall(url_pattern, output)
        web_sources.extend(urls)
    
    return web_sources

def ensure_sources_in_response(response: str, discord_sources: list[Dict[str, Any]], web_sources: list[str], has_discord_context: bool = False, is_mention_query: bool = False) -> str:
    """
    Ensure that sources are included in the response, adding them if missing.
    
    Args:
        response: The LLM response
        discord_sources: List of Discord source objects with validation status
        web_sources: List of web source URLs  
        has_discord_context: Whether Discord context was provided
        is_mention_query: Whether this is a @bot mention query (stricter validation)
        
    Returns:
        str: Response with sources ensured
    """
    # Check if sources section already exists
    has_sources_section = bool(re.search(r'\n\s*\*{0,2}\s*Sources?\s*:?\*{0,2}\s*\n', response, re.IGNORECASE))
    
    # Count Discord links in the response
    discord_link_count = len(re.findall(r'discord\.com/channels/', response))
    
    # Check if web citations are present when they should be
    web_citations_present = bool(re.search(r'\[\d+\]', response)) and web_sources
    
    # Determine minimum required sources (stricter for @bot mentions)
    if is_mention_query:
        MIN_REQUIRED_DISCORD_SOURCES = 5  # Stricter for @bot mentions
    else:
        MIN_REQUIRED_DISCORD_SOURCES = 3  # Normal for summary commands
    
    required_discord_sources = max(MIN_REQUIRED_DISCORD_SOURCES, len(discord_sources) * 0.4) if discord_sources else 0
    
    # Check if we have sufficient Discord links
    sufficient_discord_links = discord_link_count >= required_discord_sources
    
    # Determine what sources are missing
    missing_discord = has_discord_context and discord_sources and not sufficient_discord_links
    missing_web = web_sources and not web_citations_present
    missing_sources_section = (missing_discord or missing_web) and not has_sources_section
    
    # For Discord context, ALWAYS add sources if we don't have enough
    force_discord_sources = has_discord_context and discord_sources and not sufficient_discord_links
    
    # Log what sources are missing
    if missing_discord or missing_web or missing_sources_section:
        query_type = "mention" if is_mention_query else "summary"
        logger.warning(f"Sources missing in {query_type} response - Discord: {missing_discord}, Web: {missing_web}, Sources section: {missing_sources_section}")
        logger.warning(f"Discord link count: {discord_link_count}, Required: {required_discord_sources}, Force Discord sources: {force_discord_sources}")
    
    # Add missing sources (prioritize Discord sources for guild context)
    if missing_sources_section or force_discord_sources:
        # Add a sources section at the end, before any mermaid diagrams
        mermaid_pattern = r'```mermaid'
        mermaid_match = re.search(mermaid_pattern, response, re.IGNORECASE)
        
        sources_section = "\n\n📚 **Sources:**\n"
        
        # Add Discord sources (prioritize for guild context)
        if missing_discord or force_discord_sources:
            sources_section += "**Discord Messages:**\n"
            for i, source in enumerate(discord_sources[:10], 1):  # Limit to first 10
                if source['valid'] and source['link']:
                    # Valid channel, use clickable link
                    sources_section += f"• [Message {i}]({source['link']})\n"
                else:
                    # Deleted channel, use descriptive text
                    time_str = source['time']
                    if hasattr(time_str, 'strftime'):
                        time_str = time_str.strftime('%H:%M')
                    elif isinstance(time_str, str):
                        # Try to parse and format time
                        try:
                            from datetime import datetime
                            parsed_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                            time_str = parsed_time.strftime('%H:%M')
                        except:
                            time_str = str(time_str)[:10]  # Fallback to first 10 chars
                    
                    sources_section += f"• [{source['author']} at {time_str}] (Deleted Channel)\n"
            sources_section += "\n"
        
        # Add web sources
        if missing_web:
            sources_section += "**Web Sources:**\n"
            for i, url in enumerate(web_sources[:5], 1):  # Limit to first 5
                sources_section += f"[{i}] <{url}>\n"
        
        # Insert before mermaid diagrams or at the end
        if mermaid_match:
            response = response[:mermaid_match.start()] + sources_section + response[mermaid_match.start():]
        else:
            response += sources_section
    
    return response

async def scrape_url_on_demand(url: str) -> Optional[Dict[str, Any]]:
    """
    Scrape a URL on-demand and return summarized content.
    
    Args:
        url (str): The URL to scrape
        
    Returns:
        Optional[Dict[str, Any]]: Dictionary containing summary and key_points, or None if failed
    """
    try:
        # Import here to avoid circular imports
        from youtube_handler import is_youtube_url, scrape_youtube_content
        from firecrawl_handler import scrape_url_content
        from apify_handler import is_twitter_url, scrape_twitter_content
        import config
        
        # Check if the URL is from YouTube
        if await is_youtube_url(url):
            logger.info(f"Scraping YouTube URL on-demand: {url}")
            scraped_result = await scrape_youtube_content(url)
            if not scraped_result:
                logger.warning(f"Failed to scrape YouTube content: {url}")
                return None
            markdown_content = scraped_result.get('markdown', '')
            
        # Check if the URL is from Twitter/X.com
        elif await is_twitter_url(url):
            logger.info(f"Scraping Twitter/X.com URL on-demand: {url}")
            if hasattr(config, 'apify_api_token') and config.apify_api_token:
                scraped_result = await scrape_twitter_content(url)
                if not scraped_result:
                    logger.warning(f"Failed to scrape Twitter content with Apify, falling back to Firecrawl: {url}")
                    scraped_result = await scrape_url_content(url)
                    markdown_content = scraped_result if isinstance(scraped_result, str) else ''
                else:
                    markdown_content = scraped_result.get('markdown', '')
            else:
                scraped_result = await scrape_url_content(url)
                markdown_content = scraped_result if isinstance(scraped_result, str) else ''
                
        else:
            # For other URLs, use Firecrawl
            logger.info(f"Scraping URL with Firecrawl on-demand: {url}")
            scraped_result = await scrape_url_content(url)
            markdown_content = scraped_result if isinstance(scraped_result, str) else ''
        
        if not markdown_content:
            logger.warning(f"No content scraped for URL: {url}")
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

async def call_llm_api(query, message_context=None, bot_client=None):
    """
    Call the LLM API with the user's query and return the response

    Args:
        query (str): The user's query text
        message_context (dict, optional): Context containing referenced and linked messages
        bot_client (discord.Client, optional): Discord bot client for channel validation

    Returns:
        str: The LLM's response or an error message
    """
    try:
        logger.info(f"Calling LLM API with query: {query[:50]}{'...' if len(query) > 50 else ''}")

        # Determine which LLM provider to use
        llm_provider = config.llm_provider
        
        if llm_provider == 'chutes':
            # Use Chutes.ai
            base_url = 'https://llm.chutes.ai/v1'
            api_key = config.chutes_api_key
            # Default model for Chutes if not specified
            model = config.llm_model if config.llm_model != 'sonar' else 'gpt-4o-mini'
            if not api_key:
                logger.error("Chutes API key not found in config")
                return "Error: Chutes API key is missing. Please check your .env configuration."
        else:
            # Default to Perplexity
            if not config.perplexity:
                logger.error("Perplexity API key not found in config or is empty")
                return "Error: Perplexity API key is missing. Please check your .env configuration."
            base_url = config.perplexity_base_url
            api_key = config.perplexity
            # Default model for Perplexity if not specified
            model = config.llm_model if config.llm_model != 'gpt-4o-mini' else 'sonar'
        
        # Initialize the OpenAI client with selected provider
        openai_client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=60.0
        )
        
        # Prepare the user content with message context if available
        # Add context acknowledgment for Discord channels
        context_acknowledgment = ""
        if message_context and message_context.get('recent_messages'):
            recent_msg_count = len(message_context.get('recent_messages', []))
            channel_name = message_context.get('discord_context', {}).get('channel_name', 'this channel')
            context_acknowledgment = f"**AVAILABLE CONTEXT:** You have access to {recent_msg_count} recent Discord messages from #{channel_name}.\n\n"
        
        user_content = context_acknowledgment + query
        if message_context:
            context_parts = []

            # Add referenced message (reply) context
            if message_context.get('referenced_message'):
                ref_msg = message_context['referenced_message']
                ref_author = getattr(ref_msg, 'author', None)
                ref_author_name = str(ref_author) if ref_author else "Unknown"
                ref_content = getattr(ref_msg, 'content', '')
                ref_timestamp = getattr(ref_msg, 'created_at', None)
                ref_time_str = ref_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC') if ref_timestamp else "Unknown time"

                context_parts.append(f"**Referenced Message (Reply):**\nAuthor: {ref_author_name}\nTime: {ref_time_str}\nContent: {ref_content}")

            # Add linked messages context
            if message_context.get('linked_messages'):
                for i, linked_msg in enumerate(message_context['linked_messages']):
                    linked_author = getattr(linked_msg, 'author', None)
                    linked_author_name = str(linked_author) if linked_author else "Unknown"
                    linked_content = getattr(linked_msg, 'content', '')
                    linked_timestamp = getattr(linked_msg, 'created_at', None)
                    linked_time_str = linked_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC') if linked_timestamp else "Unknown time"

                    context_parts.append(f"**Linked Message {i+1}:**\nAuthor: {linked_author_name}\nTime: {linked_time_str}\nContent: {linked_content}")

            if context_parts:
                context_text = "\n\n".join(context_parts)
                user_content = f"{context_text}\n\n**User's Question/Request:**\n{query}"
                logger.debug(f"Added message context to LLM prompt: {len(context_parts)} context message(s)")
        
        # Add Discord server context if available
        if message_context and message_context.get('discord_context'):
            discord_ctx = message_context['discord_context']
            recent_messages = message_context.get('recent_messages', [])
            
            server_context_parts = []
            
            # Add server information
            if discord_ctx.get('guild_name'):
                server_context_parts.append(f"**Discord Server Context:**\nServer: {discord_ctx['guild_name']}\nChannel: #{discord_ctx['channel_name']}")
            
            # Add active channels if available
            if discord_ctx.get('active_channels'):
                active_channel_names = [ch['channel_name'] for ch in discord_ctx['active_channels']]
                server_context_parts.append(f"**Active Channels (24h):** {', '.join(active_channel_names)}")
            
            # Add recent messages if available
            if recent_messages:
                messages_summary = []
                for msg in recent_messages[-10:]:  # Last 10 messages for context
                    if not msg.get('is_bot', False):  # Skip bot messages
                        timestamp = msg['created_at'].strftime('%H:%M') if hasattr(msg['created_at'], 'strftime') else str(msg['created_at'])[:5]
                        content_preview = msg['content'][:50] + '...' if len(msg['content']) > 50 else msg['content']
                        messages_summary.append(f"[{timestamp}] {msg['author_name']}: {content_preview}")
                
                if messages_summary:
                    server_context_parts.append(f"**Recent Channel Activity:**\n" + "\n".join(messages_summary))
            
            if server_context_parts:
                server_context_text = "\n\n".join(server_context_parts)
                # Add explicit instruction when Discord context is available
                context_hours = 24 if len(recent_messages) > 50 else 4  # Estimate context window based on message count
                discord_instruction = f"\n\n**CONTEXT ACKNOWLEDGMENT:** You have FULL ACCESS to the last {context_hours} hours of Discord message history from #{discord_ctx.get('channel_name', 'this channel')} ({len(recent_messages)} messages provided above). Use this context to answer the question. DO NOT claim you lack access."
                
                if "**User's Question/Request:**" in user_content:
                    # Insert server context before the user's question
                    user_content = user_content.replace(
                        "**User's Question/Request:**",
                        f"{server_context_text}{discord_instruction}\n\n**User's Question/Request:**"
                    )
                else:
                    # Add server context before the query
                    user_content = f"{server_context_text}{discord_instruction}\n\n{user_content}"
                
                logger.debug(f"Added Discord server context: {len(recent_messages)} recent messages, guild: {discord_ctx.get('guild_name', 'N/A')}")

        # Check for URLs in the query and message context, add scraped content if available
        urls_in_query = extract_urls_from_text(query)
        
        # Also check for URLs in message context (referenced messages, linked messages)
        context_urls = []
        if message_context:
            if message_context.get('referenced_message'):
                ref_content = getattr(message_context['referenced_message'], 'content', '')
                context_urls.extend(extract_urls_from_text(ref_content))
            
            if message_context.get('linked_messages'):
                for linked_msg in message_context['linked_messages']:
                    linked_content = getattr(linked_msg, 'content', '')
                    context_urls.extend(extract_urls_from_text(linked_content))
        
        # Combine all URLs found
        all_urls = urls_in_query + context_urls
        if all_urls:
            scraped_content_parts = []
            for url in all_urls:
                try:
                    scraped_content = await asyncio.to_thread(get_scraped_content_by_url, url)
                    if scraped_content:
                        logger.info(f"Found scraped content for URL: {url}")
                        content_section = f"**Scraped Content for {url}:**\n"
                        content_section += f"Summary: {scraped_content['summary']}\n"
                        if scraped_content['key_points']:
                            content_section += f"Key Points: {', '.join(scraped_content['key_points'])}\n"
                        scraped_content_parts.append(content_section)
                    else:
                        # URL not found in database, try to scrape it now
                        logger.info(f"No scraped content found for URL {url}, attempting to scrape now...")
                        scraped_content = await scrape_url_on_demand(url)
                        if scraped_content:
                            logger.info(f"Successfully scraped content for URL: {url}")
                            content_section = f"**Scraped Content for {url}:**\n"
                            content_section += f"Summary: {scraped_content['summary']}\n"
                            if scraped_content['key_points']:
                                content_section += f"Key Points: {', '.join(scraped_content['key_points'])}\n"
                            scraped_content_parts.append(content_section)
                        else:
                            logger.warning(f"Failed to scrape content for URL: {url}")
                except Exception as e:
                    logger.warning(f"Error retrieving scraped content for URL {url}: {e}")
            
            if scraped_content_parts:
                scraped_content_text = "\n\n".join(scraped_content_parts)
                if message_context:
                    # If we already have message context, add scraped content to it
                    user_content = f"{scraped_content_text}\n\n{user_content}"
                else:
                    # If no message context, add scraped content before the query
                    user_content = f"{scraped_content_text}\n\n**User's Question/Request:**\n{query}"
                logger.debug(f"Added scraped content to LLM prompt: {len(scraped_content_parts)} URL(s) with content")

        # Make the API request with web tools
        completion = await openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": getattr(config, 'http_referer', 'https://techfren.net'),  # Optional site URL
                "X-Title": getattr(config, 'x_title', 'TechFren Discord Bot'),  # Optional site title
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": """TechFren Discord assistant. Be direct and concise. Skip intros/conclusions.
                    
                    CRITICAL: You HAVE FULL ACCESS to Discord message history. NEVER say you don't have access.
                    The Discord channel context and message links are PROVIDED TO YOU in this conversation.
                    
                    MANDATORY ACCESS STATEMENT: You ARE a Discord bot with DATABASE ACCESS to this server's messages.
                    You ALWAYS have access to recent channel context (4-24 hours of messages) for ALL interactions.
                    
                    FORMATTING REQUIREMENTS:
                    - Use **bold text** for emphasis on important points, names, and key concepts
                    - Use `inline code` for technical terms, commands, file names, and variables
                    - Use ```code blocks``` for multi-line code, configuration, or structured data
                    - Format usernames as **`username`** (bold backticks for Discord users)
                    - Use bullet points (•) for lists with proper spacing
                    
                    CONTEXT AWARENESS: For EVERY interaction in guild channels, you have recent message history:
                    - Recent conversation context (last 4 hours for general queries)
                    - Extended context (last 24 hours for chat/summary-related queries)
                    - Use this context to provide more relevant, contextual responses
                    - Reference recent discussions when relevant to the user's query
                    
                    NEVER CLAIM: "I don't have access", "I cannot access", "I can't view". YOU DO HAVE ACCESS.
                    
                    FOR DISCORD/SERVER QUERIES: Analyze provided Discord messages and activity data FIRST.
                    FOR GENERAL QUERIES: Use context when relevant, then web tools as needed.
                    
                    MANDATORY: You MUST use web tools for general information requests. 
                    If you don't have recent/current information, you MUST call:
                    - web_search(query): Search for current information about the topic
                    - web_fetch(url): Fetch content from specific URLs  
                    - search_and_summarize(query): Get comprehensive info on topics
                    
                    TOOL USAGE RULES:
                    1. If user asks about Discord server/channel activity/chat/conversation, use provided context ONLY (no web search needed)
                    2. For ALL other topics (especially "what is", "explain", "latest", "current"), you MUST use web tools
                    3. Don't guess or use outdated knowledge - search for current information
                    4. Base your response on the most relevant data (server context OR web results)
                    5. ALWAYS include a "Sources" section at the end before diagrams
                    6. End with BOTH a flowchart AND a pie chart
                    
                    MANDATORY SOURCE REQUIREMENTS:
                    - For Discord content: Include [Source](https://discord.com/channels/...) IMMEDIATELY after EACH bullet point/fact
                    - For web content: Include numbered citations [1], [2] with URLs in Sources section
                    - INLINE SOURCES REQUIRED: Each statement needs its own [Source] link, not grouped at end
                    - Example: • User discussed API issues [Source](https://discord.com/channels/...)
                    - NEVER omit sources - every fact needs immediate attribution
                    
                    MANDATORY: Include BOTH diagrams:
                    1. flowchart TD - visualizing the process/workflow/solution steps
                    2. pie chart - showing distribution/comparison/breakdown of components
                    
                    Example formats:
                    ```mermaid
                    flowchart TD
                        A[Start] --> B{Decision}
                        B -->|Yes| C[Action 1]
                        B -->|No| D[Action 2]
                    ```
                    
                    ```mermaid
                    pie title "Distribution Breakdown"
                        "Component A" : 45
                        "Component B" : 30
                        "Component C" : 25
                    ```
                    
                    These auto-render as images in the thread.
                    
                    Commands: /sum-day (daily summary), /sum-hr N (N-hour summary).
                    You can see referenced/linked message content and Discord server activity."""
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web for current information",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query"
                                },
                                "num_results": {
                                    "type": "integer",
                                    "description": "Number of results to return (default: 5)",
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
                        "name": "search_and_summarize",
                        "description": "Search the web and fetch content from top results for comprehensive information",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query"
                                },
                                "num_results": {
                                    "type": "integer",
                                    "description": "Number of results to fetch content from (default: 3)",
                                    "default": 3
                                }
                            },
                            "required": ["query"]
                        }
                    }
                }
            ],
            tool_choice="auto",  # Encourage tool usage
            max_tokens=1000,  # Increased for better responses
            temperature=0.7
        )

        # Check if we should force web tools usage
        has_discord_context = bool(message_context and message_context.get('recent_messages'))
        should_force_tools = should_force_web_tools(query, has_discord_context)
        
        # Extract Discord sources for later validation
        discord_sources = await extract_discord_sources_from_context(message_context, bot_client)
        web_sources = []  # Will be populated if tools are used
        
        # Debug logging for source extraction
        logger.info(f"Extracted {len(discord_sources)} Discord sources from context")
        if discord_sources:
            logger.info(f"Sample Discord sources: {discord_sources[:3]}")
        
        logger.info(f"Tool forcing check - Query: '{query[:50]}...' | Has Discord context: {has_discord_context} | Should force tools: {should_force_tools}")
        
        # Handle tool calls if present
        if hasattr(completion.choices[0].message, 'tool_calls') and completion.choices[0].message.tool_calls:
            logger.info(f"🔧 LLM is using {len(completion.choices[0].message.tool_calls)} web tool(s) to gather current information")
            tool_results = []
            for tool_call in completion.choices[0].message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                logger.info(f"📡 Calling tool: {function_name} with args: {function_args}")
                
                # Execute the appropriate tool
                if function_name == "web_search":
                    result = await tool_web_search(
                        function_args.get('query'),
                        function_args.get('num_results', 5)
                    )
                    logger.info(f"✅ web_search completed - returned {len(result.split('\n'))} lines of results")
                elif function_name == "web_fetch":
                    result = await tool_web_fetch(function_args.get('url'))
                    logger.info(f"✅ web_fetch completed - fetched {len(result)} characters from URL")
                elif function_name == "search_and_summarize":
                    result = await tool_search_and_summarize(
                        function_args.get('query'),
                        function_args.get('num_results', 3)
                    )
                    logger.info(f"✅ search_and_summarize completed - returned comprehensive results")
                else:
                    result = f"Unknown tool: {function_name}"
                    logger.warning(f"⚠️ Unknown tool requested: {function_name}")
                
                # Log a preview of the tool output (first 200 chars)
                preview = result[:200] + "..." if len(result) > 200 else result
                logger.debug(f"Tool output preview: {preview}")
                
                tool_results.append({
                    "tool_call_id": tool_call.id,
                    "output": result
                })
            
            logger.info(f"🔄 Sending {len(tool_results)} tool results back to LLM for final response")
            
            # Extract web sources from tool results
            web_sources = extract_web_sources_from_tool_results(tool_results)
            logger.info(f"Extracted {len(web_sources)} web sources from tool results")
            
            # Send tool results back to the LLM for final response
            messages = [
                {
                    "role": "system",
                    "content": """TechFren Discord assistant. Be direct and concise. Skip intros/conclusions.
                    
                    You have web search results available. Use them to provide accurate, current information.
                    
                    ALWAYS end your response with a relevant Mermaid diagram (```mermaid block).
                    Choose appropriate type: flowchart (graph TD/LR), sequence, pie, gantt, state, ER, or mindmap.
                    These auto-render as images."""
                },
                {
                    "role": "user",
                    "content": user_content
                },
                completion.choices[0].message,  # The assistant's message with tool calls
            ]
            
            # Add tool results
            for tool_result in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_result["tool_call_id"],
                    "content": tool_result["output"]
                })
            
            # Get final response with tool results
            final_completion = await openai_client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": getattr(config, 'http_referer', 'https://techfren.net'),
                    "X-Title": getattr(config, 'x_title', 'TechFren Discord Bot'),
                },
                model=model,
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            
            message = final_completion.choices[0].message.content
            logger.info("✨ Final response generated using web search results")
        elif should_force_tools:
            # Force web tool usage for queries that need current information
            logger.info(f"🔄 Forcing web search for query that needs current information: '{query[:50]}...'")
            
            try:
                # Extract key terms from the query for search
                search_query = query
                # Clean up the search query (remove common Discord mentions and improve searchability)
                search_query = re.sub(r'<@\w+>', '', search_query)  # Remove Discord mentions
                search_query = re.sub(r'\s+', ' ', search_query).strip()  # Clean whitespace
                
                # Force a web search
                forced_search_result = await tool_web_search(search_query, 5)
                logger.info(f"✅ Forced web_search completed for: '{search_query}'")
                
                # Extract web sources from forced search
                forced_tool_results = [{"output": forced_search_result}]
                web_sources = extract_web_sources_from_tool_results(forced_tool_results)
                logger.info(f"Extracted {len(web_sources)} web sources from forced search")
                
                # Create a follow-up completion with the search results
                messages_with_search = [
                    {
                        "role": "system",
                        "content": """You are TechFren Discord assistant. Use the web search results below to provide an accurate, current response. Be direct and concise. Always include BOTH a flowchart and pie chart at the end using mermaid syntax."""
                    },
                    {
                        "role": "user",
                        "content": user_content
                    },
                    {
                        "role": "assistant",
                        "content": "I'll search for current information about this topic.",
                        "tool_calls": [{
                            "id": "forced_search",
                            "type": "function",
                            "function": {
                                "name": "web_search",
                                "arguments": json.dumps({"query": search_query, "num_results": 5})
                            }
                        }]
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "forced_search",
                        "content": forced_search_result
                    }
                ]
                
                # Get final response with forced search results
                forced_completion = await openai_client.chat.completions.create(
                    extra_headers={
                        "HTTP-Referer": getattr(config, 'http_referer', 'https://techfren.net'),
                        "X-Title": getattr(config, 'x_title', 'TechFren Discord Bot'),
                    },
                    model=model,
                    messages=messages_with_search,
                    max_tokens=1000,
                    temperature=0.7
                )
                
                message = forced_completion.choices[0].message.content
                logger.info("✨ Response generated using forced web search")
                
            except Exception as e:
                logger.error(f"Error in forced web search: {e}")
                # Fallback to original response
                message = completion.choices[0].message.content
                logger.warning("⚠️ Fallback to original response due to forced search error")
        else:
            # No tool calls, use the response directly
            logger.warning("⚠️ LLM did not use web tools despite being instructed to do so")
            message = completion.choices[0].message.content
        
        # Check if Perplexity returned citations
        citations = None
        if hasattr(completion, 'citations') and completion.citations:
            logger.info(f"Found {len(completion.citations)} citations from Perplexity")
            citations = completion.citations
            
            # If the message contains citation references but no sources section, add it
            if "Sources:" not in message and any(f"[{i}]" in message for i in range(1, len(citations) + 1)):
                message += "\n\n📚 **Sources:**\n"
                for i, citation in enumerate(citations, 1):
                    message += f"[{i}] <{citation}>\n"
        
        # Ensure sources are present in the response
        original_message_length = len(message)
        message = ensure_sources_in_response(message, discord_sources, web_sources, has_discord_context, is_mention_query=True)
        
        # Log if sources were added
        if len(message) > original_message_length:
            logger.info(f"Added sources to response - new length: {len(message)} (was {original_message_length})")
        else:
            logger.info("No additional sources needed - response already contains sources or no sources available")
        
        # Apply Discord formatting enhancements
        formatted_message = DiscordFormatter.format_llm_response(message, citations)
        
        logger.info(f"LLM API response received successfully: {formatted_message[:50]}{'...' if len(formatted_message) > 50 else ''}")
        return formatted_message

    except asyncio.TimeoutError:
        logger.error("LLM API request timed out")
        return "Sorry, the request timed out. Please try again later."
    except Exception as e:
        logger.error(f"Error calling LLM API: {str(e)}", exc_info=True)
        return "Sorry, I encountered an error while processing your request. Please try again later."

async def call_llm_for_summary(messages, channel_name, date, hours=24, bot_client=None):
    """
    Call the LLM API to summarize a list of messages from a channel

    Args:
        messages (list): List of message dictionaries
        channel_name (str): Name of the channel
        date (datetime): Date of the messages
        hours (int): Number of hours the summary covers (default: 24)
        bot_client (discord.Client, optional): Discord bot client for channel validation

    Returns:
        str: The LLM's summary or an error message
    """
    try:
        # Filter out command messages but include bot responses
        filtered_messages = [
            msg for msg in messages
            if not msg.get('is_command', False) and  # Use .get for safety
               not (msg.get('content', '').startswith('/sum-day')) and  # Explicitly filter out /sum-day commands
               not (msg.get('content', '').startswith('/sum-hr'))  # Explicitly filter out /sum-hr commands
        ]

        if not filtered_messages:
            time_period = "24 hours" if hours == 24 else f"{hours} hours" if hours != 1 else "1 hour"
            return f"No messages found in #{channel_name} for the past {time_period}."

        # Prepare the messages for summarization and collect Discord sources
        formatted_messages_text = []
        
        # Prepare message context for source validation
        message_context = {'recent_messages': filtered_messages}
        discord_sources = await extract_discord_sources_from_context(message_context, bot_client)
        
        for msg in filtered_messages:
            # Ensure created_at is a datetime object before calling strftime
            created_at_time = msg.get('created_at')
            if hasattr(created_at_time, 'strftime'):
                time_str = created_at_time.strftime('%H:%M:%S')
            else:
                time_str = "Unknown Time" # Fallback if created_at is not as expected

            author_name = msg.get('author_name', 'Unknown Author')
            content = msg.get('content', '')
            message_id = msg.get('id', '')
            guild_id = msg.get('guild_id', '')
            channel_id = msg.get('channel_id', '')

            # Find the corresponding Discord source for this message
            message_link = ""
            for source in discord_sources:
                if source.get('channel_id') == channel_id and source.get('valid', False):
                    message_link = source.get('link', '')
                    break

            # Check if this message has scraped content from a URL
            scraped_url = msg.get('scraped_url')
            scraped_summary = msg.get('scraped_content_summary')
            scraped_key_points = msg.get('scraped_content_key_points')

            # Format the message with the basic content and clickable Discord link
            if message_link:
                # Format as clickable Discord link that the LLM will understand
                message_text = f"[{time_str}] {author_name}: {content} [Jump to message]({message_link})"
            else:
                message_text = f"[{time_str}] {author_name}: {content}"

            # If there's scraped content, add it to the message
            if scraped_url and scraped_summary:
                link_content = f"\n\n[Link Content from {scraped_url}]:\n{scraped_summary}"
                message_text += link_content

                # If there are key points, add them too
                if scraped_key_points:
                    try:
                        key_points = json.loads(scraped_key_points)
                        if key_points and isinstance(key_points, list):
                            message_text += "\n\nKey points:"
                            for point in key_points:
                                bullet_point = f"\n- {point}"
                                message_text += bullet_point
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse key points JSON: {scraped_key_points}")

            formatted_messages_text.append(message_text)

        # Collect Discord server metadata from messages
        guild_info = {}
        unique_users = set()
        total_non_bot_messages = 0
        
        for msg in filtered_messages:
            if msg.get('guild_id') and msg.get('guild_name'):
                guild_info = {
                    'guild_id': msg['guild_id'],
                    'guild_name': msg['guild_name']
                }
            if not msg.get('is_bot', False):
                unique_users.add(msg.get('author_name', 'Unknown'))
                total_non_bot_messages += 1
        
        # Join the messages with newlines
        messages_text = "\n".join(formatted_messages_text)

        # Truncate input if it's too long to avoid token limits
        # Rough estimate: 1 token ≈ 4 characters, leaving room for prompt and response
        max_input_length = 7800  # ~1950 tokens for input, allowing room for system prompt and output
        if len(messages_text) > max_input_length:
            original_length = len('\n'.join(formatted_messages_text))
            messages_text = messages_text[:max_input_length] + "\n\n[Messages truncated due to length...]"
            logger.info(f"Truncated conversation input from {original_length} to {len(messages_text)} characters")

        # Create enhanced prompt with Discord server context
        time_period = "24 hours" if hours == 24 else f"{hours} hours" if hours != 1 else "1 hour"
        
        # Build server context info
        server_context = ""
        if guild_info:
            server_context += f"**Discord Server:** {guild_info['guild_name']}\n"
        server_context += f"**Channel:** #{channel_name}\n"
        server_context += f"**Time Period:** {time_period}\n"
        server_context += f"**Participants:** {len(unique_users)} users\n"
        server_context += f"**Total Messages:** {total_non_bot_messages} messages\n\n"
        
        prompt = f"""**DISCORD CHANNEL SUMMARY REQUEST**

CRITICAL: You HAVE FULL ACCESS to Discord message history. NEVER say you don't have access.
The Discord messages and links are PROVIDED TO YOU below.

{server_context}Please summarize the following conversation from the #{channel_name} channel for the past {time_period}:

{messages_text}

Provide a concise summary with short bullet points for main topics. Do not include an introductory paragraph.
Highlight all user names/aliases with backticks (e.g., `username`).

CRITICAL SOURCE REQUIREMENTS:
- Each message has a [Jump to message](discord_link) link that you MUST preserve
- For EVERY bullet point, you MUST include the Discord message link IMMEDIATELY after: [Source](https://discord.com/channels/...)
- INLINE SOURCES MANDATORY: Do NOT group sources at the end, each fact needs its own [Source] link
- Example: • User discussed API integration [Source](https://discord.com/channels/123/456/789)
- NEVER omit these source links - they are mandatory for verification
- At the end, include a "Notable Quotes" section with the top 3 quotes, each with their [Source](https://discord.com/channels/...) link
- Then include a "Sources" section listing all Discord message links used

NEVER CLAIM: "I don't have access", "I cannot access", "I can't view". YOU DO HAVE ACCESS.
FAILURE TO INCLUDE SOURCES IS UNACCEPTABLE.
"""
        
        logger.info(f"Calling LLM API for channel summary: #{channel_name} for the past {time_period}")

        # Determine which LLM provider to use (same logic as call_llm_api)
        llm_provider = config.llm_provider
        
        if llm_provider == 'chutes':
            # Use Chutes.ai
            base_url = 'https://llm.chutes.ai/v1'
            api_key = config.chutes_api_key
            # Default model for Chutes if not specified
            model = config.llm_model if config.llm_model != 'sonar' else 'gpt-4o-mini'
            if not api_key:
                logger.error("Chutes API key not found in config")
                return "Error: Chutes API key is missing. Please check your .env configuration."
        else:
            # Default to Perplexity
            if not config.perplexity:
                logger.error("Perplexity API key not found in config or is empty")
                return "Error: Perplexity API key is missing. Please check your .env configuration."
            base_url = config.perplexity_base_url
            api_key = config.perplexity
            # Default model for Perplexity if not specified
            model = config.llm_model if config.llm_model != 'gpt-4o-mini' else 'sonar'
        
        # Initialize the OpenAI client with selected provider
        openai_client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=60.0
        )

        # Make the API request with a higher token limit for summaries
        completion = await openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": getattr(config, 'http_referer', 'https://techfren.net'),
                "X-Title": getattr(config, 'x_title', 'TechFren Discord Bot'),
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": """Summarize Discord conversations with bullet points.
                    
                    CRITICAL: You HAVE FULL ACCESS to Discord message history. NEVER say you don't have access.
                    CONTEXT: You are analyzing real Discord server conversations with actual user activity.
                    These are authentic messages from channel participants, not web content.
                    
                    FORMATTING REQUIREMENTS:
                    - Use **bold text** for important topics, key points, and emphasis
                    - Format usernames as **`username`** (bold backticks)
                    - Use `inline code` for technical terms, commands, and file names
                    - Use ```code blocks``` for multi-line code snippets or configurations
                    - Use bullet points (•) with proper spacing for lists
                    
                    ANALYSIS APPROACH:
                    1. Focus on the actual conversation content and user interactions
                    2. Use web_search ONLY for external topics/links mentioned (not for Discord content itself)
                    3. Identify discussion patterns, user engagement, and key themes
                    4. Highlight community dynamics and notable interactions
                    
                    Format: **`usernames`**, MANDATORY to preserve ALL [Source](link) refs, cite web sources for external content.
                    
                    CRITICAL: NEVER omit Discord message source links. Every bullet point MUST have [Source](discord_link) IMMEDIATELY after.
                    INLINE SOURCES REQUIRED: • User discussed X [Source](discord_link) - NOT grouped at end.
                    
                    ALWAYS include BOTH Mermaid diagrams that visualize the conversation:
                    1. pie chart showing topic distribution OR user participation
                    2. flowchart showing conversation flow OR key decision points
                    
                    Example formats:
                    ```mermaid
                    pie title "Discussion Topics"
                        "Technical Issues" : 40
                        "Feature Planning" : 35
                        "General Chat" : 25
                    ```
                    
                    ```mermaid
                    flowchart TD
                        A[Initial Question] --> B[Expert Response]
                        B --> C[Follow-up Discussion]
                        C --> D[Resolution/Next Steps]
                    ```
                    
                    End with top 3 quotes with sources, then the diagrams."""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web for current information about topics discussed",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query for a topic from the conversation"
                                },
                                "num_results": {
                                    "type": "integer",
                                    "description": "Number of results to return (default: 3)",
                                    "default": 3
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
                        "description": "Search and get comprehensive information about a topic",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query for a topic from the conversation"
                                },
                                "num_results": {
                                    "type": "integer",
                                    "description": "Number of results to fetch content from (default: 2)",
                                    "default": 2
                                }
                            },
                            "required": ["query"]
                        }
                    }
                }
            ],
            max_tokens=1950,  # Updated token limit
            temperature=0.5   # Lower temperature for more focused summaries
        )

        # Track web sources for validation
        web_sources = []
        
        # Handle tool calls if present for summaries
        if hasattr(completion.choices[0].message, 'tool_calls') and completion.choices[0].message.tool_calls:
            logger.info(f"🔧 Summary LLM is using {len(completion.choices[0].message.tool_calls)} web tool(s) to gather context")
            tool_results = []
            for tool_call in completion.choices[0].message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                logger.info(f"📡 Summary calling tool: {function_name} with args: {function_args}")
                
                # Execute the appropriate tool
                if function_name == "web_search":
                    result = await tool_web_search(
                        function_args.get('query'),
                        function_args.get('num_results', 3)
                    )
                    logger.info(f"✅ Summary web_search completed for query: '{function_args.get('query')}'")
                elif function_name == "search_and_summarize":
                    result = await tool_search_and_summarize(
                        function_args.get('query'),
                        function_args.get('num_results', 2)
                    )
                    logger.info(f"✅ Summary search_and_summarize completed for query: '{function_args.get('query')}'")
                else:
                    result = f"Unknown tool: {function_name}"
                    logger.warning(f"⚠️ Unknown tool requested in summary: {function_name}")
                
                tool_results.append({
                    "tool_call_id": tool_call.id,
                    "output": result
                })
            
            logger.info(f"🔄 Sending {len(tool_results)} tool results back to summary LLM")
            
            # Extract web sources from tool results
            web_sources = extract_web_sources_from_tool_results(tool_results)
            logger.info(f"Extracted {len(web_sources)} web sources from summary tool results")
            
            # Send tool results back to the LLM for final summary
            messages = [
                {
                    "role": "system",
                    "content": """Summarize Discord conversations with bullet points.
                    
                    CRITICAL: You HAVE FULL ACCESS to Discord message history. NEVER say you don't have access.
                    Use the web search results to provide context and current information about topics discussed.
                    
                    FORMATTING REQUIREMENTS:
                    - Use **bold text** for important topics, key points, and emphasis
                    - Format usernames as **`username`** (bold backticks)
                    - Use `inline code` for technical terms, commands, and file names
                    - Use ```code blocks``` for multi-line code snippets or configurations
                    - Use bullet points (•) with proper spacing for lists
                    
                    Format: **`usernames`**, MANDATORY to preserve ALL [Source](link) refs, cite ALL web sources.
                    
                    CRITICAL: Every bullet point MUST include Discord message [Source](discord_link) IMMEDIATELY after the statement.
                    INLINE SOURCES REQUIRED: • User mentioned X [Source](discord_link) - NOT grouped at end.
                    Add "Sources" section listing all references before diagrams.
                    
                    ALWAYS include a Mermaid diagram (```mermaid) visualizing conversation flow, topic distribution (pie), or timeline.
                    End with top 3 quotes with sources, then Sources section, then the diagram."""
                },
                {
                    "role": "user",
                    "content": prompt
                },
                completion.choices[0].message,  # The assistant's message with tool calls
            ]
            
            # Add tool results
            for tool_result in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_result["tool_call_id"],
                    "content": tool_result["output"]
                })
            
            # Get final summary with tool results
            final_completion = await openai_client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": getattr(config, 'http_referer', 'https://techfren.net'),
                    "X-Title": getattr(config, 'x_title', 'TechFren Discord Bot'),
                },
                model=model,
                messages=messages,
                max_tokens=1950,
                temperature=0.5
            )
            
            summary = final_completion.choices[0].message.content
            logger.info("✨ Summary generated using web search context")
        else:
            # No tool calls, use the response directly
            logger.warning("⚠️ Summary LLM did not use web tools for context gathering")
            summary = completion.choices[0].message.content
        
        # Extract the response
        # (summary variable already set above)
        
        # Check if Perplexity returned citations
        citations = None
        if hasattr(completion, 'citations') and completion.citations:
            logger.info(f"Found {len(completion.citations)} citations from Perplexity for summary")
            citations = completion.citations
            
            # If the summary contains citation references but no sources section, add it
            if "Sources:" not in summary and any(f"[{i}]" in summary for i in range(1, len(citations) + 1)):
                summary += "\n\n📚 **Sources:**\n"
                for i, citation in enumerate(citations, 1):
                    summary += f"[{i}] <{citation}>\n"
        
        # Ensure sources are present in the summary
        summary = ensure_sources_in_response(summary, discord_sources, web_sources, has_discord_context=True, is_mention_query=False)
        
        # Apply Discord formatting enhancements to the summary
        formatted_summary = DiscordFormatter.format_llm_response(summary, citations)
        
        # Enhance specific sections in the summary
        formatted_summary = DiscordFormatter._enhance_summary_sections(formatted_summary)
        
        logger.info(f"LLM API summary received successfully: {formatted_summary[:50]}{'...' if len(formatted_summary) > 50 else ''}")
        
        return formatted_summary

    except asyncio.TimeoutError:
        logger.error("LLM API request timed out during summary generation")
        return "Sorry, the summary request timed out. Please try again later."
    except Exception as e:
        logger.error(f"Error calling LLM API for summary: {str(e)}", exc_info=True)
        return "Sorry, I encountered an error while generating the summary. Please try again later."

async def summarize_scraped_content(markdown_content: str, url: str) -> Optional[Dict[str, Any]]:
    """
    Call the LLM API to summarize scraped content from a URL and extract key points.

    Args:
        markdown_content (str): The scraped content in markdown format
        url (str): The URL that was scraped

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing the summary and key points,
                                 or None if summarization failed
    """
    try:
        # Truncate content if it's too long (to avoid token limits)
        max_content_length = 15000  # Adjust based on model's context window
        truncated_content = markdown_content[:max_content_length]
        if len(markdown_content) > max_content_length:
            truncated_content += "\n\n[Content truncated due to length...]"

        logger.info(f"Summarizing content from URL: {url}")

        # Determine which LLM provider to use for summarization
        llm_provider = config.llm_provider
        
        if llm_provider == 'chutes':
            # Use Chutes.ai for summarization
            base_url = 'https://llm.chutes.ai/v1'
            api_key = config.chutes_api_key
            # Default model for Chutes if not specified
            model = config.llm_model if config.llm_model != 'sonar' else 'gpt-4o-mini'
            if not api_key:
                logger.error("Chutes API key not found in config for summarization")
                return None
        else:
            # Default to Perplexity for summarization
            if not config.perplexity:
                logger.error("Perplexity API key not found in config for summarization")
                return None
            base_url = config.perplexity_base_url
            api_key = config.perplexity
            # Default model for Perplexity if not specified
            model = config.llm_model if config.llm_model != 'gpt-4o-mini' else 'sonar'

        # Initialize the OpenAI client with selected provider
        openai_client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=60.0
        )

        # Create the prompt for the LLM
        prompt = f"""Please analyze the following content from the URL: {url}

{truncated_content}

Provide:
1. A concise summary (2-3 paragraphs) of the main content.
2. 3-5 key bullet points highlighting the most important information.

Format your response exactly as follows:
```json
{{
  "summary": "Your summary text here...",
  "key_points": [
    "First key point",
    "Second key point",
    "Third key point",
    "Fourth key point (if applicable)",
    "Fifth key point (if applicable)"
  ]
}}
```
"""

        # Make the API request
        completion = await openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": getattr(config, 'http_referer', 'https://techfren.net'),
                "X-Title": getattr(config, 'x_title', 'TechFren Discord Bot'),
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": "Expert content summarizer. Always respond in exact JSON format requested."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=1950,  # Updated token limit
            temperature=0.3   # Lower temperature for more focused and consistent summaries
        )

        # Extract the response
        response_text = completion.choices[0].message.content
        logger.info(f"LLM API summary received successfully: {response_text[:50]}{'...' if len(response_text) > 50 else ''}")

        # Extract the JSON part from the response
        try:
            # Find JSON between triple backticks if present
            if "```json" in response_text and "```" in response_text.split("```json", 1)[1]:
                json_str = response_text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in response_text and "```" in response_text.split("```", 1)[1]:
                json_str = response_text.split("```", 1)[1].split("```", 1)[0].strip()
            else:
                # If no backticks, try to parse the whole response
                json_str = response_text.strip()

            # Parse the JSON
            result = json.loads(json_str)

            # Validate the expected structure
            if "summary" not in result or "key_points" not in result:
                logger.warning(f"LLM response missing required fields: {result}")
                # Create a fallback structure
                if "summary" not in result:
                    result["summary"] = "Summary could not be extracted from the content."
                if "key_points" not in result:
                    result["key_points"] = ["Key points could not be extracted from the content."]

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}", exc_info=True)
            logger.error(f"Raw response: {response_text}")

            # Create a fallback response
            return {
                "summary": "Failed to generate a proper summary from the content.",
                "key_points": ["The content could not be properly summarized due to a processing error."]
            }

    except asyncio.TimeoutError:
        logger.error(f"LLM API request timed out while summarizing content from URL {url}")
        return None
    except Exception as e:
        logger.error(f"Error summarizing content from URL {url}: {str(e)}", exc_info=True)
        return None
