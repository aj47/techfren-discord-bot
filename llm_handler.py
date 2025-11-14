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
        Optional[Dict[str, Any]]: Dictionary containing summary (plain text with key points), or None if failed
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

        # Summarize the scraped content (returns plain text with summary and key points)
        summary_text = await summarize_scraped_content(markdown_content, url)
        if not summary_text:
            logger.warning(f"Failed to summarize scraped content for URL: {url}")
            return None

        return {
            'summary': summary_text,
            'key_points': []  # Empty list for backward compatibility
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

        # Check if Perplexity API key exists
        if not hasattr(config, 'perplexity') or not config.perplexity:
            logger.error("Perplexity API key not found in config.py or is empty")
            return "Error: Perplexity API key is missing. Please contact the bot administrator."

# Initialize the OpenAI client with Perplexity base URL
        openai_client = AsyncOpenAI(
            base_url=getattr(config, 'perplexity_base_url', 'https://api.perplexity.ai'),
            api_key=config.perplexity,
            timeout=60.0
        )
        
        # Get the model from config or use default (Perplexity models)
        model = getattr(config, 'llm_model', "sonar")
        
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

        # Make the API request
        completion = await openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": getattr(config, 'http_referer', 'https://techfren.net'),  # Optional site URL
                "X-Title": getattr(config, 'x_title', 'TechFren Discord Bot'),  # Optional site title
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": "You are an assistant bot to the techfren community discord server. A community of AI coding, Open source and technology enthusiasts. \
                    Be direct and concise in your responses. Get straight to the point without introductory or concluding paragraphs. Answer questions directly. \
                    Users can use /sum-day to summarize messages from today, or /sum-hr <hours> to summarize messages from the past N hours (e.g., /sum-hr 6 for past 6 hours). \
                    When users reference or link to other messages, you can see the content of those messages and should refer to them in your response when relevant. \
                    IMPORTANT: If you need to present tabular data, use markdown table format (| header | header |) and it will be automatically converted to a formatted table for Discord. \
                    Keep tables simple with 2-3 columns max. For complex comparisons with many details, use a list format instead of tables. \
                    Wide tables or tables with long content will be automatically reformatted into a card-style vertical layout for better mobile readability. \
                    CRITICAL:Never wrap large parts of your response in a markdown code block (```). Only use code blocks for specific code snippets. Your response text should be plain text with inline formatting."
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            max_tokens=1000,  # Increased for better responses
            temperature=0.7
        )

        # Extract the response
        message = completion.choices[0].message.content

        # Check if Perplexity returned citations
        citations = None
        if hasattr(completion, 'citations') and completion.citations:
            logger.info(f"Found {len(completion.citations)} citations from Perplexity")
            citations = completion.citations

        # Apply Discord formatting enhancements
        # The formatter will convert [1], [2] etc. into clickable hyperlinked footnotes
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

            # Check if this message has image descriptions
            image_descriptions = msg.get('image_descriptions')

            # Format the message with the basic content and clickable Discord link
            if message_link:
                # Format as clickable Discord link that the LLM will understand
                message_text = f"[{time_str}] {author_name}: {content} [Jump to message]({message_link})"
            else:
                message_text = f"[{time_str}] {author_name}: {content}"

            # If there are image descriptions, add them to the message
            if image_descriptions:
                try:
                    images = json.loads(image_descriptions)
                    if images and isinstance(images, list):
                        if len(images) == 1:
                            message_text += f"\n[Image: {images[0]['description']}]"
                        else:
                            message_text += "\n[Images:"
                            for i, img in enumerate(images, 1):
                                message_text += f"\n  {i}. {img['description']}"
                            message_text += "\n]"
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse image descriptions JSON: {image_descriptions}")

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
        max_input_length = 60000  # ~15k tokens for input, allowing room for system prompt and output
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

        # Check if Perplexity API key exists
        if not hasattr(config, 'perplexity') or not config.perplexity:
            logger.error("Perplexity API key not found in config.py or is empty")
            return "Error: Perplexity API key is missing. Please contact the bot administrator."

        # Initialize the OpenAI client with Perplexity base URL
        openai_client = AsyncOpenAI(
            base_url=getattr(config, 'perplexity_base_url', 'https://api.perplexity.ai'),
            api_key=config.perplexity,
            timeout=60.0
        )

        # Get the model from config or use default
        model = getattr(config, 'llm_model', "sonar")

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
                    "content": "You are a helpful assistant that summarizes Discord conversations. IMPORTANT: For each link or topic mentioned, search the web for relevant context and incorporate that information. When users share GitHub repos, YouTube videos, or documentation, search for and include relevant information about those resources. Create concise summaries with short bullet points that combine the Discord messages with web-sourced context. Highlight all user names with backticks. For each bullet point, include both the Discord message source [Source](link) and cite any web sources you found. End with the top 3 most interesting quotes from the conversation, each with their source link. Always search the web to provide additional context about shared links and topics. If you need to present tabular data, use markdown table format (| header | header |) and it will be automatically converted to a formatted table for Discord. Keep tables simple with 2-3 columns max. For complex comparisons, use a list format instead of tables. CRITICAL: Never wrap large parts of your response in a markdown code block (```). Only use code blocks for specific code snippets. Your response text should be plain text with inline formatting. Bold, h2, etc is good"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=2500,  # Increased for very detailed summaries with extensive web context
            temperature=0.5   # Lower temperature for more focused summaries
        )

        # Extract the response
        summary = completion.choices[0].message.content

        # Check if Perplexity returned citations
        citations = None
        if hasattr(completion, 'citations') and completion.citations:
            logger.info(f"Found {len(completion.citations)} citations from Perplexity for summary")
            citations = completion.citations

        # Apply Discord formatting enhancements to the summary
        # The formatter will convert [1], [2] etc. into clickable hyperlinked footnotes
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

