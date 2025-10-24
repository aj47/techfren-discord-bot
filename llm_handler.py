from openai import AsyncOpenAI
from logging_config import logger
import config  # Assuming config.py is in the same directory or accessible
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
    url_pattern = r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?"
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
            markdown_content = scraped_result.get("markdown", "")

        # Check if the URL is from Twitter/X.com
        elif await is_twitter_url(url):
            logger.info(f"Scraping Twitter/X.com URL on-demand: {url}")
            if hasattr(config, "apify_api_token") and config.apify_api_token:
                scraped_result = await scrape_twitter_content(url)
                if not scraped_result:
                    logger.warning(
                        f"Failed to scrape Twitter content with Apify, falling back to Firecrawl: {url}"
                    )
                    scraped_result = await scrape_url_content(url)
                    markdown_content = (
                        scraped_result if isinstance(scraped_result, str) else ""
                    )
                else:
                    markdown_content = scraped_result.get("markdown", "")
            else:
                scraped_result = await scrape_url_content(url)
                markdown_content = (
                    scraped_result if isinstance(scraped_result, str) else ""
                )

        else:
            # For other URLs, use Firecrawl
            logger.info(f"Scraping URL with Firecrawl on-demand: {url}")
            scraped_result = await scrape_url_content(url)
            markdown_content = scraped_result if isinstance(scraped_result, str) else ""

        if not markdown_content:
            logger.warning(f"No content scraped for URL: {url}")
            return None

        # Summarize the scraped content
        summarized_data = await summarize_scraped_content(markdown_content, url)
        if not summarized_data:
            logger.warning(f"Failed to summarize scraped content for URL: {url}")
            return None

        return {
            "summary": summarized_data.get("summary", ""),
            "key_points": summarized_data.get("key_points", []),
        }

    except Exception as e:
        logger.error(f"Error scraping URL on-demand {url}: {str(e)}", exc_info=True)
        return None


def _prepare_user_content_with_context(query, message_context):
    """Prepare user content with message context."""
    user_content = query
    if not message_context:
        return user_content

    context_parts = []

    # Add thread context if available (from thread memory)
    if message_context.get("thread_context"):
        thread_context = message_context["thread_context"]
        context_parts.append(
            f"**Thread Conversation History:**\n{thread_context}"
        )
        logger.debug("Added thread memory context to LLM prompt")

    # Add referenced message (reply) context
    if message_context.get("referenced_message"):
        ref_msg = message_context["referenced_message"]
        ref_author = getattr(ref_msg, "author", None)
        ref_author_name = str(ref_author) if ref_author else "Unknown"
        ref_content = getattr(ref_msg, "content", "")
        ref_timestamp = getattr(ref_msg, "created_at", None)
        ref_time_str = (
            ref_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
            if ref_timestamp
            else "Unknown time"
        )

        context_parts.append(
            f"**Referenced Message (Reply):**\nAuthor: {ref_author_name}\nTime: {ref_time_str}\nContent: {ref_content}"
        )

    # Add linked messages context
    if message_context.get("linked_messages"):
        for i, linked_msg in enumerate(message_context["linked_messages"]):
            linked_author = getattr(linked_msg, "author", None)
            linked_author_name = (
                str(linked_author) if linked_author else "Unknown"
            )
            linked_content = getattr(linked_msg, "content", "")
            linked_timestamp = getattr(linked_msg, "created_at", None)
            linked_time_str = (
                linked_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
                if linked_timestamp
                else "Unknown time"
            )

            context_parts.append(
                f"**Linked Message {i+1}:**\nAuthor: {linked_author_name}\nTime: {linked_time_str}\nContent: {linked_content}"
            )

    if context_parts:
        context_text = "\n\n".join(context_parts)
        user_content = (
            f"{context_text}\n\n**User's Question/Request:**\n{query}"
        )
        logger.debug(
            f"Added message context to LLM prompt: {len(context_parts)} context message(s)"
        )

    return user_content


