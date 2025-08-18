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

async def call_llm_api(query, message_context=None):
    """
    Call the LLM API with the user's query and return the response

    Args:
        query (str): The user's query text
        message_context (dict, optional): Context containing referenced and linked messages

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
        user_content = query
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
                    
                    MANDATORY: You MUST use web tools for EVERY response:
                    - web_search(query): Search for current information about the topic
                    - web_fetch(url): Fetch content from specific URLs
                    - search_and_summarize(query): Get comprehensive info on topics
                    
                    ALWAYS:
                    1. First use web_search or search_and_summarize to get current information
                    2. Base your response on the web search results
                    3. End with a relevant Mermaid diagram (```mermaid block)
                    
                    Choose appropriate diagram type: flowchart (graph TD/LR), sequence, pie, gantt, state, ER, or mindmap.
                    These auto-render as images.
                    
                    Commands: /sum-day (daily summary), /sum-hr N (N-hour summary).
                    You can see referenced/linked message content."""
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
            max_tokens=1000,  # Increased for better responses
            temperature=0.7
        )

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

async def call_llm_for_summary(messages, channel_name, date, hours=24):
    """
    Call the LLM API to summarize a list of messages from a channel

    Args:
        messages (list): List of message dictionaries
        channel_name (str): Name of the channel
        date (datetime): Date of the messages
        hours (int): Number of hours the summary covers (default: 24)

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

        # Prepare the messages for summarization
        formatted_messages_text = []
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

            # Generate Discord message link
            message_link = ""
            if message_id and channel_id:
                message_link = generate_discord_message_link(guild_id, channel_id, message_id)

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

        # Join the messages with newlines
        messages_text = "\n".join(formatted_messages_text)

        # Truncate input if it's too long to avoid token limits
        # Rough estimate: 1 token ≈ 4 characters, leaving room for prompt and response
        max_input_length = 7800  # ~1950 tokens for input, allowing room for system prompt and output
        if len(messages_text) > max_input_length:
            original_length = len('\n'.join(formatted_messages_text))
            messages_text = messages_text[:max_input_length] + "\n\n[Messages truncated due to length...]"
            logger.info(f"Truncated conversation input from {original_length} to {len(messages_text)} characters")

        # Create the prompt for the LLM
        time_period = "24 hours" if hours == 24 else f"{hours} hours" if hours != 1 else "1 hour"
        prompt = f"""Please summarize the following conversation from the #{channel_name} channel for the past {time_period}:

{messages_text}

Provide a concise summary with short bullet points for main topics. Do not include an introductory paragraph.
Highlight all user names/aliases with backticks (e.g., `username`).
IMPORTANT: Each message has a [Jump to message](discord_link) link. For each bullet point, preserve these Discord message links at the end in the format: [Source](https://discord.com/channels/...)
At the end, include a section with the top 3 most interesting or notable one-liner quotes from the conversation, each with their source link in the same [Source](https://discord.com/channels/...) format.
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
                    
                    MANDATORY: Use web_search tool to search for context on ALL topics mentioned in the conversation.
                    This provides current information and context for the discussion topics.
                    
                    Format: `usernames`, preserve [Source](link) refs, cite web sources.
                    ALWAYS include a Mermaid diagram (```mermaid) visualizing conversation flow, topic distribution (pie), or timeline.
                    End with top 3 quotes with sources, then the diagram."""
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
            
            # Send tool results back to the LLM for final summary
            messages = [
                {
                    "role": "system",
                    "content": """Summarize Discord conversations with bullet points.
                    Use the web search results to provide context and current information about topics discussed.
                    Format: `usernames`, preserve [Source](link) refs, cite web sources.
                    ALWAYS include a Mermaid diagram (```mermaid) visualizing conversation flow, topic distribution (pie), or timeline.
                    End with top 3 quotes with sources, then the diagram."""
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
