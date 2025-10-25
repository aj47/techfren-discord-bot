from openai import AsyncOpenAI
from logging_config import logger
import config  # Assuming config.py is in the same directory or accessible
import json
from typing import Optional, Dict, Any, List, Union
import asyncio
import re
from message_utils import generate_discord_message_link
from database import get_scraped_content_by_url
from discord_formatter import DiscordFormatter
import aiohttp
import base64


class ImageContent:
    """Builder pattern for image content in LLM requests."""

    def __init__(self):
        self._images: List[Dict[str, Any]] = []

    def add_image_url(self, url: str, detail: str = "auto") -> "ImageContent":
        """Add an image from a URL."""
        self._images.append({"type": "image_url", "image_url": {"url": url, "detail": detail}})
        return self

    def add_image_base64(self, base64_data: str, media_type: str = "image/jpeg", detail: str = "auto") -> "ImageContent":
        """Add an image from base64 data."""
        data_url = f"data:{media_type};base64,{base64_data}"
        self._images.append({"type": "image_url", "image_url": {"url": data_url, "detail": detail}})
        return self

    def build(self) -> List[Dict[str, Any]]:
        """Build the image content list."""
        return self._images

    def has_images(self) -> bool:
        """Check if any images have been added."""
        return len(self._images) > 0


async def download_image_as_base64(url: str) -> Optional[tuple[str, str]]:
    """
    Download an image and convert to base64.

    Args:
        url: The image URL to download

    Returns:
        Optional[tuple[str, str]]: (base64_data, media_type) or None if failed
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    logger.warning("Failed to download image from %s: HTTP %s", url, response.status)
                    return None

                content_type = response.headers.get("Content-Type", "image/jpeg")
                if not content_type.startswith("image/"):
                    logger.warning("URL %s is not an image (Content-Type: %s)", url, content_type)
                    return None

                image_data = await response.read()
                base64_data = base64.b64encode(image_data).decode("utf-8")
                logger.info("Successfully downloaded and encoded image from %s", url)
                return base64_data, content_type

    except asyncio.TimeoutError:
        logger.warning("Timeout downloading image from %s", url)
        return None
    except Exception as e:
        logger.error("Error downloading image from %s: %s", url, e)
        return None


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
        Optional[Dict[str, Any]]: Dictionary containing summary and key_points, or None if failed  # noqa: E501
    """
    try:
        # Import here to avoid circular imports
        from youtube_handler import is_youtube_url, scrape_youtube_content
        from firecrawl_handler import scrape_url_content
        from apify_handler import is_twitter_url, scrape_twitter_content
        import config

        # Check if the URL is from YouTube
        if await is_youtube_url(url):
            logger.info("Scraping YouTube URL on-demand: %s", url)
            scraped_result = await scrape_youtube_content(url)
            if not scraped_result:
                logger.warning("Failed to scrape YouTube content: %s", url)
                return None
            markdown_content = scraped_result.get("markdown", "")

        # Check if the URL is from Twitter/X.com
        elif await is_twitter_url(url):
            logger.info("Scraping Twitter/X.com URL on-demand: %s", url)
            if hasattr(config, "apify_api_token") and config.apify_api_token:
                scraped_result = await scrape_twitter_content(url)
                if not scraped_result:
                    logger.warning(
                        f"Failed to scrape Twitter content with Apify, falling back to Firecrawl: {url}"  # noqa: E501
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
            logger.info("Scraping URL with Firecrawl on-demand: %s", url)
            scraped_result = await scrape_url_content(url)
            markdown_content = scraped_result if isinstance(scraped_result, str) else ""

        if not markdown_content:
            logger.warning("No content scraped for URL: %s", url)
            return None

        # Summarize the scraped content
        summarized_data = await summarize_scraped_content(markdown_content, url)
        if not summarized_data:
            logger.warning("Failed to summarize scraped content for URL: %s", url)
            return None

        return {
            "summary": summarized_data.get("summary", ""),
            "key_points": summarized_data.get("key_points", []),
        }

    except Exception as e:
        logger.error("Error scraping URL on-demand %s: %s", url, str(e), exc_info=True)
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
        context_parts.append(f"**Thread Conversation History:**\n{thread_context}")
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
            f"**Referenced Message (Reply):**\nAuthor: {ref_author_name}\nTime: {ref_time_str}\nContent: {ref_content}"  # noqa: E501
        )

    # Add linked messages context
    if message_context.get("linked_messages"):
        for i, linked_msg in enumerate(message_context["linked_messages"]):
            linked_author = getattr(linked_msg, "author", None)
            linked_author_name = str(linked_author) if linked_author else "Unknown"
            linked_content = getattr(linked_msg, "content", "")
            linked_timestamp = getattr(linked_msg, "created_at", None)
            linked_time_str = (
                linked_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
                if linked_timestamp
                else "Unknown time"
            )

            context_parts.append(
                f"**Linked Message {
                    i +
                    1}:**\nAuthor: {linked_author_name}\nTime: {linked_time_str}\nContent: {linked_content}"  # noqa: E501
            )

    if context_parts:
        context_text = "\n\n".join(context_parts)
        user_content = f"{context_text}\n\n**User's Question/Request:**\n{query}"
        logger.debug(
            f"Added message context to LLM prompt: {
                len(context_parts)} context message(s)"
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
            scraped_content = await get_scraped_content_by_url(url)
            if scraped_content:
                logger.info("Found scraped content for URL: %s", url)
                content_section = f"**Scraped Content for {url}:**\n"
                content_section += f"Summary: {scraped_content['summary']}\n"
                if scraped_content["key_points"]:
                    content_section += f"Key Points: {
                        ', '.join(
                            scraped_content['key_points'])}\n"
                scraped_content_parts.append(content_section)
            else:
                # URL not found in database, try to scrape it now
                logger.info(
                    f"No scraped content found for URL {url}, attempting to scrape now..."  # noqa: E501
                )
                scraped_content = await scrape_url_on_demand(url)
                if scraped_content:
                    logger.info("Successfully scraped content for URL: %s", url)
                    content_section = f"**Scraped Content for {url}:**\n"
                    content_section += f"Summary: {scraped_content['summary']}\n"
                    if scraped_content["key_points"]:
                        content_section += f"Key Points: {
                            ', '.join(
                                scraped_content['key_points'])}\n"
                    scraped_content_parts.append(content_section)
                else:
                    logger.warning("Failed to scrape content for URL: %s", url)
        except Exception as e:
            logger.warning("Error retrieving scraped content for URL %s: %s", url, e)

    if scraped_content_parts:
        scraped_content_text = "\n\n".join(scraped_content_parts)
        logger.debug(
            f"Added scraped content to LLM prompt: {
                len(scraped_content_parts)} URL(s) with content"
        )
        return f"{scraped_content_text}\n\n"
    return ""


def _validate_llm_api_key():
    """Validate LLM API key exists."""
    if not hasattr(config, "llm_api_key") or not config.llm_api_key:
        logger.error("LLM API key not found in config.py or is empty")
        return False
    return True


