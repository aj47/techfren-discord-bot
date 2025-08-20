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
# Web tools removed - keeping only Discord context and Mermaid functionality

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

# Web tools functionality removed - bot now focuses on Discord context only

# Channel validation removed - using minimal on-demand approach

async def extract_discord_sources_from_context(message_context: Optional[Dict[str, Any]], bot_client=None) -> list[Dict[str, Any]]:
    """
    Extract minimal Discord source data from message context (optimized for speed).
    No API validation - just collect basic message info for on-demand link construction.
    
    Args:
        message_context: The message context containing recent messages
        bot_client: Discord bot client (unused in optimized version)
        
    Returns:
        list[Dict[str, Any]]: List of minimal Discord source objects
    """
    discord_sources = []
    
    if not message_context:
        return discord_sources
    
    # Extract minimal data from recent messages (no API calls)
    recent_messages = message_context.get('recent_messages', [])
    for msg in recent_messages:
        message_id = msg.get('id', '')
        guild_id = msg.get('guild_id', '')
        channel_id = msg.get('channel_id', '')
        author_name = msg.get('author_name', 'Unknown')
        created_at = msg.get('created_at', '')
        
        # Only store if we have the essential IDs
        if message_id and channel_id:
            discord_sources.append({
                'message_id': message_id,
                'guild_id': guild_id,
                'channel_id': channel_id,
                'author': author_name,
                'time': created_at
            })
    
    return discord_sources

# Web source extraction removed along with web tools