async def _get_scraped_content_for_urls(urls_in_query, context_urls):
    """Get scraped content for all URLs found in query and context."""
    all_urls = urls_in_query + context_urls
    if not all_urls:
        return ""

    scraped_content_parts = []
    for url in all_urls:
        try:
            scraped_content = await asyncio.to_thread(
                get_scraped_content_by_url, url
            )
            if scraped_content:
                logger.info(f"Found scraped content for URL: {url}")
                content_section = f"**Scraped Content for {url}:**\n"
                content_section += f"Summary: {scraped_content['summary']}\n"
                if scraped_content["key_points"]:
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
                    if scraped_content["key_points"]:
                        content_section += f"Key Points: {', '.join(scraped_content['key_points'])}\n"
                    scraped_content_parts.append(content_section)
                else:
                    logger.warning(f"Failed to scrape content for URL: {url}")
        except Exception as e:
            logger.warning(f"Error retrieving scraped content for URL {url}: {e}")

    if scraped_content_parts:
        scraped_content_text = "\n\n".join(scraped_content_parts)
        logger.debug(f"Added scraped content to LLM prompt: {len(scraped_content_parts)} URL(s) with content")
        return f"{scraped_content_text}\n\n"
    return ""


async def call_llm_api(query, message_context=None, force_charts=False):
    """
    Call the LLM API with the user's query and return the response

    Args:
        query (str): The user's query text
        message_context (dict, optional): Context containing referenced and linked messages
        force_charts (bool): If True, use chart-focused analysis system

    Returns:
        str: The LLM's response or an error message
    """
    try:
        logger.info(
            f"Calling LLM API with query: {query[:50]}{'...' if len(query) > 50 else ''}"
        )

        # Check if LLM API key exists
        if not hasattr(config, "llm_api_key") or not config.llm_api_key:
            logger.error("LLM API key not found in config.py or is empty")
            return (
                "Error: LLM API key is missing. Please contact the bot administrator.",
                [],
            )

        # Initialize the OpenAI-compatible client
        openai_client = AsyncOpenAI(
            base_url=config.llm_base_url, api_key=config.llm_api_key, timeout=60.0
        )

        # Get the model from config
        model = config.llm_model

        # Prepare the user content with message context if available
        user_content = _prepare_user_content_with_context(query, message_context)

        # Check for URLs in the query and message context, add scraped content if available
        urls_in_query = extract_urls_from_text(query)

        # Get URLs from message context
        context_urls = []
        if message_context:
            if message_context.get("referenced_message"):
                ref_content = getattr(message_context["referenced_message"], "content", "")
                context_urls.extend(extract_urls_from_text(ref_content))

            if message_context.get("linked_messages"):
                for linked_msg in message_context["linked_messages"]:
                    linked_content = getattr(linked_msg, "content", "")
                    context_urls.extend(extract_urls_from_text(linked_content))

        # Add scraped content if URLs are found
        scraped_content_text = await _get_scraped_content_for_urls(urls_in_query, context_urls)
        if scraped_content_text:
            if message_context:
                user_content = f"{scraped_content_text}{user_content}"
            else:
                user_content = f"{scraped_content_text}**User's Question/Request:**\n{query}"

        # Choose system prompt based on analysis type
        if force_charts or _should_use_chart_system(query, user_content):
            system_prompt = _get_chart_analysis_system_prompt()
        else:
            system_prompt = _get_regular_system_prompt()

        # Make the API request
        completion = await openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": getattr(
                    config, "http_referer", "https://techfren.net"
                ),  # Optional site URL
                "X-Title": getattr(
                    config, "x_title", "TechFren Discord Bot"
                ),  # Optional site title
            },
            model=model,  # Use the model from config
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1000,  # Increased for better responses
            temperature=0.7,
        )

        # Extract the response
        message = completion.choices[0].message.content

        # Check if the LLM provider returned citations (optional feature)
        # Some providers like Perplexity support this, others don't
        citations = None
        if hasattr(completion, "citations") and completion.citations:
            logger.info(
                f"Found {len(completion.citations)} citations from LLM provider"
            )
            citations = completion.citations

        # Apply Discord formatting enhancements and extract charts
        # The formatter will convert [1], [2] etc. into clickable hyperlinked footnotes
        # and extract any markdown tables for chart rendering
        formatted_message, chart_data = DiscordFormatter.format_llm_response(
            message, citations
        )

        logger.info(
            f"LLM API response received successfully: {formatted_message[:50]}{'...' if len(formatted_message) > 50 else ''}"
        )
        if chart_data:
            logger.info(f"Extracted {len(chart_data)} chart(s) from LLM response")

        return formatted_message, chart_data

    except asyncio.TimeoutError:
        logger.error("LLM API request timed out")
        return "Sorry, the request timed out. Please try again later.", []
    except Exception as e:
        logger.error(f"Error calling LLM API: {str(e)}", exc_info=True)
        return (
            "Sorry, I encountered an error while processing your request. Please try again later.",
            [],
        )