async def summarize_scraped_content(markdown_content: str, url: str) -> Optional[str]:
    """
    Call the LLM API to summarize scraped content from a URL.

    Args:
        markdown_content (str): The scraped content in markdown format
        url (str): The URL that was scraped

    Returns:
        Optional[str]: A formatted summary string with key points, or None if summarization failed
    """
    try:
        # Truncate content if it's too long (to avoid token limits)
        max_content_length = 15000  # Adjust based on model's context window
        truncated_content = markdown_content[:max_content_length]
        if len(markdown_content) > max_content_length:
            truncated_content += "\n\n[Content truncated due to length...]"

        logger.info(f"Summarizing content from URL: {url}")

        # Check if Perplexity API key exists
        if not hasattr(config, 'perplexity') or not config.perplexity:
            logger.error("Perplexity API key not found in config.py or is empty")
            return None

        # Initialize the OpenAI client with Perplexity base URL
        openai_client = AsyncOpenAI(
            base_url=getattr(config, 'perplexity_base_url', 'https://api.perplexity.ai'),
            api_key=config.perplexity,
            timeout=60.0
        )

        # Get the model from config or use default
        model = getattr(config, 'llm_model', "sonar")

        # Create the prompt for the LLM
        prompt = f"""Analyze and summarize this content from {url}:

{truncated_content}

Provide a concise summary (2-3 sentences) followed by 3-5 key points as bullet points.
Format your response as plain text with bullet points (use - for bullets).
Do not include an introductory paragraph or title.
Keep the summary brief and focused on the most important information."""

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
                    "content": "You are a helpful assistant that summarizes web content concisely. Create brief summaries with bullet points. Do not use JSON format. Respond with plain text only. CRITICAL: Never wrap your response in a markdown code block (```). Use plain text with inline formatting only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=500,  # Enough for a concise summary with key points
            temperature=0.3   # Lower temperature for more focused and consistent summaries
        )

        # Extract the response
        response_text = completion.choices[0].message.content
        logger.info(f"LLM API summary received successfully: {response_text[:50]}{'...' if len(response_text) > 50 else ''}")

        # Clean up the response
        cleaned_response = response_text.strip()

        # Remove any markdown code block wrappers if present
        if cleaned_response.startswith("```") and cleaned_response.endswith("```"):
            # Remove the code block markers
            lines = cleaned_response.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned_response = "\n".join(lines).strip()

        # Apply Discord formatting enhancements
        formatted_response = DiscordFormatter.format_llm_response(cleaned_response)

        logger.info(f"Formatted scraped content summary: {formatted_response[:50]}{'...' if len(formatted_response) > 50 else ''}")

        return formatted_response

    except asyncio.TimeoutError:
        logger.error(f"LLM API request timed out while summarizing content from URL {url}")
        return None
    except Exception as e:
        logger.error(f"Error summarizing content from URL {url}: {str(e)}", exc_info=True)
        return None