def _extract_context_urls(message_context):
    """Extract URLs from message context."""
    context_urls = []
    if message_context:
        if message_context.get("referenced_message"):
            ref_content = getattr(message_context["referenced_message"], "content", "")
            context_urls.extend(extract_urls_from_text(ref_content))

        if message_context.get("linked_messages"):
            for linked_msg in message_context["linked_messages"]:
                linked_content = getattr(linked_msg, "content", "")
                context_urls.extend(extract_urls_from_text(linked_content))
    return context_urls


async def _prepare_user_content_with_urls(query, user_content, message_context):
    """Prepare user content with scraped URL data."""
    urls_in_query = extract_urls_from_text(query)
    context_urls = _extract_context_urls(message_context)

    scraped_content_text = await _get_scraped_content_for_urls(
        urls_in_query, context_urls
    )
    if scraped_content_text:
        if message_context:
            return f"{scraped_content_text}{user_content}"
        else:
            return f"{scraped_content_text}**User's Question/Request:**\n{query}"
    return user_content


def _select_system_prompt(force_charts, query, user_content):
    """Select appropriate system prompt based on analysis type."""
    if force_charts or _should_use_chart_system(query, user_content):
        return _get_chart_analysis_system_prompt()
    else:
        return _get_regular_system_prompt()


async def _make_llm_request(openai_client, model, system_prompt, user_content, image_content: Optional[ImageContent] = None):
    """Make the API request to LLM with optional image support."""
    user_message_content: Union[str, List[Dict[str, Any]]]

    if image_content and image_content.has_images():
        user_message_content = [
            {"type": "text", "text": user_content}
        ] + image_content.build()
        logger.info("Making LLM request with %d image(s)", len(image_content.build()))
    else:
        user_message_content = user_content

    return await openai_client.chat.completions.create(
        extra_headers={
            "HTTP-Referer": getattr(config, "http_referer", "https://techfren.net"),
            "X-Title": getattr(config, "x_title", "TechFren Discord Bot"),
        },
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message_content},
        ],
        max_tokens=1000,
        temperature=0.7,
    )


def _extract_citations(completion):
    """Extract citations from completion if available."""
    if hasattr(completion, "citations") and completion.citations:
        logger.info("Found %d citations from LLM provider", len(completion.citations))
        return completion.citations
    return None


async def _process_images_from_context(message_context) -> Optional[ImageContent]:
    """Extract and process images from message context."""
    if not message_context:
        logger.debug("No message context provided for image processing")
        return None

    logger.debug("Processing images from context. Keys: %s", list(message_context.keys()))

    image_content = ImageContent()
    total_images_found = 0

    if message_context.get("referenced_message"):
        ref_msg = message_context["referenced_message"]
        if hasattr(ref_msg, "attachments"):
            for attachment in ref_msg.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    result = await download_image_as_base64(attachment.url)
                    if result:
                        base64_data, media_type = result
                        image_content.add_image_base64(base64_data, media_type)
                        total_images_found += 1
                        logger.info("Added image from referenced message: %s", attachment.filename)

    if message_context.get("linked_messages"):
        for linked_msg in message_context["linked_messages"]:
            if hasattr(linked_msg, "attachments"):
                for attachment in linked_msg.attachments:
                    if attachment.content_type and attachment.content_type.startswith("image/"):
                        result = await download_image_as_base64(attachment.url)
                        if result:
                            base64_data, media_type = result
                            image_content.add_image_base64(base64_data, media_type)
                            total_images_found += 1
                            logger.info("Added image from linked message: %s", attachment.filename)

    if message_context.get("current_message"):
        current_msg = message_context["current_message"]
        logger.debug("Checking current_message for attachments. Has attachments attr: %s", hasattr(current_msg, 'attachments'))
        if hasattr(current_msg, "attachments"):
            logger.debug("Current message has %d attachment(s)", len(current_msg.attachments))
            for attachment in current_msg.attachments:
                logger.debug("Processing attachment: %s, content_type: %s", attachment.filename, attachment.content_type)
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    result = await download_image_as_base64(attachment.url)
                    if result:
                        base64_data, media_type = result
                        image_content.add_image_base64(base64_data, media_type)
                        total_images_found += 1
                        logger.info("Added image from current message: %s", attachment.filename)
                else:
                    logger.debug("Skipping non-image attachment: %s", attachment.filename)

    if image_content.has_images():
        logger.info("Processed %s image(s) from message context for LLM", total_images_found)
        return image_content
    return None


async def call_llm_api(query, message_context=None, force_charts=False):
    """
    Call the LLM API with the user's query and return the response

    Args:
        query (str): The user's query text
        message_context (dict, optional): Context containing referenced and linked messages  # noqa: E501
        force_charts (bool): If True, use chart-focused analysis system

    Returns:
        str: The LLM's response or an error message
    """
    try:
        has_context = message_context is not None
        has_images_pending = message_context and (
            message_context.get("current_message") or
            message_context.get("referenced_message") or
            message_context.get("linked_messages")
        )
        logger.info(
            f"🔵 LLM CALL: query='{query[:50]}...' context={has_context} potential_images={has_images_pending}"  # noqa: E501
        )

        # Validate API key
        if not _validate_llm_api_key():
            return (
                "Error: LLM API key is missing. Please contact the bot administrator.",
                [],
            )

        # Initialize client
        openai_client = AsyncOpenAI(
            base_url=config.llm_base_url, api_key=config.llm_api_key, timeout=60.0
        )

        # Prepare content
        user_content = _prepare_user_content_with_context(query, message_context)
        user_content = await _prepare_user_content_with_urls(
            query, user_content, message_context
        )

        # Process images from context
        image_content = await _process_images_from_context(message_context)

        # Select system prompt
        system_prompt = _select_system_prompt(force_charts, query, user_content)

        # Log which system is being used
        is_chart_mode = system_prompt == _get_chart_analysis_system_prompt()
        logger.info(f"System mode selected: {'CHART ANALYSIS' if is_chart_mode else 'REGULAR CONVERSATION'}")

        # Make API request
        completion = await _make_llm_request(
            openai_client, config.llm_model, system_prompt, user_content, image_content
        )

        # Extract response and citations
        message = completion.choices[0].message.content
        citations = _extract_citations(completion)

        # Format response
        formatted_message, chart_data = DiscordFormatter.format_llm_response(
            message, citations, user_query=query
        )

        logger.info(
            f"LLM API response received successfully: {formatted_message[:50]}{'...' if len(formatted_message) > 50 else ''}"  # noqa: E501
        )
        logger.info(f"Chart extraction result: {len(chart_data)} chart(s) found")

        # Learn from successful chart requests
        if len(chart_data) > 0 and ("chart" in query.lower() or "graph" in query.lower()):
            learn_from_chart_request(query, success=True)
            logger.info(f"Learning from successful chart request: '{query[:50]}...'")

        # Log a preview of the LLM response for debugging
        if len(chart_data) == 0 and ("chart" in query.lower() or "graph" in query.lower()):
            logger.warning(f"Chart requested but no charts extracted. LLM response preview: {message[:200]}{'...' if len(message) > 200 else ''}")

        return formatted_message, chart_data

    except asyncio.TimeoutError:
        logger.error("LLM API request TIMED OUT - No fallback available")
        raise TimeoutError("LLM API request timed out. Please try again later.")
    except Exception as e:
        logger.error("LLM API FAILED - No fallback available: %s", str(e), exc_info=True)
        raise RuntimeError(f"LLM API call failed: {e}")


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
        message_link = generate_discord_message_link(guild_id, channel_id, message_id)

    # Format the message with the basic content and clickable Discord link
    if message_link:
        return (
            f"[{time_str}] {author_name}: {content} [Jump to message]({message_link})"
        )
    else:
        return f"[{time_str}] {author_name}: {content}"