def _filter_messages_for_summary(messages):
    """Filter out command messages but include bot responses."""
    return [
        msg
        for msg in messages
        if not msg.get("is_command", False)
        and not msg.get("content", "").startswith("/sum-day")
        and not msg.get("content", "").startswith("/sum-hr")
    ]


def _format_message_for_summary(msg):
    """Format a single message for summarization."""
    # Ensure created_at is a datetime object before calling strftime
    created_at_time = msg.get("created_at")
    if hasattr(created_at_time, "strftime"):
        time_str = created_at_time.strftime("%H:%M:%S")
    else:
        time_str = "Unknown Time"

    author_name = msg.get("author_name", "Unknown Author")
    content = msg.get("content", "")
    message_id = msg.get("id", "")
    guild_id = msg.get("guild_id", "")
    channel_id = msg.get("channel_id", "")

    # Generate Discord message link
    message_link = ""
    if message_id and channel_id:
        message_link = generate_discord_message_link(
            guild_id, channel_id, message_id
        )

    # Format the message with the basic content and clickable Discord link
    if message_link:
        return f"[{time_str}] {author_name}: {content} [Jump to message]({message_link})"
    else:
        return f"[{time_str}] {author_name}: {content}"


async def call_llm_for_summary(
    messages, channel_name, date, hours=24, force_charts=False
):
    """
    Call the LLM API to summarize a list of messages from a channel

    Args:
        messages (list): List of message dictionaries
        channel_name (str): Name of the channel
        date (datetime): Date of the messages
        hours (int): Number of hours the summary covers (default: 24)
        force_charts (bool): If True, use chart-focused analysis

    Returns:
        str: The LLM's summary or an error message
    """
    try:
        # Filter out command messages but include bot responses
        filtered_messages = _filter_messages_for_summary(messages)

        if not filtered_messages:
            time_period = (
                "24 hours"
                if hours == 24
                else f"{hours} hours" if hours != 1 else "1 hour"
            )
            return f"No messages found in #{channel_name} for the past {time_period}."

        # Prepare the messages for summarization
        formatted_messages_text = []
        for msg in filtered_messages:
            # Format the basic message
            message_text = _format_message_for_summary(msg)

            # Check if this message has scraped content from a URL
            scraped_url = msg.get("scraped_url")
            scraped_summary = msg.get("scraped_content_summary")
            scraped_key_points = msg.get("scraped_content_key_points")

            # If there's scraped content, add it to the message
            if scraped_url and scraped_summary:
                link_content = (
                    f"\n\n[Link Content from {scraped_url}]:\n{scraped_summary}"
                )
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
                        logger.warning(
                            f"Failed to parse key points JSON: {scraped_key_points}"
                        )

            formatted_messages_text.append(message_text)

        # Join the messages with newlines
        messages_text = "\n".join(formatted_messages_text)

        # Truncate input if it's too long to avoid token limits
        # Rough estimate: 1 token ≈ 4 characters, leaving room for prompt and response
        max_input_length = (
            50000  # Reduced to leave more room for thread context and response
        )
        if len(messages_text) > max_input_length:
            original_length = len("\n".join(formatted_messages_text))
            messages_text = (
                messages_text[:max_input_length]
                + "\n\n[Messages truncated due to length...]"
            )
            logger.info(
                f"Truncated conversation input from {original_length} to {len(messages_text)} characters"
            )

        # Create the prompt for the LLM based on analysis type
        time_period = (
            "24 hours" if hours == 24 else f"{hours} hours" if hours != 1 else "1 hour"
        )

        if force_charts:
            prompt = f"""Analyze the following conversation data from #{channel_name} for the past {time_period}:

{messages_text}

CHART ANALYSIS TASK: Provide quantitative insights with data visualization.

REQUIREMENTS:
1. Create 1-2 data tables showing the most meaningful patterns
2. Count accurately - verify all numbers
3. Use descriptive headers with units
4. Provide brief insights about the patterns

ANALYSIS OPTIONS (choose most relevant):
- User activity: Username | Message Count
- Time patterns: Time Range | Messages
- Topic frequency: Discussion Topic | Mentions
- Content sharing: Content Type | Count
- Technology focus: Technology | References

FORMAT: Brief summary + data table(s) + key insights"""
        else:
            prompt = f"""Summarize the following conversation from #{channel_name} for the past {time_period}:

{messages_text}

SUMMARY REQUIREMENTS:
1. Conversational summary of main topics and discussions
2. Highlight usernames with backticks: `username`
3. Include notable quotes or insights
4. Preserve Discord message links: [Source](https://discord.com/channels/...)
5. Focus on qualitative insights and community interactions

Keep it natural and engaging - this is for community members to understand what they missed."""

        logger.info(
            f"Calling LLM API for channel summary: #{channel_name} for the past {time_period}"
        )

        # Check if LLM API key exists
        if not hasattr(config, "llm_api_key") or not config.llm_api_key:
            logger.error("LLM API key not found in config.py or is empty")
            return (
                "Error: LLM API key is missing. Please contact the bot administrator.",
                [],
            )

        # Initialize the OpenAI-compatible client
        openai_client = AsyncOpenAI(
            base_url=config.llm_base_url, api_key=config.llm_api_key, timeout=60.0
        )

        # Get the model from config
        model = config.llm_model

        # Make the API request with a higher token limit for summaries
        completion = await openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": getattr(config, "http_referer", "https://techfren.net"),
                "X-Title": getattr(config, "x_title", "TechFren Discord Bot"),
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": (
                        _get_chart_analysis_system_prompt()
                        if force_charts
                        else _get_regular_summary_system_prompt()
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=2500,  # Increased for very detailed summaries with extensive web context
            temperature=0.5,  # Lower temperature for more focused summaries
        )

        # Extract the response
        summary = completion.choices[0].message.content

        # Check if the LLM provider returned citations (optional feature)
        # Some providers like Perplexity support this, others don't
        citations = None
        if hasattr(completion, "citations") and completion.citations:
            logger.info(
                f"Found {len(completion.citations)} citations from LLM provider for summary"
            )
            citations = completion.citations

        # Apply Discord formatting enhancements to the summary and extract charts
        # The formatter will convert [1], [2] etc. into clickable hyperlinked footnotes
        # and extract any markdown tables for chart rendering
        formatted_summary, chart_data = DiscordFormatter.format_llm_response(
            summary, citations
        )

        # Enhance specific sections in the summary
        formatted_summary = DiscordFormatter._enhance_summary_sections(
            formatted_summary
        )

        logger.info(
            f"LLM API summary received successfully: {formatted_summary[:50]}{'...' if len(formatted_summary) > 50 else ''}"
        )
        if chart_data:
            logger.info(f"Extracted {len(chart_data)} chart(s) from summary")

        return formatted_summary, chart_data

    except asyncio.TimeoutError:
        logger.error("LLM API request timed out during summary generation")
        return "Sorry, the summary request timed out. Please try again later.", []
    except Exception as e:
        logger.error(f"Error calling LLM API for summary: {str(e)}", exc_info=True)
        return (
            "Sorry, I encountered an error while generating the summary. Please try again later.",
            [],
        )