def ensure_sources_in_response(response: str, discord_sources: list[Dict[str, Any]], has_discord_context: bool = False, is_mention_query: bool = False) -> str:
    """
    Ensure that Discord sources are included in the response, adding them if missing.
    Optimized version - constructs Discord links on-demand with minimal API usage.
    
    Args:
        response: The LLM response
        discord_sources: List of minimal Discord source objects (message_id, guild_id, channel_id, etc.)
        has_discord_context: Whether Discord context was provided
        is_mention_query: Whether this is a @bot mention query (stricter validation)
        
    Returns:
        str: Response with sources ensured
    """
    # Check if sources section already exists
    has_sources_section = bool(re.search(r'\n\s*\*{0,2}\s*Sources?\s*:?\*{0,2}\s*\n', response, re.IGNORECASE))
    
    # Count Discord links in the response
    discord_link_count = len(re.findall(r'discord\.com/channels/', response))
    
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
    missing_sources_section = missing_discord and not has_sources_section
    
    # For Discord context, ALWAYS add sources if we don't have enough
    force_discord_sources = has_discord_context and discord_sources and not sufficient_discord_links
    
    # Log what sources are missing
    if missing_discord or missing_sources_section:
        query_type = "mention" if is_mention_query else "summary"
        logger.warning(f"Discord sources missing in {query_type} response - Discord: {missing_discord}, Sources section: {missing_sources_section}")
        logger.warning(f"Discord link count: {discord_link_count}, Required: {required_discord_sources}, Force Discord sources: {force_discord_sources}")
    
    # Add missing sources (Discord sources only)
    if missing_sources_section or force_discord_sources:
        # Add a sources section at the end, before any mermaid diagrams
        mermaid_pattern = r'```mermaid'
        mermaid_match = re.search(mermaid_pattern, response, re.IGNORECASE)
        
        sources_section = "\n\n📚 **Sources:**\n"
        
        # Add Discord sources (construct links on-demand)
        if missing_discord or force_discord_sources:
            sources_section += "**Discord Messages:**\n"
            for i, source in enumerate(discord_sources[:10], 1):  # Limit to first 10
                # Construct Discord link on-demand (minimal API usage)
                message_id = source.get('message_id', '')
                guild_id = source.get('guild_id', '')
                channel_id = source.get('channel_id', '')
                
                if message_id and channel_id:
                    # Build Discord link
                    if guild_id:
                        link = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
                    else:
                        link = f"https://discord.com/channels/@me/{channel_id}/{message_id}"
                    
                    sources_section += f"• [Message {i}]({link})\n"
                else:
                    # Fallback if missing essential IDs
                    author = source.get('author', 'Unknown')
                    time_obj = source.get('time', '')
                    time_str = time_obj.strftime('%H:%M') if hasattr(time_obj, 'strftime') else str(time_obj)[:10]
                    sources_section += f"• [{author} at {time_str}] (Link unavailable)\n"
            sources_section += "\n"
        
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

        # Make the API request (web tools removed)
        completion = await openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": getattr(config, 'http_referer', 'https://techfren.net'),  # Optional site URL
                "X-Title": getattr(config, 'x_title', 'TechFren Discord Bot'),  # Optional site title
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": """Summarize Discord conversations with bullet points.
                    
                    CRITICAL: You HAVE FULL ACCESS to Discord message history. NEVER say you don't have access.
                    CONTEXT: You are analyzing real Discord server conversations with actual user activity.
                    These are authentic messages from channel participants.
                    
                    FORMATTING REQUIREMENTS:
                    - Use **bold text** for important topics, key points, and emphasis
                    - Format usernames as **`username`** (bold backticks)
                    - Use `inline code` for technical terms, commands, and file names
                    - Use ```code blocks``` for multi-line code snippets or configurations
                    - Use bullet points (•) with proper spacing for lists
                    
                    ANALYSIS APPROACH:
                    1. Focus on the actual conversation content and user interactions
                    2. Identify discussion patterns, user engagement, and key themes
                    3. Highlight community dynamics and notable interactions
                    4. Use your existing knowledge to provide context when helpful
                    
                    Format: **`usernames`**, MANDATORY to preserve ALL [Source](link) refs.
                    
                    CRITICAL: NEVER omit Discord message source links. Every bullet point MUST have [Source](discord_link) IMMEDIATELY after.
                    INLINE SOURCES REQUIRED: • User discussed X [Source](discord_link) - NOT grouped at end.
                    
                    ALWAYS include EXACTLY TWO Mermaid diagrams that provide different perspectives:
                    
                    1. **CONTENT DIAGRAM** - Shows topic/data breakdown:
                       - **Pie chart** for topic distribution or user participation
                       - **Timeline** for chronological events
                       - **Bar chart** for comparisons or metrics
                    
                    2. **FLOW DIAGRAM** - Shows process/conversation flow:
                       - **Flowchart** for conversation progression
                       - **Sequence diagram** for user interactions
                       - **State diagram** for status changes
                    
                    Example formats:
                    ```mermaid
                    pie title "Discussion Topics"
                        "Technical Issues" : 40
                        "Feature Planning" : 35
                        "General Chat" : 25
                    ```
                    
                    ```mermaid
                    flowchart TD
                        A[User Posts Question] --> B[Community Responds]
                        B --> C{Solution Found?}
                        C -->|Yes| D[Implementation Discussion]
                        C -->|No| E[Further Research]
                        E --> B
                    ```
                    
                    These diagrams are automatically processed: Mermaid blocks are extracted and converted 
                    to PNG images, with text replaced by "📊 *Content + Flow diagrams rendered*" references.
                    
                    End with top 3 quotes with sources, then BOTH diagrams (content first, then flow)."""
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            max_tokens=1000,  # Increased for better responses
            temperature=0.7
        )

        # Extract Discord sources for validation (web tools removed)
        discord_sources = await extract_discord_sources_from_context(message_context, bot_client)
        
        # Debug logging for source extraction
        logger.info(f"Extracted {len(discord_sources)} Discord sources from context")
        if discord_sources:
            logger.info(f"Sample Discord sources: {discord_sources[:3]}")
        
        # Use the response directly (no web tool processing)
        message = completion.choices[0].message.content
        logger.info("✨ Response generated from Discord context and LLM knowledge")
        
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
        
        # Ensure Discord sources are present in the response (web sources removed)
        has_discord_context = bool(message_context and message_context.get('recent_messages'))
        original_message_length = len(message)
        message = ensure_sources_in_response(message, discord_sources, has_discord_context, is_mention_query=True)
        
        # Log if sources were added
        if len(message) > original_message_length:
            logger.info(f"Added Discord sources to response - new length: {len(message)} (was {original_message_length})")
        else:
            logger.info("No additional Discord sources needed - response already contains sources or no sources available")
        
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
                    These are authentic messages from channel participants.
                    
                    FORMATTING REQUIREMENTS:
                    - Use **bold text** for important topics, key points, and emphasis
                    - Format usernames as **`username`** (bold backticks)
                    - Use `inline code` for technical terms, commands, and file names
                    - Use ```code blocks``` for multi-line code snippets or configurations
                    - Use bullet points (•) with proper spacing for lists
                    
                    ANALYSIS APPROACH:
                    1. Focus on the actual conversation content and user interactions
                    2. Identify discussion patterns, user engagement, and key themes
                    3. Highlight community dynamics and notable interactions
                    4. Use your existing knowledge to provide context when helpful
                    
                    Format: **`usernames`**, MANDATORY to preserve ALL [Source](link) refs.
                    
                    CRITICAL: NEVER omit Discord message source links. Every bullet point MUST have [Source](discord_link) IMMEDIATELY after.
                    INLINE SOURCES REQUIRED: • User discussed X [Source](discord_link) - NOT grouped at end.
                    
                    ALWAYS include EXACTLY TWO Mermaid diagrams that provide different perspectives:
                    
                    1. **CONTENT DIAGRAM** - Shows topic/data breakdown:
                       - **Pie chart** for topic distribution or user participation
                       - **Timeline** for chronological events
                       - **Bar chart** for comparisons or metrics
                    
                    2. **FLOW DIAGRAM** - Shows process/conversation flow:
                       - **Flowchart** for conversation progression
                       - **Sequence diagram** for user interactions
                       - **State diagram** for status changes
                    
                    Example formats:
                    ```mermaid
                    pie title "Discussion Topics"
                        "Technical Issues" : 40
                        "Feature Planning" : 35
                        "General Chat" : 25
                    ```
                    
                    ```mermaid
                    flowchart TD
                        A[User Posts Question] --> B[Community Responds]
                        B --> C{Solution Found?}
                        C -->|Yes| D[Implementation Discussion]
                        C -->|No| E[Further Research]
                        E --> B
                    ```
                    
                    These diagrams are automatically processed: Mermaid blocks are extracted and converted 
                    to PNG images, with text replaced by "📊 *Content + Flow diagrams rendered*" references.
                    
                    End with top 3 quotes with sources, then BOTH diagrams (content first, then flow)."""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            # Web tools removed - no tool definitions
            max_tokens=1950,  # Updated token limit
            temperature=0.5   # Lower temperature for more focused summaries
        )

        # Use the response directly (web tools removed from summaries)
        summary = completion.choices[0].message.content
        logger.info("✨ Summary generated from Discord context only")
        
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
        
        # Ensure Discord sources are present in the summary (web sources removed)
        summary = ensure_sources_in_response(summary, discord_sources, has_discord_context=True, is_mention_query=False)
        
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
