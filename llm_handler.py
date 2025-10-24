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

        # Check if LLM API key exists
        if not hasattr(config, 'llm_api_key') or not config.llm_api_key:
            logger.error("LLM API key not found in config.py or is empty")
            return "Error: LLM API key is missing. Please contact the bot administrator.", []

        # Initialize the OpenAI-compatible client
        openai_client = AsyncOpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            timeout=60.0
        )
        
        # Get the model from config
        model = config.llm_model
        
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
                    "content": """You are an assistant bot to the techfren community discord server. A community of AI coding, Open source and technology enthusiasts.

═══════════════════════════════════════════════════════════
TECHFREN BOT CONSTITUTION - MANDATORY RESPONSE LAWS
═══════════════════════════════════════════════════════════

ARTICLE I - CORE BEHAVIOR
Be direct and concise. Get straight to the point without introductory or concluding paragraphs. Answer questions directly.
Users can use /sum-day or /sum-hr <hours> to get summaries. When users reference or link messages, use that context in your response.

ARTICLE II - DATA VISUALIZATION MANDATE (CRITICAL)
LAW 2.1: ANY response containing numbers, counts, percentages, or quantifiable data MUST include a markdown table.
LAW 2.2: Tables are REQUIRED (not optional) for: comparisons, rankings, statistics, counts, frequencies, measurements, top lists.
LAW 2.3: EXACT TABLE FORMAT (CHARACTER-BY-CHARACTER):
  Line 1 (Header): | Header1 | Header2 |
  Line 2 (Separator): | --- | --- |
  Line 3+ (Data): | value1 | value2 |

  CRITICAL FORMAT RULES:
  ✓ ALWAYS start row with pipe: |
  ✓ ALWAYS end row with pipe: |
  ✓ Separator MUST be: | --- | --- | (with spaces around dashes)
  ✓ Same number of columns in every row
  ✓ One space after opening | and before closing |

  CORRECT EXAMPLE (COPY EXACTLY):
  | User | Messages |
  | --- | --- |
  | alice | 45 |
  | bob | 32 |

  WRONG FORMATS (WILL BREAK):
  ✗ User | Messages (missing leading/trailing pipes)
  ✗ |User|Messages| (missing spaces)
  ✗ |-----|-----| (missing spaces in separator)
  ✗ | User | Messages | (then data without separator row)

LAW 2.4: Keep tables simple: 2-3 columns maximum.

ARTICLE III - AUTOMATIC TABLE TRIGGERS
You MUST create a table when your response includes:
✓ "X users/people did Y" → REQUIRED FORMAT:
  | User | Count |
  | --- | --- |
  | alice | 45 |

✓ "top N items/topics" → REQUIRED FORMAT:
  | Item | Rank |
  | --- | --- |
  | Python | 1 |

✓ "activity by time/hour/day" → REQUIRED FORMAT:
  | Period | Activity |
  | --- | --- |
  | 10:00 | High |

✓ "comparison of X vs Y" → REQUIRED FORMAT:
  | Item | Metric |
  | --- | --- |
  | Option A | 85% |

✓ "statistics/metrics/analytics" → REQUIRED FORMAT:
  | Metric | Value |
  | --- | --- |
  | Total | 127 |

CREATION STEPS:
1. Count columns (e.g., 2 columns: User + Count)
2. Write header with pipes: | User | Count |
3. Write separator (same # of columns): | --- | --- |
4. Write data rows: | alice | 45 |

ARTICLE IV - ENFORCEMENT RULES
PROHIBITED ACTIONS:
✗ NEVER describe quantifiable data in prose when table format is possible
✗ NEVER use bullet lists when data has numbers/values (use tables instead)
✗ NEVER wrap tables or large responses in code blocks (```)
✗ NEVER skip tables because "data is simple" - tables = automatic charts

WHY THIS MATTERS: Tables automatically become visual charts/graphs for Discord users.
This dramatically improves user experience. Compliance is MANDATORY.

ARTICLE V - CODE BLOCKS
Code blocks (```) are ONLY for actual code snippets. Never use them for tables, data, or regular text.
"""
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

        # Check if the LLM provider returned citations (optional feature)
        # Some providers like Perplexity support this, others don't
        citations = None
        if hasattr(completion, 'citations') and completion.citations:
            logger.info(f"Found {len(completion.citations)} citations from LLM provider")
            citations = completion.citations

        # Apply Discord formatting enhancements and extract charts
        # The formatter will convert [1], [2] etc. into clickable hyperlinked footnotes
        # and extract any markdown tables for chart rendering
        formatted_message, chart_data = DiscordFormatter.format_llm_response(message, citations)

        logger.info(f"LLM API response received successfully: {formatted_message[:50]}{'...' if len(formatted_message) > 50 else ''}")
        if chart_data:
            logger.info(f"Extracted {len(chart_data)} chart(s) from LLM response")

        return formatted_message, chart_data

    except asyncio.TimeoutError:
        logger.error("LLM API request timed out")
        return "Sorry, the request timed out. Please try again later.", []
    except Exception as e:
        logger.error(f"Error calling LLM API: {str(e)}", exc_info=True)
        return "Sorry, I encountered an error while processing your request. Please try again later.", []

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
        max_input_length = 60000  # ~15k tokens for input, allowing room for system prompt and output
        if len(messages_text) > max_input_length:
            original_length = len('\n'.join(formatted_messages_text))
            messages_text = messages_text[:max_input_length] + "\n\n[Messages truncated due to length...]"
            logger.info(f"Truncated conversation input from {original_length} to {len(messages_text)} characters")

        # Create the prompt for the LLM
        time_period = "24 hours" if hours == 24 else f"{hours} hours" if hours != 1 else "1 hour"
        prompt = f"""Please summarize the following conversation from the #{channel_name} channel for the past {time_period}:

{messages_text}

═══════════════════════════════════════════════════════════
SUMMARY REQUIREMENTS (MANDATORY)
═══════════════════════════════════════════════════════════

STRUCTURE:
1. Provide concise summary with short bullet points for main topics (no introductory paragraph)
2. Highlight all user names/aliases with backticks (e.g., `username`)
3. Preserve Discord message links: [Source](https://discord.com/channels/...)
4. End with top 3 notable quotes with source links

MANDATORY DATA VISUALIZATION:
You MUST analyze the conversation and create AT LEAST ONE markdown table showing patterns.
Choose the MOST relevant metric from these options:

REQUIRED OPTIONS (pick at least one):

OPTION 1 - User participation:
| User | Messages |
| --- | --- |
| alice | 45 |
| bob | 32 |

OPTION 2 - Time distribution:
| Hour | Activity |
| --- | --- |
| 10:00 | 15 |
| 11:00 | 23 |

OPTION 3 - Topic frequency:
| Topic | Mentions |
| --- | --- |
| AI | 12 |
| Coding | 8 |

OPTION 4 - URL sharing:
| User | Links |
| --- | --- |
| alice | 5 |
| bob | 3 |

COPY THE EXACT FORMAT ABOVE including:
- Pipes at start and end of every line: | xxx |
- Separator row: | --- | --- |
- Spaces around content: | alice | not |alice|

WHY: Tables automatically become visual charts for users. This is REQUIRED, not optional.
Failure to include a table means users miss critical data visualization.
"""
        
        logger.info(f"Calling LLM API for channel summary: #{channel_name} for the past {time_period}")

        # Check if LLM API key exists
        if not hasattr(config, 'llm_api_key') or not config.llm_api_key:
            logger.error("LLM API key not found in config.py or is empty")
            return "Error: LLM API key is missing. Please contact the bot administrator.", []

        # Initialize the OpenAI-compatible client
        openai_client = AsyncOpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            timeout=60.0
        )

        # Get the model from config
        model = config.llm_model

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

        # Check if the LLM provider returned citations (optional feature)
        # Some providers like Perplexity support this, others don't
        citations = None
        if hasattr(completion, 'citations') and completion.citations:
            logger.info(f"Found {len(completion.citations)} citations from LLM provider for summary")
            citations = completion.citations

        # Apply Discord formatting enhancements to the summary and extract charts
        # The formatter will convert [1], [2] etc. into clickable hyperlinked footnotes
        # and extract any markdown tables for chart rendering
        formatted_summary, chart_data = DiscordFormatter.format_llm_response(summary, citations)

        # Enhance specific sections in the summary
        formatted_summary = DiscordFormatter._enhance_summary_sections(formatted_summary)

        logger.info(f"LLM API summary received successfully: {formatted_summary[:50]}{'...' if len(formatted_summary) > 50 else ''}")
        if chart_data:
            logger.info(f"Extracted {len(chart_data)} chart(s) from summary")

        return formatted_summary, chart_data

    except asyncio.TimeoutError:
        logger.error("LLM API request timed out during summary generation")
        return "Sorry, the summary request timed out. Please try again later.", []
    except Exception as e:
        logger.error(f"Error calling LLM API for summary: {str(e)}", exc_info=True)
        return "Sorry, I encountered an error while generating the summary. Please try again later.", []

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

        # Check if LLM API key exists
        if not hasattr(config, 'llm_api_key') or not config.llm_api_key:
            logger.error("LLM API key not found in config.py or is empty")
            return None

        # Initialize the OpenAI-compatible client
        openai_client = AsyncOpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            timeout=60.0
        )

        # Get the model from config
        model = config.llm_model

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
                    "content": "You are an expert assistant that summarizes web content and extracts key points. You always respond in the exact JSON format requested."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=200,  # Limit for content summarization
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