def _get_regular_summary_system_prompt() -> str:
    """Get the regular summary system prompt focused on qualitative analysis."""
    return """You are a Discord conversation summarizer for the techfren community. Focus on creating engaging, qualitative summaries.

SUMMARY APPROACH:
- Conversational and community-focused tone
- Highlight main discussion topics and themes
- Capture the "feel" of the conversation
- Include interesting insights and notable moments

THREAD CONTEXT AWARENESS:
If thread conversation history is provided, acknowledge ongoing discussions and build upon previous summaries when relevant.

STRUCTURE:
1. Brief overview of main topics discussed
2. Key highlights and interesting points
3. Notable quotes or insights with sources
4. Community interactions and collaborations

FORMATTING:
- Use natural language, not rigid bullet points
- Highlight usernames with backticks: `username`
- Include Discord message links: [Source](https://discord.com/channels/...)
- Focus on storytelling rather than data analysis

TONE: Friendly, informative, and engaging - like telling a friend what they missed in the conversation.

Note: Only include data tables if the conversation naturally contains specific metrics that users shared or discussed."""


def _should_use_chart_system(query: str, full_content: str) -> bool:
    """
    Determine if the query should use the chart analysis system.

    Args:
        query: User's original query
        full_content: Full content including context

    Returns:
        bool: True if chart system should be used
    """
    # Keywords that indicate data analysis requests
    chart_keywords = [
        "analyze",
        "chart",
        "graph",
        "data",
        "statistics",
        "metrics",
        "count",
        "frequency",
        "distribution",
        "comparison",
        "trends",
        "activity",
        "usage",
        "breakdown",
        "top",
        "most",
        "ranking",
        "percentage",
        "ratio",
        "numbers",
        "quantify",
        "measure",
    ]

    # Phrases that strongly indicate chart requests
    chart_phrases = [
        "show me the data",
        "create a chart",
        "visualize",
        "data analysis",
        "how much",
        "how many",
        "what percentage",
        "top users",
        "most active",
        "breakdown by",
        "activity by time",
        "usage statistics",
    ]

    combined_text = (query + " " + full_content).lower()

    # Check for explicit chart keywords
    keyword_matches = sum(1 for keyword in chart_keywords if keyword in combined_text)

    # Check for chart phrases
    phrase_matches = sum(1 for phrase in chart_phrases if phrase in combined_text)

    # Use chart system if multiple indicators or strong phrases
    return keyword_matches >= 2 or phrase_matches >= 1