def _add_scraped_content_to_message(message_text, msg):
    """Add scraped content to message if available."""
    scraped_url = msg.get("scraped_url")
    scraped_summary = msg.get("scraped_content_summary")
    scraped_key_points = msg.get("scraped_content_key_points")

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
                logger.warning("Failed to parse key points JSON: %s", scraped_key_points)

    return message_text


def _truncate_messages_if_needed(messages_text):
    """Truncate input if it's too long to avoid token limits."""
    max_input_length = (
        50000  # Reduced to leave more room for thread context and response
    )
    if len(messages_text) > max_input_length:
        original_length = len(messages_text)
        messages_text = (
            messages_text[:max_input_length]
            + "\n\n[Messages truncated due to length...]"
        )
        logger.info(
            f"Truncated conversation input from {original_length} to {
                len(messages_text)} characters"
        )
    return messages_text


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

            # Add scraped content if available
            message_text = _add_scraped_content_to_message(message_text, msg)

            formatted_messages_text.append(message_text)

        # Join the messages with newlines
        messages_text = "\n".join(formatted_messages_text)

        # Truncate input if it's too long to avoid token limits
        messages_text = _truncate_messages_if_needed(messages_text)

        # Create the prompt for the LLM based on analysis type
        time_period = (
            "24 hours" if hours == 24 else f"{hours} hours" if hours != 1 else "1 hour"
        )

        if force_charts:
            prompt = f"""Analyze the following conversation data from #{channel_name} for the past {time_period}:  # noqa: E501

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
            prompt = f"""Summarize the following conversation from #{channel_name} for the past {time_period}:  # noqa: E501

{messages_text}