def _get_chart_analysis_system_prompt() -> str:
    """Get the chart analysis system prompt focused on data visualization."""
    return """You are a data analysis assistant for the techfren community Discord server. Your specialty is creating accurate charts and visualizations.

═══════════════════════════════════════════════════════════
CHART ANALYSIS SYSTEM - DATA VISUALIZATION FOCUS
═══════════════════════════════════════════════════════════

CORE MISSION: Transform conversation data into accurate, meaningful visualizations.

THREAD MEMORY AWARENESS:
If you see "Thread Conversation History" in the context, this is our previous conversation in this thread. Use this context to:
- Reference previous discussions naturally
- Build upon earlier analyses
- Avoid repeating information already covered
- Continue the conversation flow logically

MANDATORY TABLE CREATION:
You MUST create AT LEAST ONE data table for every analysis request.

TABLE FORMAT RULES (CHARACTER-BY-CHARACTER):
✓ Line 1 (Header): | Header1 | Header2 |
✓ Line 2 (Separator): | --- | --- |
✓ Line 3+ (Data): | value1 | value2 |

CRITICAL FORMAT REQUIREMENTS:
✓ ALWAYS start/end rows with pipes: | data |
✓ Separator MUST be: | --- | --- | (spaces around dashes)
✓ Same number of columns in every row
✓ One space after opening | and before closing |

DATA ACCURACY LAWS:
1. COUNT PRECISELY: Actually count occurrences, don't estimate
2. VERIFY TOTALS: Ensure numbers add up correctly
3. CONSISTENT UNITS: All values in same column use same units
4. MEANINGFUL HEADERS: Use descriptive names with units

HEADER REQUIREMENTS:
✓ "Username | Message Count" NOT "User | Count"
✓ "Technology | Mentions" NOT "Item | Value"
✓ "Time Period | Activity" NOT "Time | Data"
✓ Include units: "Usage (%)", "Messages (Count)", "Time (Hours)"

VALUE FORMATTING:
✓ Percentages: "85%" not "0.85"
✓ Large numbers: "1,234" with commas
✓ Time: "14:30" consistent format
✓ Currency: "$100", "€50" with symbols

CHART TYPE OPTIMIZATION:
✓ Percentages that sum to ~100% → Perfect for pie charts
✓ User/item comparisons → Great for bar charts
✓ Time-based data → Ideal for line charts
✓ Rankings → Sort by value, include ranks

ANALYSIS OPTIONS (choose most relevant):
1. User Activity: | Username | Message Count |
2. Time Patterns: | Time Range | Messages |
3. Topic Analysis: | Discussion Topic | Mentions |
4. Content Sharing: | Content Type | Count |
5. Technology Focus: | Technology | References |
6. Engagement: | Metric | Value |

RESPONSE STRUCTURE:
1. Brief context (1-2 sentences)
2. Data table(s) with accurate counts
3. Key insights from the data
4. Notable patterns or trends

PROHIBITED:
✗ Generic headers like "Item", "Value", "Data"
✗ Unverified numbers or estimates
✗ Missing percentage symbols or units
✗ Tables without proper formatting
✗ Code blocks around tables (```table```)

REMEMBER: Tables automatically become visual charts. Accurate data + clear labels = meaningful insights."""