SUMMARY REQUIREMENTS:
1. Conversational summary of main topics and discussions
2. Highlight usernames with backticks: `username`
3. Include notable quotes or insights
4. Preserve Discord message links: [Source](https://discord.com/channels/...)
5. Focus on qualitative insights and community interactions

Keep it natural and engaging - this is for community members to understand what they missed."""  # noqa: E501

        logger.info(
            f"Calling LLM API for channel summary: #{channel_name} for the past {time_period}"  # noqa: E501
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
            max_tokens=2500,  # Increased for very detailed summaries with extensive web context  # noqa: E501
            temperature=0.5,  # Lower temperature for more focused summaries
        )

        # Extract the response
        summary = completion.choices[0].message.content

        # Check if the LLM provider returned citations (optional feature)
        # Some providers like Perplexity support this, others don't
        citations = None
        if hasattr(completion, "citations") and completion.citations:
            logger.info(
                f"Found {len(completion.citations)} citations from LLM provider for summary"  # noqa: E501
            )
            citations = completion.citations

        # Apply Discord formatting enhancements to the summary and extract charts
        # The formatter will convert [1], [2] etc. into clickable hyperlinked footnotes
        # and extract any markdown tables for chart rendering
        formatted_summary, chart_data = DiscordFormatter.format_llm_response(
            summary, citations, user_query=None
        )

        # Enhance specific sections in the summary
        formatted_summary = DiscordFormatter._enhance_summary_sections(
            formatted_summary
        )

        logger.info(
            f"LLM API summary received successfully: {formatted_summary[:50]}{'...' if len(formatted_summary) > 50 else ''}"  # noqa: E501
        )
        if chart_data:
            logger.info("Extracted %d chart(s) from summary", len(chart_data))

        return formatted_summary, chart_data

    except asyncio.TimeoutError:
        logger.error("LLM API summary request TIMED OUT - No fallback available")
        raise TimeoutError("Summary generation timed out. Please try again later.")
    except Exception as e:
        logger.error("LLM Summary API FAILED - No fallback available: %s", str(e), exc_info=True)
        raise RuntimeError(f"Summary generation failed: {e}")


def _get_regular_summary_system_prompt() -> str:
    """Get the regular summary system prompt focused on qualitative analysis."""
    return """You are a Discord conversation summarizer for the techfren community. Focus on creating engaging, qualitative summaries.  # noqa: E501

SUMMARY APPROACH:
- Conversational and community-focused tone
- Highlight main discussion topics and themes
- Capture the "feel" of the conversation
- Include interesting insights and notable moments

THREAD CONTEXT AWARENESS:
If thread conversation history is provided, acknowledge ongoing discussions and build upon previous summaries when relevant.  # noqa: E501

STRUCTURE:
1. Brief overview of main topics discussed
2. Key highlights and interesting points
3. Notable quotes or insights with sources
4. Community interactions and collaborations

FORMATTING:
- Use natural language, not rigid bullet points
- Highlight usernames with backticks: `username`
- Reference channels with # prefix: #channel-name (e.g., #general, #tech-talk)
- Include Discord message links: [Source](https://discord.com/channels/...)
- Focus on storytelling rather than data analysis

TONE: Friendly, informative, and engaging - like telling a friend what they missed in the conversation.  # noqa: E501

Note: Only include data tables if the conversation naturally contains specific metrics that users shared or discussed."""  # noqa: E501


def _should_use_chart_system(query: str, full_content: str) -> bool:
    """
    Determine if the query should use the chart analysis system.

    Args:
        query: User's original query
        full_content: Full content including context

    Returns:
        bool: True if chart system should be used
    """
    # Check if user provided tabular data (strong indicator)
    has_table_data = bool(re.search(r'\|.+\|.*\n\|[-:\s|]+\|', query + full_content))
    if has_table_data:
        logger.info("Detected table data in query/content, using chart system")
        return True

    # Get base keywords and enhance with learned ones
    base_chart_keywords = [
        # Core chart/visualization keywords
        "analyze", "analysis", "analyzing", "chart", "charts", "graph", "graphs",
        "plot", "plots", "plotting", "visualize", "visualization", "visualizing",
        "diagram", "diagrams", "figure", "figures", "graphic", "graphics",

        # Data and statistics keywords
        "data", "statistics", "stats", "statistical", "metrics", "measurements",
        "count", "counts", "counting", "frequency", "frequencies", "distribution",
        "breakdown", "breakdowns", "summary", "summaries", "overview", "overviews",

        # Comparison and ranking keywords
        "comparison", "comparisons", "compare", "comparing", "versus", "vs", "against",
        "ranking", "rankings", "rank", "ranked", "top", "bottom", "highest", "lowest",
        "best", "worst", "most", "least", "more", "less", "greater", "smaller",

        # Trend and pattern keywords
        "trends", "trend", "trending", "patterns", "pattern", "changes", "change",
        "increase", "decrease", "growth", "decline", "rise", "fall", "fluctuation",
        "fluctuations", "variation", "variations", "progression", "progressions",

        # Activity and usage keywords
        "activity", "activities", "usage", "usages", "engagement", "interactions",
        "traffic", "visits", "visitors", "users", "participation", "involvement",

        # Quantification keywords
        "quantify", "quantification", "measure", "measuring", "calculate", "calculating",
        "percentage", "percentages", "percent", "ratio", "ratios", "proportion",
        "proportions", "rate", "rates", "average", "averages", "mean", "median", "mode",

        # Time-based keywords
        "time", "times", "period", "periods", "duration", "durations", "hour", "hours",
        "day", "days", "week", "weeks", "month", "months", "year", "years",
        "daily", "weekly", "monthly", "yearly", "quarterly", "annual",

        # Numerical and quantity keywords
        "numbers", "number", "amount", "amounts", "quantity", "quantities", "total",
        "totals", "sum", "sums", "count", "counts", "figure", "figures", "value", "values",

        # Category and grouping keywords
        "category", "categories", "group", "groups", "type", "types", "kind", "kinds",
        "classification", "classifications", "segment", "segments", "division", "divisions",

        # Performance keywords
        "performance", "performances", "score", "scores", "rating", "ratings", "grade",
        "grades", "result", "results", "outcome", "outcomes", "success", "successes",

        # Chart-specific verbs
        "create", "creating", "make", "making", "generate", "generating", "build", "building",
        "draw", "drawing", "render", "rendering", "produce", "producing", "show", "showing",
        "display", "displaying", "present", "presenting", "illustrate", "illustrating",

        # Chart types (individual words)
        "pie", "bar", "line", "scatter", "heatmap", "box", "histogram", "area",
        "bubble", "radar", "polar", "tree", "map", "surface", "candlestick", "funnel",

        # Analysis types
        "correlation", "correlations", "relationship", "relationships", "association",
        "associations", "dependency", "dependencies", "impact", "impacts", "effect", "effects",
    ]

    # Combine base keywords with learned keywords
    chart_keywords = base_chart_keywords + list(_learned_chart_keywords)

    # Phrases that strongly indicate chart requests
    # Get base phrases and enhance with learned ones
    base_chart_phrases = [
        # Chart creation phrases (comprehensive)
        "create a", "make a", "generate a", "build a", "draw a", "render a", "produce a",
        "show me a", "display a", "present a", "give me a", "i need a", "can you make",
        "can you create", "can you generate", "can you show", "can you display",

        # Chart type combinations (with create/make/generate)
        "create a chart", "make a chart", "generate a chart", "build a chart", "draw a chart",
        "create a graph", "make a graph", "generate a graph", "build a graph", "draw a graph",
        "create a pie chart", "make a pie chart", "generate a pie chart", "build a pie chart",
        "create a bar chart", "make a bar chart", "generate a bar chart", "build a bar chart",
        "create a line chart", "make a line chart", "generate a line chart", "build a line chart",
        "create a scatter plot", "make a scatter plot", "generate a scatter plot", "build a scatter plot",
        "create a scatter chart", "make a scatter chart", "generate a scatter chart",
        "create a heatmap", "make a heatmap", "generate a heatmap", "build a heatmap",
        "create a heat map", "make a heat map", "generate a heat map", "build a heat map",
        "create a box plot", "make a box plot", "generate a box plot", "build a box plot",
        "create a boxplot", "make a boxplot", "generate a boxplot", "build a boxplot",
        "create a histogram", "make a histogram", "generate a histogram", "build a histogram",
        "create an area chart", "make an area chart", "generate an area chart", "build an area chart",
        "create a bubble chart", "make a bubble chart", "generate a bubble chart", "build a bubble chart",
        "create a radar chart", "make a radar chart", "generate a radar chart", "build a radar chart",
        "create a pie graph", "make a pie graph", "generate a pie graph", "build a pie graph",
        "create a bar graph", "make a bar graph", "generate a bar graph", "build a bar graph",
        "create a line graph", "make a line graph", "generate a line graph", "build a line graph",

        # Data analysis phrases
        "show me the data", "show me data", "display the data", "present the data",
        "data analysis", "analyze this data", "analyze the data", "data visualization",
        "visualize this", "visualize this data", "visualize the data", "visualize these numbers",
        "turn this into a chart", "turn this into a graph", "chart this data", "graph this data",

        # Question phrases that indicate data requests
        "how much", "how many", "what percentage", "what percent", "what's the breakdown",
        "what's the distribution", "what's the trend", "what are the patterns", "what's the correlation",
        "show me trends", "show patterns", "show breakdown", "show distribution", "show comparison",

        # User activity and ranking phrases
        "top users", "most active", "most engaged", "highest activity", "lowest activity",
        "user activity", "user engagement", "user ranking", "user statistics", "user metrics",
        "activity by user", "engagement by user", "posts by user", "messages by user",

        # Time-based analysis phrases
        "activity by time", "usage over time", "trends over time", "changes over time",
        "daily activity", "weekly activity", "monthly activity", "hourly activity",
        "activity by hour", "activity by day", "activity by week", "activity by month",
        "breakdown by time", "time analysis", "temporal analysis", "time series",

        # Statistical and measurement phrases
        "usage statistics", "user statistics", "activity statistics", "engagement statistics",
        "show statistics", "display stats", "view stats", "check stats", "analyze stats",
        "measure usage", "measure activity", "measure engagement", "calculate metrics",
        "quantify activity", "quantify usage", "count occurrences", "frequency analysis",

        # Comparison and ranking phrases
        "compare this", "comparison between", "versus analysis", "vs comparison",
        "side by side", "compare and contrast", "ranking analysis", "top performers",
        "bottom performers", "highest ranked", "lowest ranked", "sort by", "ordered by",

        # Pattern and trend phrases
        "find patterns", "identify trends", "show trends", "trend analysis", "pattern analysis",
        "spot patterns", "detect trends", "analyze patterns", "growth trends", "decline trends",
        "fluctuation analysis", "seasonal patterns", "cyclical patterns", "anomaly detection",

        # Distribution and breakdown phrases
        "breakdown by", "distribution of", "split by", "categorized by", "grouped by",
        "segment analysis", "category breakdown", "type distribution", "classification analysis",
        "proportion analysis", "percentage breakdown", "share of", "portion of",

        # Performance and results phrases
        "performance analysis", "performance metrics", "results analysis", "outcome analysis",
        "success metrics", "failure analysis", "effectiveness analysis", "efficiency metrics",
        "quality metrics", "performance comparison", "results visualization", "outcome visualization",

        # Visualization and presentation phrases
        "i want to see", "show me visually", "make it visual", "visual representation",
        "graphical representation", "chart representation", "visual summary", "graphical summary",
        "present this visually", "display as chart", "display as graph", "show as visualization",

        # Data request phrases
        "get the data", "fetch the data", "pull the data", "extract data", "data request",
        "need the numbers", "show me numbers", "what are the numbers", "get statistics",
        "provide data", "data summary", "data overview", "data breakdown", "data insights",

        # Analysis request phrases
        "analyze this", "analyze the", "analysis of", "break down this", "examine this",
        "investigate this", "look into this", "study this", "review this", "assess this",

        # Conversion phrases
        "turn this into", "convert this to", "transform this into", "change this to",
        "make this into", "represent this as", "show this as", "display this as",

        # Specific request patterns
        "chart this", "graph this", "plot this", "visualize this", "diagram this",
        "chart the data", "graph the data", "plot the data", "visualize the data",
        "from this image", "from this screenshot", "from this data", "from these numbers",
    ]

    # Combine base phrases with learned phrases
    chart_phrases = base_chart_phrases + list(_learned_chart_phrases)

    combined_text = (query + " " + full_content).lower()

    # Check for explicit chart keywords
    keyword_matches = sum(1 for keyword in chart_keywords if keyword in combined_text)

    # Check for chart phrases
    phrase_matches = sum(1 for phrase in chart_phrases if phrase in combined_text)

    # Debug logging
    logger.debug(f"Chart detection debug:")
    logger.debug(f"   Query: '{query}'")
    logger.debug(f"   Combined text: '{combined_text[:100]}...'")
    logger.debug(f"   Keyword matches: {keyword_matches}")
    logger.debug(f"   Phrase matches: {phrase_matches}")

    # Log which keywords/phrases were found
    found_keywords = [kw for kw in chart_keywords if kw in combined_text]
    found_phrases = [ph for ph in chart_phrases if ph in combined_text]
    if found_keywords:
        logger.debug(f"   Found keywords: {found_keywords}")
    if found_phrases:
        logger.debug(f"   Found phrases: {found_phrases}")

    # Special case: if query contains "create" and "chart" with any words in between
    has_create_and_chart = "create" in query.lower() and "chart" in query.lower()

    # Use chart system if multiple indicators, strong phrases, or create+chart combo
    should_use_chart = keyword_matches >= 2 or phrase_matches >= 1 or has_create_and_chart

    if has_create_and_chart and phrase_matches == 0:
        logger.info(f"Special case: 'create' + 'chart' detected, forcing chart mode")

    logger.info(f"Chart system decision: {'USE CHART SYSTEM' if should_use_chart else 'USE REGULAR SYSTEM'} (keywords: {keyword_matches}, phrases: {phrase_matches}, create+chart: {has_create_and_chart})")

    return should_use_chart


# Dynamic learning system for chart detection
_learned_chart_keywords = set()
_learned_chart_phrases = set()

def learn_from_chart_request(query: str, success: bool = True):
    """
    Learn from successful chart requests to improve detection over time.

    Args:
        query: The user's query that resulted in a chart
        success: Whether the chart creation was successful
    """
    if not success or not query:
        return

    global _learned_chart_keywords, _learned_chart_phrases

    query_lower = query.lower()
    words = query_lower.split()

    # Get base keywords to check against (not the local ones)
    # Define base keywords here for the learning system to use
    base_chart_keywords_for_learning = [
        "analyze", "analysis", "analyzing", "chart", "charts", "graph", "graphs",
        "plot", "plots", "plotting", "visualize", "visualization", "visualizing",
        "diagram", "diagrams", "figure", "figures", "graphic", "graphics",
        "data", "statistics", "stats", "statistical", "metrics", "measurements",
        "count", "counts", "counting", "frequency", "frequencies", "distribution",
        "breakdown", "breakdowns", "summary", "summaries", "overview", "overviews",
        "comparison", "comparisons", "compare", "comparing", "versus", "vs", "against",
        "ranking", "rankings", "rank", "ranked", "top", "bottom", "highest", "lowest",
        "best", "worst", "most", "least", "more", "less", "greater", "smaller",
        "trends", "trend", "trending", "patterns", "pattern", "changes", "change",
        "increase", "decrease", "growth", "decline", "rise", "fall", "fluctuation",
        "fluctuations", "variation", "variations", "progression", "progressions",
        "activity", "activities", "usage", "usages", "engagement", "interactions",
        "traffic", "visits", "visitors", "users", "participation", "involvement",
        "quantify", "quantification", "measure", "measuring", "calculate", "calculating",
        "percentage", "percentages", "percent", "ratio", "ratios", "proportion",
        "proportions", "rate", "rates", "average", "averages", "mean", "median", "mode",
        "time", "times", "period", "periods", "duration", "durations", "hour", "hours",
        "day", "days", "week", "weeks", "month", "months", "year", "years",
        "daily", "weekly", "monthly", "yearly", "quarterly", "annual",
        "numbers", "number", "amount", "amounts", "quantity", "quantities", "total",
        "totals", "sum", "sums", "count", "counts", "figure", "figures", "value", "values",
        "category", "categories", "group", "groups", "type", "types", "kind", "kinds",
        "classification", "classifications", "segment", "segments", "division", "divisions",
        "performance", "performances", "score", "scores", "rating", "ratings", "grade",
        "grades", "result", "results", "outcome", "outcomes", "success", "successes",
        "create", "creating", "make", "making", "generate", "generating", "build", "building",
        "draw", "drawing", "render", "rendering", "produce", "producing", "show", "showing",
        "display", "displaying", "present", "presenting", "illustrate", "illustrating",
        "pie", "bar", "line", "scatter", "heatmap", "box", "histogram", "area",
        "bubble", "radar", "polar", "tree", "map", "surface", "candlestick", "funnel",
        "correlation", "correlations", "relationship", "relationships", "association",
        "associations", "dependency", "dependencies", "impact", "impacts", "effect", "effects",
    ]

    base_chart_phrases_for_learning = [
        "show me the data", "show me data", "display the data", "present the data",
        "data analysis", "analyze this data", "analyze the data", "data visualization",
        "visualize this", "visualize this data", "visualize the data", "visualize these numbers",
        "turn this into a chart", "turn this into a graph", "chart this data", "graph this data",
        "how much", "how many", "what percentage", "what percent", "what's the breakdown",
        "what's the distribution", "what's the trend", "what are the patterns", "what's the correlation",
        "show me trends", "show patterns", "show breakdown", "show distribution", "show comparison",
        "top users", "most active", "most engaged", "highest activity", "lowest activity",
        "user activity", "user engagement", "user ranking", "user statistics", "user metrics",
        "activity by user", "engagement by user", "posts by user", "messages by user",
        "activity by time", "usage over time", "trends over time", "changes over time",
        "daily activity", "weekly activity", "monthly activity", "hourly activity",
        "activity by hour", "activity by day", "activity by week", "activity by month",
        "breakdown by time", "time analysis", "temporal analysis", "time series",
        "usage statistics", "user statistics", "activity statistics", "engagement statistics",
        "show statistics", "display stats", "view stats", "check stats", "analyze stats",
        "measure usage", "measure activity", "measure engagement", "calculate metrics",
        "quantify activity", "quantify usage", "count occurrences", "frequency analysis",
        "compare this", "comparison between", "versus analysis", "vs comparison",
        "side by side", "compare and contrast", "ranking analysis", "top performers",
        "bottom performers", "highest ranked", "lowest ranked", "sort by", "ordered by",
        "find patterns", "identify trends", "show trends", "trend analysis", "pattern analysis",
        "spot patterns", "detect trends", "analyze patterns", "growth trends", "decline trends",
        "fluctuation analysis", "seasonal patterns", "cyclical patterns", "anomaly detection",
        "breakdown by", "distribution of", "split by", "categorized by", "grouped by",
        "segment analysis", "category breakdown", "type distribution", "classification analysis",
        "proportion analysis", "percentage breakdown", "share of", "portion of",
        "performance analysis", "performance metrics", "results analysis", "outcome analysis",
        "success metrics", "failure analysis", "effectiveness analysis", "efficiency metrics",
        "quality metrics", "performance comparison", "results visualization", "outcome visualization",
        "i want to see", "show me visually", "make it visual", "visual representation",
        "graphical representation", "chart representation", "visual summary", "graphical summary",
        "present this visually", "display as chart", "display as graph", "show as visualization",
        "get the data", "fetch the data", "pull the data", "extract data", "data request",
        "need the numbers", "show me numbers", "what are the numbers", "get statistics",
        "provide data", "data summary", "data overview", "data breakdown", "data insights",
        "analyze this", "analyze the", "analysis of", "break down this", "examine this",
        "investigate this", "look into this", "study this", "review this", "assess this",
        "turn this into", "convert this to", "transform this into", "change this to",
        "make this into", "represent this as", "show this as", "display this as",
        "chart this", "graph this", "plot this", "visualize this", "diagram this",
        "chart the data", "graph the data", "plot the data", "visualize the data",
        "from this image", "from this screenshot", "from this data", "from these numbers",
    ]

    # Learn individual words that might indicate chart requests
    for word in words:
        if len(word) > 3 and word.isalpha():  # Only learn meaningful words
            if word not in base_chart_keywords_for_learning and word not in _learned_chart_keywords:
                _learned_chart_keywords.add(word)
                logger.info(f"Learned new chart keyword: '{word}'")

    # Learn 2-word and 3-word phrases
    for i in range(len(words) - 1):
        phrase = f"{words[i]} {words[i+1]}"
        if phrase not in base_chart_phrases_for_learning and phrase not in _learned_chart_phrases:
            _learned_chart_phrases.add(phrase)
            logger.info(f"Learned new chart phrase: '{phrase}'")

    for i in range(len(words) - 2):
        phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
        if phrase not in base_chart_phrases_for_learning and phrase not in _learned_chart_phrases:
            _learned_chart_phrases.add(phrase)
            logger.info(f"Learned new chart phrase: '{phrase}'")

def get_enhanced_chart_keywords():
    """Get chart keywords including learned ones."""
    # Define the base keywords here to avoid scope issues
    base_chart_keywords = [
        "analyze", "analysis", "analyzing", "chart", "charts", "graph", "graphs",
        "plot", "plots", "plotting", "visualize", "visualization", "visualizing",
        "diagram", "diagrams", "figure", "figures", "graphic", "graphics",
        "data", "statistics", "stats", "statistical", "metrics", "measurements",
        "count", "counts", "counting", "frequency", "frequencies", "distribution",
        "breakdown", "breakdowns", "summary", "summaries", "overview", "overviews",
        "comparison", "comparisons", "compare", "comparing", "versus", "vs", "against",
        "ranking", "rankings", "rank", "ranked", "top", "bottom", "highest", "lowest",
        "best", "worst", "most", "least", "more", "less", "greater", "smaller",
        "trends", "trend", "trending", "patterns", "pattern", "changes", "change",
        "increase", "decrease", "growth", "decline", "rise", "fall", "fluctuation",
        "fluctuations", "variation", "variations", "progression", "progressions",
        "activity", "activities", "usage", "usages", "engagement", "interactions",
        "traffic", "visits", "visitors", "users", "participation", "involvement",
        "quantify", "quantification", "measure", "measuring", "calculate", "calculating",
        "percentage", "percentages", "percent", "ratio", "ratios", "proportion",
        "proportions", "rate", "rates", "average", "averages", "mean", "median", "mode",
        "time", "times", "period", "periods", "duration", "durations", "hour", "hours",
        "day", "days", "week", "weeks", "month", "months", "year", "years",
        "daily", "weekly", "monthly", "yearly", "quarterly", "annual",
        "numbers", "number", "amount", "amounts", "quantity", "quantities", "total",
        "totals", "sum", "sums", "count", "counts", "figure", "figures", "value", "values",
        "category", "categories", "group", "groups", "type", "types", "kind", "kinds",
        "classification", "classifications", "segment", "segments", "division", "divisions",
        "performance", "performances", "score", "scores", "rating", "ratings", "grade",
        "grades", "result", "results", "outcome", "outcomes", "success", "successes",
        "create", "creating", "make", "making", "generate", "generating", "build", "building",
        "draw", "drawing", "render", "rendering", "produce", "producing", "show", "showing",
        "display", "displaying", "present", "presenting", "illustrate", "illustrating",
        "pie", "bar", "line", "scatter", "heatmap", "box", "histogram", "area",
        "bubble", "radar", "polar", "tree", "map", "surface", "candlestick", "funnel",
        "correlation", "correlations", "relationship", "relationships", "association",
        "associations", "dependency", "dependencies", "impact", "impacts", "effect", "effects",
    ]
    return base_chart_keywords + list(_learned_chart_keywords)

def get_enhanced_chart_phrases():
    """Get chart phrases including learned ones."""
    # Define the base phrases here to avoid scope issues
    base_chart_phrases = [
        "show me the data", "show me data", "display the data", "present the data",
        "data analysis", "analyze this data", "analyze the data", "data visualization",
        "visualize this", "visualize this data", "visualize the data", "visualize these numbers",
        "turn this into a chart", "turn this into a graph", "chart this data", "graph this data",
        "how much", "how many", "what percentage", "what percent", "what's the breakdown",
        "what's the distribution", "what's the trend", "what are the patterns", "what's the correlation",
        "show me trends", "show patterns", "show breakdown", "show distribution", "show comparison",
        "top users", "most active", "most engaged", "highest activity", "lowest activity",
        "user activity", "user engagement", "user ranking", "user statistics", "user metrics",
        "activity by user", "engagement by user", "posts by user", "messages by user",
        "activity by time", "usage over time", "trends over time", "changes over time",
        "daily activity", "weekly activity", "monthly activity", "hourly activity",
        "activity by hour", "activity by day", "activity by week", "activity by month",
        "breakdown by time", "time analysis", "temporal analysis", "time series",
        "usage statistics", "user statistics", "activity statistics", "engagement statistics",
        "show statistics", "display stats", "view stats", "check stats", "analyze stats",
        "measure usage", "measure activity", "measure engagement", "calculate metrics",
        "quantify activity", "quantify usage", "count occurrences", "frequency analysis",
        "compare this", "comparison between", "versus analysis", "vs comparison",
        "side by side", "compare and contrast", "ranking analysis", "top performers",
        "bottom performers", "highest ranked", "lowest ranked", "sort by", "ordered by",
        "find patterns", "identify trends", "show trends", "trend analysis", "pattern analysis",
        "spot patterns", "detect trends", "analyze patterns", "growth trends", "decline trends",
        "fluctuation analysis", "seasonal patterns", "cyclical patterns", "anomaly detection",
        "breakdown by", "distribution of", "split by", "categorized by", "grouped by",
        "segment analysis", "category breakdown", "type distribution", "classification analysis",
        "proportion analysis", "percentage breakdown", "share of", "portion of",
        "performance analysis", "performance metrics", "results analysis", "outcome analysis",
        "success metrics", "failure analysis", "effectiveness analysis", "efficiency metrics",
        "quality metrics", "performance comparison", "results visualization", "outcome visualization",
        "i want to see", "show me visually", "make it visual", "visual representation",
        "graphical representation", "chart representation", "visual summary", "graphical summary",
        "present this visually", "display as chart", "display as graph", "show as visualization",
        "get the data", "fetch the data", "pull the data", "extract data", "data request",
        "need the numbers", "show me numbers", "what are the numbers", "get statistics",
        "provide data", "data summary", "data overview", "data breakdown", "data insights",
        "analyze this", "analyze the", "analysis of", "break down this", "examine this",
        "investigate this", "look into this", "study this", "review this", "assess this",
        "turn this into", "convert this to", "transform this into", "change this to",
        "make this into", "represent this as", "show this as", "display this as",
        "chart this", "graph this", "plot this", "visualize this", "diagram this",
        "chart the data", "graph the data", "plot the data", "visualize the data",
        "from this image", "from this screenshot", "from this data", "from these numbers",
    ]
    return base_chart_phrases + list(_learned_chart_phrases)

def get_learning_stats():
    """Get statistics about the learning system."""
    # Define base counts to avoid scope issues
    base_keyword_count = 85  # Count of base keywords
    base_phrase_count = 96   # Count of base phrases

    return {
        "learned_keywords": len(_learned_chart_keywords),
        "learned_phrases": len(_learned_chart_phrases),
        "total_keywords": base_keyword_count + len(_learned_chart_keywords),
        "total_phrases": base_phrase_count + len(_learned_chart_phrases),
        "learned_keywords_list": list(_learned_chart_keywords),
        "learned_phrases_list": list(_learned_chart_phrases)
    }

def reset_learning():
    """Reset the learning system (for debugging)."""
    global _learned_chart_keywords, _learned_chart_phrases
    _learned_chart_keywords.clear()
    _learned_chart_phrases.clear()
    logger.info("Learning system reset")


def _get_chart_analysis_system_prompt() -> str:
    """Get the chart analysis system prompt focused on data visualization."""
    return """You are a data analysis assistant for the techfren community Discord server. Your specialty is creating accurate charts and visualizations from conversation data.

═══════════════════════════════════════════════════════════
CHART ANALYSIS SYSTEM - DATA VISUALIZATION MODE
═══════════════════════════════════════════════════════════

CORE MISSION: Transform data into accurate, meaningful visualizations using properly formatted markdown tables.

YOUR JOB IS TO CREATE CHARTS, NOT EXPLAIN HOW:
When users provide data (in any format - table, list, text), you must:
1. Parse and understand the data
2. Create a properly formatted markdown table
3. The system will automatically render it as a visual chart
4. Add brief analysis below the table

DO NOT explain how to make charts - YOU make the chart by creating the table!

THREAD MEMORY AWARENESS:
If you see "Thread Conversation History" in the context, this is our previous conversation in this thread. Use this context to:  # noqa: E501
- Reference previous discussions naturally
- Build upon earlier analyses
- Avoid repeating information already covered
- Continue the conversation flow logically

MANDATORY TABLE CREATION:
You MUST create AT LEAST ONE properly formatted markdown table for EVERY request, including:
- Requests to analyze conversation data
- When users provide data to visualize (in ANY format)
- When users ask for charts or graphs
- When users show you data and ask "create a graph"
- **CRITICAL**: When users upload images and ask for charts/graphs - extract data from the image and create tables!

EXAMPLE - User provides data:
User: "| Month | Savings | | Jan | $250 | | Feb | $80 |"
You MUST respond with: "Here's your savings visualization:

| Month    | Savings |
| -------- | ------- |
| January  | $250    |
| February | $80     |
| March    | $420    |

Your savings show a strong recovery in March after a dip in February."

EXAMPLE - User uploads image with chart request:
User: (uploads image with data) "create a pie chart from this image"
You MUST respond with: "I've extracted the data from your image and created this visualization:

| Category    | Value   | Percentage |
| ----------- | ------- | ---------- |
| Category A  | 45      | 45%        |
| Category B  | 30      | 30%        |
| Category C  | 25      | 25%        |

The data shows Category A represents the largest portion at 45%."

MARKDOWN TABLE FORMAT (STRICT):
```
| Header 1 | Header 2 | Header 3 |
| --- | --- | --- |
| Value 1 | Value 2 | Value 3 |
| Value 4 | Value 5 | Value 6 |
```

CRITICAL FORMAT REQUIREMENTS:
✓ ALWAYS start AND end every row with pipe: | data |
✓ Header separator MUST be: | --- | (exactly 3 dashes, spaces around them)
✓ Same number of columns in EVERY row (header, separator, all data rows)
✓ One space after opening | and one space before closing |
✓ NO code blocks around tables (no ```table or ```markdown)
✓ Tables render directly into visual charts automatically
✓ MEANINGFUL HEADERS: Use descriptive names like "User Name" NOT "Item"
✓ DATA VALUES: Include numbers, percentages, or quantifiable data in cells
✓ CONSISTENT DATA: Each column should contain the same type of information

DATA ACCURACY LAWS:
1. COUNT PRECISELY: Actually count occurrences, don't estimate
2. VERIFY TOTALS: Ensure numbers add up correctly
3. CONSISTENT UNITS: All values in same column use same units
4. MEANINGFUL HEADERS: Use descriptive names with units

HEADER REQUIREMENTS (Be Descriptive):
✓ GOOD: "Username | Message Count" 
✗ BAD: "User | Count"
✓ GOOD: "Technology | Mentions"
✗ BAD: "Item | Value"
✓ GOOD: "Time Period | Activity Level"
✗ BAD: "Time | Data"
✓ Always include units where applicable: "Usage (%)", "Messages", "Duration (Hours)"

VALUE FORMATTING (Consistent and Clear):
✓ Percentages: "85%" or "85.5%" (not 0.85)
✓ Large numbers: "1,234" or "5,678" (use commas)
✓ Time: "14:30" or "2:30 PM" (pick one format, stick with it)
✓ Currency: "$100" or "€50" (symbol first)
✓ Whole numbers for counts: "42" not "42.0"

CHART TYPE OPTIMIZATION (What works best):
BAR CHARTS: User comparisons, rankings, categorical data
   Example: | Username | Messages |
   
PIE CHARTS: Percentages that sum to ~100%, composition breakdown
   Example: | Category | Percentage |
   
LINE CHARTS: Time-based trends, temporal patterns
   Example: | Hour | Activity |
   
METHODOLOGY TABLES: Step-by-step processes, methodologies
   Example: | Step | Action | Purpose |

COMMON ANALYSIS TYPES:
1. User Activity Analysis: | Username | Message Count | Percentage |
2. Time Pattern Analysis: | Time Period | Message Count | Peak Activity |
3. Topic/Tag Analysis: | Topic/Tag | Mentions | Top Contributors |
4. Technology Discussion: | Technology | References | Context |
5. Content Type Breakdown: | Content Type | Count | Percentage |
6. Engagement Metrics: | Metric | Value | Trend |

RESPONSE STRUCTURE (Follow this order):
1. **Brief Context** (1-2 sentences explaining what you're analyzing)
2. **Data Table(s)** (properly formatted markdown tables with accurate data)
3. **Key Insights** (2-3 bullet points highlighting important findings)
4. **Notable Patterns** (trends, anomalies, or interesting observations)

DISCORD FORMATTING BEST PRACTICES:
✓ **Bold** for emphasis: **important point**
✓ *Italic* for subtle emphasis: *note this*
✓ `Backticks` for usernames: `@username`
✓ #channel-name for channels: #general, #tech-talk
✓ > Quote blocks for highlighting specific messages
✓ Links: [Link text](URL) or bare URLs for Discord message links
✓ Lists: Use - or • for bullet points
✗ NO code blocks around tables (tables must be raw markdown)
✗ NO excessive formatting that clutters the message

CRITICAL PROHIBITIONS:
✗ Generic/vague headers: "Item", "Value", "Data", "Thing", "Name", "Description"
✗ Tables with only text and no numbers/percentages/quantifiable data
✗ Estimated or unverified numbers (count precisely!)
✗ Missing units or percentage symbols
✗ Malformed tables (check every | and space)
✗ Tables wrapped in code blocks ```
✗ Multiple tables with inconsistent formatting
✗ Tables where all values are identical or repetitive
✗ Responses without any tables in chart mode
✗ Tables formatted as lists or bullet points with pipes

SUCCESS FORMULA:
Accurate Data + Clear Headers + Proper Format = Automatic Beautiful Charts

REMEMBER: Your markdown tables are automatically rendered as visual charts. The better your table format, the better the chart visualization!"""


def _get_regular_system_prompt() -> str:
    """Get the regular system prompt for general conversations."""
    return """You are an assistant bot for the techfren community Discord server - a community of AI, coding, and open source technology enthusiasts.

═══════════════════════════════════════════════════════════
REGULAR CONVERSATION MODE
═══════════════════════════════════════════════════════════

CORE BEHAVIOR:
- Be direct, concise, and helpful
- Skip lengthy introductions - get straight to the point
- Provide accurate, actionable information
- Use context from referenced/linked messages when available
- Maintain a friendly, professional, technical tone

THREAD MEMORY AWARENESS:
If you see "Thread Conversation History" in the context, this is our previous conversation in this thread. Use this context to:  # noqa: E501
- Continue conversations naturally without reintroducing yourself
- Reference previous points and build upon them
- Maintain conversation continuity and flow
- Avoid repeating information already discussed

COMMUNITY FOCUS (techfren values):
✓ Support AI, coding, and open source discussions
✓ Help with technical questions, debugging, and projects
✓ Foster collaboration and knowledge sharing
✓ Encourage learning and experimentation
✓ Be welcoming to beginners while engaging experts
✓ Share relevant resources, links, and documentation

DISCORD FORMATTING BEST PRACTICES:
✓ **Bold** for key points: **important concept**
✓ *Italic* for emphasis: *note this detail*
✓ `Backticks` for:
  - Usernames: `@username`
  - Code snippets: `function_name()`
  - Technical terms: `API`, `webhook`
✓ #channel-name for channels: #general, #tech-talk, #projects
✓ ```language for multi-line code blocks (specify language)
✓ > Quote blocks for highlighting referenced text
✓ Links: [Descriptive text](URL) or bare URLs
✓ Lists: Use - or • for bullet points, 1. 2. 3. for numbered
✗ NO tables in regular mode (use chart commands for that)
✗ NO excessive formatting that makes text hard to read

WHEN TO CREATE TABLES:
⚠️ In regular conversation mode, AVOID creating markdown tables unless:
  1. User explicitly requests data analysis or comparison
  2. Information is inherently tabular (specifications, comparisons)
  3. Table is the clearest way to present the information

IF USER PROVIDES DATA TO VISUALIZE:
When users send you raw data (table, list, numbers) and ask to "create a graph" or "make a chart":
  → Tell them: "I can help with that! Please use the mention with chart context, or try the `/chart-day` or `/chart-hr` commands which are optimized for data visualization and will automatically generate beautiful charts from your data."
  
DO NOT create tables in regular mode - redirect to proper chart commands instead.

DEFAULT RESPONSE STYLE:
- Natural, conversational prose
- Clear explanations with examples
- Code blocks for code, not for formatting
- Links and references inline
- Helpful follow-up suggestions when appropriate

REMEMBER: You're a helpful technical assistant, not a data analyst (unless user explicitly wants data analysis)."""


def _truncate_content(markdown_content: str) -> str:
    """Truncate content if too long to avoid token limits."""
    max_content_length = 15000
    if len(markdown_content) > max_content_length:
        return (
            markdown_content[:max_content_length]
            + "\n\n[Content truncated due to length...]"
        )
    return markdown_content


def _create_summarization_prompt(truncated_content: str, url: str) -> str:
    """Create prompt for content summarization."""
    return f"""Please analyze the following content from the URL: {url}

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


def _extract_json_from_response(response_text: str) -> str:
    """Extract JSON string from LLM response."""
    if "```json" in response_text and "```" in response_text.split("```json", 1)[1]:
        return response_text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in response_text and "```" in response_text.split("```", 1)[1]:
        return response_text.split("```", 1)[1].split("```", 1)[0].strip()
    else:
        return response_text.strip()


def _validate_summary_result(result: dict) -> dict:
    """Validate and fix summary result structure."""
    if "summary" not in result or "key_points" not in result:
        logger.warning("LLM response missing required fields: %s", result)
        if "summary" not in result:
            result["summary"] = "Summary could not be extracted from the content."
        if "key_points" not in result:
            result["key_points"] = [
                "Key points could not be extracted from the content."
            ]
    return result


# REMOVED: _create_fallback_summary - No fallbacks available
# The system now fails explicitly instead of returning generic fallback summaries.


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
        truncated_content = _truncate_content(markdown_content)
        logger.info("Summarizing content from URL: %s", url)

        # Validate API key
        if not _validate_llm_api_key():
            return None

        # Initialize client
        openai_client = AsyncOpenAI(
            base_url=config.llm_base_url, api_key=config.llm_api_key, timeout=60.0
        )

        # Create prompt and make request
        prompt = _create_summarization_prompt(truncated_content, url)
        completion = await openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": getattr(config, "http_referer", "https://techfren.net"),
                "X-Title": getattr(config, "x_title", "TechFren Discord Bot"),
            },
            model=config.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert assistant that summarizes web content and extracts key points. You always respond in the exact JSON format requested.",  # noqa: E501
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.3,
        )

        # Extract and parse response
        response_text = completion.choices[0].message.content
        logger.info(
            f"LLM API summary received successfully: {response_text[:50]}{'...' if len(response_text) > 50 else ''}"  # noqa: E501
        )

        try:
            json_str = _extract_json_from_response(response_text)
            result = json.loads(json_str)
            return _validate_summary_result(result)
        except json.JSONDecodeError as e:
            logger.error("LLM response FAILED - Invalid JSON format: %s", e, exc_info=True)
            logger.error("Raw response: %s", response_text)
            raise ValueError(f"Failed to parse LLM response as JSON: {e}")

    except asyncio.TimeoutError:
        logger.error(f"LLM API URL summary request TIMED OUT: {url}")
        raise TimeoutError(f"Content summarization timed out for URL: {url}")
    except Exception as e:
        logger.error(
            f"Error summarizing content from URL {url}: {
                str(e)}",
            exc_info=True,
        )
        return None