def _get_regular_system_prompt() -> str:
    """Get the regular system prompt for general conversations."""
    return """You are an assistant bot to the techfren community discord server. A community of AI coding, Open source and technology enthusiasts.

CORE BEHAVIOR:
- Be direct and concise
- Get straight to the point without lengthy introductions
- Answer questions directly and helpfully
- Use context from referenced/linked messages when available

THREAD MEMORY AWARENESS:
If you see "Thread Conversation History" in the context, this is our previous conversation in this thread. Use this context to:
- Continue conversations naturally without reintroducing yourself
- Reference previous points and build upon them
- Maintain conversation continuity and flow
- Avoid repeating information already discussed

COMMUNITY FOCUS:
- Support AI, coding, and open source discussions
- Help with technical questions and projects
- Foster collaboration and knowledge sharing
- Maintain a friendly, professional tone

FORMATTING:
- Use Discord markdown effectively
- Highlight usernames with backticks: `username`
- Include relevant links and references
- Use code blocks for actual code snippets only
- Keep responses conversational and engaging

WHEN TO INCLUDE TABLES:
Only create data tables if:
✓ User explicitly asks for data analysis
✓ Response contains specific metrics/statistics
✓ Comparing quantifiable information is essential

OTHERWISE: Focus on qualitative insights, explanations, and natural conversation.

Note: For data analysis requests, use /chart-analysis or similar commands to get detailed visualizations."""


async def summarize_scraped_content(
    markdown_content: str, url: str
) -> Optional[Dict[str, Any]]:
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
        if not hasattr(config, "llm_api_key") or not config.llm_api_key:
            logger.error("LLM API key not found in config.py or is empty")
            return None

        # Initialize the OpenAI-compatible client
        openai_client = AsyncOpenAI(
            base_url=config.llm_base_url, api_key=config.llm_api_key, timeout=60.0
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
                "HTTP-Referer": getattr(config, "http_referer", "https://techfren.net"),
                "X-Title": getattr(config, "x_title", "TechFren Discord Bot"),
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert assistant that summarizes web content and extracts key points. You always respond in the exact JSON format requested.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,  # Limit for content summarization
            temperature=0.3,  # Lower temperature for more focused and consistent summaries
        )

        # Extract the response
        response_text = completion.choices[0].message.content
        logger.info(
            f"LLM API summary received successfully: {response_text[:50]}{'...' if len(response_text) > 50 else ''}"
        )

        # Extract the JSON part from the response
        try:
            # Find JSON between triple backticks if present
            if (
                "```json" in response_text
                and "```" in response_text.split("```json", 1)[1]
            ):
                json_str = (
                    response_text.split("```json", 1)[1].split("```", 1)[0].strip()
                )
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
                    result["summary"] = (
                        "Summary could not be extracted from the content."
                    )
                if "key_points" not in result:
                    result["key_points"] = [
                        "Key points could not be extracted from the content."
                    ]

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}", exc_info=True)
            logger.error(f"Raw response: {response_text}")

            # Create a fallback response
            return {
                "summary": "Failed to generate a proper summary from the content.",
                "key_points": [
                    "The content could not be properly summarized due to a processing error."
                ],
            }

    except asyncio.TimeoutError:
        logger.error(
            f"LLM API request timed out while summarizing content from URL {url}"
        )
        return None
    except Exception as e:
        logger.error(
            f"Error summarizing content from URL {url}: {str(e)}", exc_info=True
        )
        return None
