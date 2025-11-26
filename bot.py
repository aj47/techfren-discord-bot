# This example requires the 'message_content' intent.

import discord
from discord.ext import commands
import asyncio
import re
from urllib.parse import urlparse

import os
import json
from typing import Optional
from datetime import datetime, timedelta, timezone
import database
from logging_config import logger  # Import the logger from the new module
from rate_limiter import check_rate_limit, update_rate_limit_config  # Import rate limiting functions
from llm_handler import call_llm_api, call_llm_for_summary, summarize_scraped_content, summarize_url_with_perplexity, call_llm_with_database_context  # Import LLM functions
from message_utils import split_long_message, fetch_referenced_message, is_discord_message_link  # Import message utility functions
from youtube_handler import is_youtube_url, scrape_youtube_content  # Import YouTube functions
from summarization_tasks import daily_channel_summarization, set_discord_client, before_daily_summarization  # Import summarization tasks
from config_validator import validate_config  # Import config validator
from command_handler import handle_bot_command, handle_sum_day_command, handle_sum_hr_command  # Import command handlers
from firecrawl_handler import scrape_url_content  # Import Firecrawl handler
from apify_handler import scrape_twitter_content, is_twitter_url  # Import Apify handler
from gif_limiter import check_and_record_gif_post, check_gif_rate_limit
from image_analyzer import analyze_message_images  # Import image analysis functions
from gif_utils import is_gif_url, is_discord_emoji_url

GIF_WARNING_DELETE_DELAY = 30  # seconds before deleting warning messages


# Track users who have been warned about GIF limits (user_id -> expiry_time)
_gif_warned_users = {}


def _format_gif_cooldown(seconds_remaining: int) -> str:
    """Convert remaining seconds into a human readable string."""

    seconds_remaining = max(int(seconds_remaining), 0)
    minutes, seconds = divmod(seconds_remaining, 60)

    parts = []
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds or not parts:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    if len(parts) == 1:
        return parts[0]
    return " and ".join(parts)


def message_contains_gif(message: discord.Message) -> bool:
    """Detect GIFs in attachments, message content URLs, and embeds."""

    # Check attachments
    for attachment in getattr(message, "attachments", []):
        filename = (attachment.filename or "").lower()
        content_type = (attachment.content_type or "").lower()
        if filename.endswith((".gif", ".gifv")) or "gif" in content_type:
            return True

    # Check message content for URLs
    content = message.content or ""
    if re.search(r'https?://\S+', content):
        for match in re.finditer(r'https?://\S+', content):
            if is_gif_url(match.group(0)):
                return True

    # Check embeds
    for embed in getattr(message, "embeds", []):
        if getattr(embed, "type", None) == "gifv":
            return True

        # Check all embed URLs
        for url_attr in ["url", "image.url", "thumbnail.url"]:
            parts = url_attr.split(".")
            obj = embed
            for part in parts:
                obj = getattr(obj, part, None)
                if obj is None:
                    break
            if obj and is_gif_url(str(obj)):
                return True

    return False

# Using message_content intent (requires enabling in the Discord Developer Portal)
intents = discord.Intents.default()
intents.message_content = True  # This is required to read message content in guild channels

# Use commands.Bot instead of discord.Client to support slash commands
bot = commands.Bot(command_prefix='!', intents=intents)

# Keep client reference for backward compatibility
client = bot

async def process_url(message_id: str, url: str):
    """
    Process a URL found in a message by scraping its content, summarizing it,
    and updating the message in the database with the scraped data.

    Args:
        message_id (str): The ID of the message containing the URL
        url (str): The URL to process
    """
    try:
        logger.info(f"Processing URL {url} from message {message_id}")

        # Check if the URL is from YouTube
        if await is_youtube_url(url):
            logger.info(f"Detected YouTube URL: {url}")

            # Use YouTube handler to scrape content
            scraped_result = await scrape_youtube_content(url)

            # If YouTube scraping fails, fall back to Firecrawl
            if not scraped_result:
                logger.warning(f"Failed to scrape YouTube content, falling back to Firecrawl: {url}")
                scraped_result = await scrape_url_content(url)
            else:
                logger.info(f"Successfully scraped YouTube content: {url}")
                # Extract markdown content from the scraped result
                markdown_content = scraped_result.get('markdown')
        # Check if the URL is from Twitter/X.com
        elif await is_twitter_url(url):
            logger.info(f"Detected Twitter/X.com URL: {url}")

            # Validate if the URL contains a tweet ID (status)
            from apify_handler import extract_tweet_id
            tweet_id = extract_tweet_id(url)
            if not tweet_id:
                logger.warning(f"URL appears to be Twitter/X.com but doesn't contain a valid tweet ID: {url}")

                # For base Twitter/X.com URLs without a tweet ID, create a simple markdown response
                if url.lower() in ["https://x.com", "https://twitter.com", "http://x.com", "http://twitter.com"]:
                    logger.info(f"Handling base Twitter/X.com URL with custom response: {url}")
                    scraped_result = {
                        "markdown": f"# Twitter/X.com\n\nThis is the main page of Twitter/X.com: {url}"
                    }
                else:
                    # For other Twitter/X.com URLs without a tweet ID, try Firecrawl
                    scraped_result = await scrape_url_content(url)
            else:
                # Check if Apify API token is configured
                if not hasattr(config, 'apify_api_token') or not config.apify_api_token:
                    logger.warning("Apify API token not found in config.py or is empty, falling back to Firecrawl")
                    scraped_result = await scrape_url_content(url)
                else:
                    # Use Apify to scrape Twitter/X.com content
                    scraped_result = await scrape_twitter_content(url)

                    # If Apify scraping fails, fall back to Firecrawl
                    if not scraped_result:
                        logger.warning(f"Failed to scrape Twitter/X.com content with Apify, falling back to Firecrawl: {url}")
                        scraped_result = await scrape_url_content(url)
                    else:
                        logger.info(f"Successfully scraped Twitter/X.com content with Apify: {url}")
                        # Extract markdown content from the scraped result
                        markdown_content = scraped_result.get('markdown')
        else:
            # For non-Twitter/X.com and non-YouTube URLs, use Firecrawl
            scraped_result = await scrape_url_content(url)
            markdown_content = scraped_result  # Firecrawl returns markdown directly

        # Check if scraping was successful
        if not scraped_result:
            logger.warning(f"Failed to scrape content from URL: {url}")
            return

        # Handle different types of scraped results
        if await is_youtube_url(url):
            # YouTube handler returns a dict with 'markdown' key
            if isinstance(scraped_result, dict) and 'markdown' in scraped_result:
                markdown_content = scraped_result.get("markdown", "")
            else:
                logger.warning(f"Invalid scraped result structure for YouTube URL {url}: expected dict with 'markdown' key")
                return
        elif await is_twitter_url(url) and hasattr(config, 'apify_api_token') and config.apify_api_token:
            # Twitter/X.com URLs scraped with Apify return a dict with 'markdown' key
            if isinstance(scraped_result, dict) and 'markdown' in scraped_result:
                markdown_content = scraped_result.get("markdown", "")
            else:
                logger.warning(f"Invalid scraped result structure for Twitter URL {url}: expected dict with 'markdown' key")
                return
        else:
            # Firecrawl returns markdown directly as a string
            if isinstance(scraped_result, str):
                markdown_content = scraped_result
            else:
                logger.warning(f"Invalid scraped result for URL {url}: expected string, got {type(scraped_result)}")
                return

        # Step 2: Summarize the scraped content
        summary_text = await summarize_scraped_content(markdown_content, url)
        if not summary_text:
            logger.warning(f"Failed to summarize content from URL: {url}")
            return

        # Step 3: Store the summary (no separate key points since it's now plain text)
        # Store empty JSON array for key_points to maintain database compatibility
        key_points_json = json.dumps([])

        # Step 4: Update the message in the database with the scraped data
        success = await database.update_message_with_scraped_data(
            message_id,
            url,
            summary_text,
            key_points_json
        )

        if success:
            logger.info(f"Successfully processed URL {url} from message {message_id}")
        else:
            logger.warning(f"Failed to update message {message_id} with scraped data")

    except Exception as e:
        logger.error(f"Error processing URL {url} from message {message_id}: {str(e)}", exc_info=True)


async def create_or_get_summary_thread(message: discord.Message, thread_name: str):
    """Create or fetch a summary thread for a message and ensure the bot has joined it.

    Args:
        message: The Discord message to create the thread from.
        thread_name: The name to use when creating the thread.

    Returns:
        The thread object if found or created successfully, otherwise None.
    """
    thread = None
    try:
        # Try to create a thread from the message
        thread = await message.create_thread(name=thread_name, auto_archive_duration=1440)
        # Join the thread to ensure it's visible and active
        await thread.join()
        logger.info(f"Created and joined thread {thread.id} for message {message.id}")
    except discord.errors.HTTPException as e:
        if e.code == 160004:  # Thread already exists
            logger.info(f"Thread already exists for message {message.id}, fetching it")
            # Get the existing thread
            # Discord doesn't provide a direct way to get thread from message, so we need to search
            if isinstance(message.channel, discord.TextChannel):
                # Search through active threads
                for active_thread in message.channel.threads:
                    if active_thread.id == message.id or (
                        hasattr(active_thread, 'starter_message')
                        and active_thread.starter_message
                        and active_thread.starter_message.id == message.id
                    ):
                        thread = active_thread
                        break

                # If not found in active threads, search archived threads
                if not thread:
                    async for archived_thread in message.channel.archived_threads(limit=100):
                        if archived_thread.id == message.id or (
                            hasattr(archived_thread, 'starter_message')
                            and archived_thread.starter_message
                            and archived_thread.starter_message.id == message.id
                        ):
                            thread = archived_thread
                            break
        else:
            raise

    if not thread:
        logger.error(f"Could not create or find thread for message {message.id}")
        return None

    # Ensure bot is a member of the thread (important for visibility)
    try:
        if not thread.me:
            await thread.join()
            logger.info(f"Joined existing thread {thread.id}")
    except Exception as e:
        logger.warning(f"Could not join thread {thread.id}: {e}")

    return thread

async def handle_x_post_summary(message: discord.Message) -> bool:
    """
    Automatically detect X/Twitter links in messages, scrape and summarize them,
    and reply to the message with the summary.

    Args:
        message: The Discord message to check for X/Twitter links

    Returns:
        bool: True if an X post was found and processed, False otherwise
    """
    try:
        # Skip bot messages
        if message.author.bot:
            return False

        # Extract URLs from message content
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?'
        urls = re.findall(url_pattern, message.content)

        if not urls:
            return False

        # Check each URL to find X/Twitter links
        x_urls = []
        for url in urls:
            if await is_twitter_url(url):
                from apify_handler import extract_tweet_id
                tweet_id = extract_tweet_id(url)
                if tweet_id:  # Only process URLs with valid tweet IDs
                    x_urls.append(url)

        if not x_urls:
            return False

        logger.info(f"Found {len(x_urls)} X/Twitter URL(s) in message {message.id}")

        # Process each X URL
        for url in x_urls:
            try:
                # Check if Apify API token is configured
                import config
                if not hasattr(config, 'apify_api_token') or not config.apify_api_token:
                    logger.warning("Apify API token not configured, skipping X post summarization")
                    continue

                # Scrape the X/Twitter content FIRST (before creating thread)
                logger.info(f"Starting to scrape X post: {url}")
                scraped_result = await scrape_twitter_content(url)

                if not scraped_result or 'markdown' not in scraped_result:
                    logger.warning(f"Failed to scrape X post: {url}")
                    continue

                markdown_content = scraped_result.get('markdown', '')

                # Summarize the content BEFORE creating thread
                logger.info(f"Summarizing scraped content for: {url}")
                summary_text = await summarize_scraped_content(markdown_content, url)

                if not summary_text:
                    logger.warning(f"Failed to summarize X post: {url}")
                    continue

                # Build the response message with header
                response = f"📊 **X Post Summary:**\n\n{summary_text}"

                # Split into multiple messages if needed to respect Discord's 2000 character limit
                if len(response) > 1900:
                    logger.info(f"Splitting X post summary of {len(response)} chars into multiple parts")
                    message_parts = await split_long_message(response, max_length=1900)
                else:
                    message_parts = [response]

                # NOW create or get existing thread from the message (after Apify calls complete)
                from apify_handler import extract_tweet_id
                tweet_id = extract_tweet_id(url)
                thread_name = f"X Post Summary: {tweet_id[:20]}" if tweet_id else "X Post Summary"

                thread = await create_or_get_summary_thread(message, thread_name)
                if not thread:
                    continue

                # Post the summary directly to the thread (no "processing" message needed)
                for part in message_parts:
                    await thread.send(part)
                logger.info(
                    f"Posted X post summary ({len(response)} chars total) in {len(message_parts)} part(s) "
                    f"to thread {thread.id} (thread name: {thread.name})"
                )

                # Store the scraped data in the database
                # Store empty JSON array for key_points to maintain database compatibility
                key_points_json = json.dumps([])
                await database.update_message_with_scraped_data(
                    str(message.id),
                    url,
                    summary_text,
                    key_points_json
                )

                logger.info(f"Successfully processed X post: {url}")

            except Exception as e:
                logger.error(f"Error processing X URL {url}: {str(e)}", exc_info=True)
                # If thread was created before error, post error message to it
                try:
                    if 'thread' in locals() and thread:
                        await thread.send(f"❌ Error processing X post: {str(e)[:100]}")
                except:
                    pass

        return len(x_urls) > 0

    except Exception as e:
        logger.error(f"Error in handle_x_post_summary: {str(e)}", exc_info=True)
        return False

async def handle_link_summary(message: discord.Message) -> bool:
    """
    Automatically detect non-X/Twitter URLs in messages, summarize them using Perplexity directly,
    and reply to the message with the summary.

    Args:
        message: The Discord message to check for URLs

    Returns:
        bool: True if a link was found and processed, False otherwise
    """
    try:
        # Skip bot messages
        if message.author.bot:
            return False

        # Extract URLs from message content
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?'
        urls = re.findall(url_pattern, message.content)

        if not urls:
            return False

        # Filter out X/Twitter URLs, YouTube URLs, GIF URLs, and Discord emoji/image URLs
        # (they have their own handling or are skipped entirely)
        regular_urls = []
        for url in urls:
            # Skip GIF URLs completely (no link summary or image analysis)
            if is_gif_url(url):
                logger.info(f"Skipping GIF URL from link summary: {url}")
                continue

            # Skip Discord CDN emoji/image URLs (e.g., cdn.discordapp.com/emojis/*.webp)
            if is_discord_emoji_url(url):
                logger.info(f"Skipping Discord emoji/image URL from link summary: {url}")
                continue

            # Skip internal Discord message permalinks (discord.com/channels/...)
            if is_discord_message_link(url):
                logger.info(f"Skipping Discord message link from link summary: {url}")
                continue

            is_x_url = await is_twitter_url(url)
            is_yt_url = await is_youtube_url(url)

            if not is_x_url and not is_yt_url:
                regular_urls.append(url)

        if not regular_urls:
            return False

        logger.info(f"Found {len(regular_urls)} regular URL(s) in message {message.id}")

        # Process each URL
        for url in regular_urls:
            try:
                # Summarize the URL directly using Perplexity
                logger.info(f"Starting to summarize URL with Perplexity: {url}")
                summary_text = await summarize_url_with_perplexity(url)

                if not summary_text:
                    logger.warning(f"Failed to summarize URL: {url}")
                    continue

                # Build the response message with header
                response = f"🔗 **Link Summary:**\n\n{summary_text}"

                # Split into multiple messages if needed to respect Discord's 2000 character limit
                if len(response) > 1900:
                    logger.info(f"Splitting link summary of {len(response)} chars into multiple parts")
                    message_parts = await split_long_message(response, max_length=1900)
                else:
                    message_parts = [response]

                # Create or get existing thread from the message
                # Extract domain from URL for thread name
                parsed_url = urlparse(url)
                domain = parsed_url.netloc or "Link"
                thread_name = f"Link Summary: {domain[:40]}"  # Limit length

                thread = await create_or_get_summary_thread(message, thread_name)
                if not thread:
                    continue

                # Post the summary directly to the thread
                for part in message_parts:
                    await thread.send(part)
                logger.info(
                    f"Posted link summary ({len(response)} chars total) in {len(message_parts)} part(s) "
                    f"to thread {thread.id} (thread name: {thread.name})"
                )

                # Store the scraped data in the database
                # Store empty JSON array for key_points to maintain database compatibility
                key_points_json = json.dumps([])
                await database.update_message_with_scraped_data(
                    str(message.id),
                    url,
                    summary_text,
                    key_points_json
                )

                logger.info(f"Successfully processed URL: {url}")

            except Exception as e:
                logger.error(f"Error processing URL {url}: {str(e)}", exc_info=True)
                # If thread was created before error, post error message to it
                try:
                    if 'thread' in locals() and thread:
                        await thread.send(f"❌ Error processing link: {str(e)[:100]}")
                except:
                    pass

        return len(regular_urls) > 0

    except Exception as e:
        logger.error(f"Error in handle_link_summary: {str(e)}", exc_info=True)
        return False

async def handle_links_dump_channel(message: discord.Message) -> bool:
    """
    Handle messages in the links dump channel.
    Delete non-link messages with a warning that auto-deletes after 1 minute.

    Args:
        message: The Discord message to check

    Returns:
        bool: True if message was handled (deleted), False if message should remain
    """
    try:
        # Import config here to avoid circular imports
        import config

        # Check if links dump channel is configured and this is that channel
        if not hasattr(config, 'links_dump_channel_id') or not config.links_dump_channel_id:
            return False

        # Check if this is the links dump channel or a thread within it
        is_links_dump_channel = False

        if str(message.channel.id) == config.links_dump_channel_id:
            # Direct message in the links dump channel
            is_links_dump_channel = True
        elif isinstance(message.channel, discord.Thread) and str(message.channel.parent_id) == config.links_dump_channel_id:
            # Message in a thread created from the links dump channel - allow these
            logger.info(f"Message {message.id} is in a thread from links dump channel, allowing")
            return False

        if not is_links_dump_channel:
            return False

        # Don't handle bot messages or commands
        if message.author.bot:
            return False

        # Check for URLs in the message content using the same regex as process_url
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?'
        urls = re.findall(url_pattern, message.content)


        # If message contains URLs, allow it
        if urls:
            logger.info(f"Message {message.id} in links dump channel contains URL, allowing")
            return False

        # Always allow forwarded messages from other channels
        if message.reference and message.reference.message_id and (
            message.reference.channel_id != message.channel.id
        ):
            logger.info(
                f"Message {message.id} is forwarded from another channel, allowing"
            )
            return False

        # Message doesn't contain URLs, send warning and schedule deletion
        logger.info(f"Deleting non-link message {message.id} in links dump channel")

        warning_msg = await message.channel.send(
            f"{message.author.mention} We only allow sharing of links in this channel. "
            "If you want to comment on a link please put it in a thread, "
            "otherwise type your message in the appropriate channel. "
            "This message will be deleted in 1 minute."
        )

        # Schedule deletion of both messages after 1 minute (60 seconds)
        async def delete_messages():
            await asyncio.sleep(60)  # 1 minute
            try:
                await message.delete()
                logger.info(f"Deleted original message {message.id} from links dump channel")
            except discord.NotFound:
                logger.info(f"Original message {message.id} already deleted")
            except discord.Forbidden:
                logger.warning(f"No permission to delete original message {message.id}")
            except Exception as e:
                logger.error(f"Error deleting original message {message.id}: {e}")

            try:
                await warning_msg.delete()
                logger.info(f"Deleted warning message {warning_msg.id} from links dump channel")
            except discord.NotFound:
                logger.info(f"Warning message {warning_msg.id} already deleted")
            except discord.Forbidden:
                logger.warning(f"No permission to delete warning message {warning_msg.id}")
            except Exception as e:
                logger.error(f"Error deleting warning message {warning_msg.id}: {e}")

        # Create background task for deletion
        asyncio.create_task(delete_messages())

        return True  # Message was handled

    except Exception as e:
        logger.error(f"Error handling links dump channel message {message.id}: {e}", exc_info=True)
        return False

@bot.event
async def on_ready():
    set_discord_client(bot) # Set the client instance for summarization tasks
    logger.info(f'Bot has successfully connected as {bot.user}')
    logger.info(f'Bot ID: {bot.user.id}')
    logger.info(f'Connected to {len(bot.guilds)} guilds')

    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        logger.info(f'Synced {len(synced)} command(s)')
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')

    # Initialize the database - critical for bot operation
    try:
        database.init_database()

        # Check if database connection is working
        if not database.check_database_connection():
            logger.critical('Database connection check failed. Shutting down.')
            await bot.close()
            return

        message_count = database.get_message_count()
        logger.info(f'Database initialized successfully. Current message count: {message_count}')

        # Log database file information
        db_file_path = os.path.join(os.getcwd(), database.DB_FILE)
        if os.path.exists(db_file_path):
            logger.info(f'Database file exists at: {db_file_path}')
            logger.info(f'Database file size: {os.path.getsize(db_file_path)} bytes')
        else:
            logger.critical(f'Database file does not exist at: {db_file_path}')
            await bot.close()
            return
    except Exception as e:
        logger.critical(f'Failed to initialize database: {str(e)}', exc_info=True)
        logger.critical('Database initialization is required for bot operation. Shutting down.')
        await bot.close()
        return

    # Start the daily summarization task if not already running
    if not daily_channel_summarization.is_running():
        daily_channel_summarization.start()
        logger.info("Started daily channel summarization task")

    # Log details about each connected guild
    for guild in bot.guilds:
        logger.info(f'Connected to guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members')

@bot.event
async def on_guild_join(guild):
    """Log when the bot joins a new guild"""
    logger.info(f'Bot joined new guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members')

@bot.event
async def on_guild_remove(guild):
    """Log when the bot is removed from a guild"""
    logger.info(f'Bot removed from guild: {guild.name} (ID: {guild.id})')

@bot.event
async def on_error(event, *args, **kwargs):
    """Log Discord API errors"""
    logger.error(f'Discord error in {event}', exc_info=True)
    # Log additional context if available
    if args:
        logger.error(f'Error context args: {args}')
    if kwargs:
        logger.error(f'Error context kwargs: {kwargs}')

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Handle links dump channel logic first
    # This needs to happen before storing in database to avoid storing deleted messages
    handled_by_links_dump = await handle_links_dump_channel(message)
    if handled_by_links_dump:
        return  # Message was handled (deleted), stop processing

    # Helper function to recursively check reference chain for GIFs
    async def check_reference_chain_for_gif(msg, depth=0, max_depth=25):
        """
        Recursively follow message references to check if any message in the chain contains a GIF.
        Returns (has_gif, chain_depth, is_external) tuple.
        is_external=True means the reference is from a channel/server the bot can't access.
        """
        if depth >= max_depth:
            logger.warning(f"Reference chain depth limit reached ({max_depth})")
            # Allow deep chains - fail open to avoid blocking legitimate conversations
            return False, depth, False

        if not msg.reference or not msg.reference.message_id:
            return False, depth, False

        try:
            # Use existing utility to fetch referenced message (handles caching, cross-channel refs)
            ref_msg = await fetch_referenced_message(msg)

            if ref_msg is None:
                # Determine why we couldn't fetch: external server or deleted message
                ref_channel = bot.get_channel(msg.reference.channel_id) if msg.reference.channel_id else msg.channel
                if ref_channel is None:
                    logger.info(
                        f"Chain[{depth}] Cannot access channel {msg.reference.channel_id} - "
                        f"likely external server or no permission"
                    )
                    return True, depth, True  # Block external forwards we can't verify
                else:
                    # Channel exists but message couldn't be fetched (likely deleted or no permission)
                    logger.info(f"Chain[{depth}] Message {msg.reference.message_id} not accessible")
                    return False, depth, False  # Allow if just deleted

            # Successfully fetched message
            has_gif = message_contains_gif(ref_msg)
            logger.info(
                f"Chain[{depth}] msg {ref_msg.id} - "
                f"GIF: {has_gif} | "
                f"Embeds: {len(ref_msg.embeds)} | "
                f"Has ref: {ref_msg.reference is not None}"
            )

            if has_gif:
                return True, depth, False

            # Continue following the chain
            if ref_msg.reference:
                return await check_reference_chain_for_gif(ref_msg, depth + 1, max_depth)

            return False, depth, False
        except Exception as e:
            logger.error(f"Error checking chain at depth {depth}: {e}")
            return False, depth, False

        return False, depth, False

    # Check if this message references another message (reply or forward)
    # This must happen BEFORE the GIF check because forwards might not have GIF content loaded yet
    if not message.author.bot and message.reference and message.reference.message_id:
        try:
            logger.info(f"Reference detected - User: {message.author.id} | Ref: {message.reference.message_id}")

            # Log embed details of current message if present
            if message.embeds:
                for i, embed in enumerate(message.embeds):
                    logger.info(
                        f"Current msg embed {i}: "
                        f"type={getattr(embed, 'type', None)} | "
                        f"url={getattr(embed, 'url', None)}"
                    )

            # Check if the CURRENT message (the forward) contains a GIF
            current_has_gif = message_contains_gif(message)

            # Check the entire reference chain for GIFs
            chain_has_gif, chain_depth, is_external = await check_reference_chain_for_gif(message)
            logger.info(
                f"Chain check complete - GIF: {chain_has_gif} | "
                f"Depth: {chain_depth} | External: {is_external}"
            )

            if chain_has_gif or current_has_gif:
                # Check if user can post a GIF (read-only check, will record later)
                can_post_gif, seconds_remaining = await check_gif_rate_limit(
                    str(message.author.id), message.created_at
                )

                if can_post_gif:
                    # User is allowed to post - record it and let the forward through
                    logger.info(
                        f"Forward/reply with GIF allowed - User: {message.author.id} | "
                        f"Chain GIF: {chain_has_gif} | Current GIF: {current_has_gif}"
                    )
                    # Record the GIF post now (don't rely on direct GIF handler for forwards)
                    if chain_has_gif and not current_has_gif:
                        recorded, record_seconds_remaining = await check_and_record_gif_post(
                            str(message.author.id), message.created_at
                        )
                        if not recorded:
                            logger.info(
                                f"Blocking forward/reply (race-triggered rate limit) - "
                                f"User: {message.author.id} | Wait: {record_seconds_remaining}s"
                            )
                            try:
                                await message.delete()
                            except discord.NotFound:
                                pass
                            except discord.Forbidden:
                                logger.warning(f"No permission to delete message {message.id}")
                            except Exception as delete_error:
                                logger.error(f"Error deleting message: {delete_error}", exc_info=True)

                            wait_text = _format_gif_cooldown(record_seconds_remaining)
                            warning_message = (
                                f"{message.author.mention} You can only post one GIF every 5 minutes. "
                                f"Please wait {wait_text} before posting another GIF. "
                                f"This message will be deleted in 30 seconds."
                            )
                            warning_msg = None
                            try:
                                warning_msg = await message.channel.send(warning_message)
                            except Exception as send_error:
                                logger.error(f"Error sending rate limit warning: {send_error}", exc_info=True)
                            if warning_msg:
                                async def delete_warning_after_delay():
                                    await asyncio.sleep(GIF_WARNING_DELETE_DELAY)
                                    try:
                                        await warning_msg.delete()
                                    except Exception:
                                        pass
                                asyncio.create_task(delete_warning_after_delay())
                            return

                        logger.info(f"Recorded forwarded GIF for user {message.author.id}")
                    # If current_has_gif is also True, it will be recorded below in the direct handler
                else:
                    # User is rate limited - block the forward
                    logger.info(
                        f"Blocking forward/reply (rate limited) - User: {message.author.id} | "
                        f"Wait: {seconds_remaining}s"
                    )

                    # Delete the forward/reply
                    try:
                        await message.delete()
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        logger.warning(f"No permission to delete message {message.id}")
                    except Exception as delete_error:
                        logger.error(f"Error deleting message: {delete_error}", exc_info=True)

                    # Send rate limit warning with wait time
                    wait_text = _format_gif_cooldown(seconds_remaining)
                    warning_message = (
                        f"{message.author.mention} You can only post one GIF every 5 minutes. "
                        f"Please wait {wait_text} before posting another GIF. "
                        f"This message will be deleted in 30 seconds."
                    )

                    warning_msg = None
                    try:
                        warning_msg = await message.channel.send(warning_message)
                    except Exception as send_error:
                        logger.error(f"Error sending rate limit warning: {send_error}", exc_info=True)

                    if warning_msg:
                        async def delete_warning_after_delay():
                            await asyncio.sleep(GIF_WARNING_DELETE_DELAY)
                            try:
                                await warning_msg.delete()
                            except Exception:
                                pass

                        asyncio.create_task(delete_warning_after_delay())

                    return  # Stop processing this message
        except discord.NotFound:
            pass  # Referenced message not found
        except discord.Forbidden:
            logger.warning(f"No permission to fetch referenced message {message.reference.message_id}")
        except Exception as ref_error:
            logger.error(f"Error fetching referenced message: {ref_error}", exc_info=True)

    # Check if message contains GIF (for all non-bot messages)
    has_gif = False
    if not message.author.bot:
        has_gif = message_contains_gif(message)
        if has_gif:
            logger.info(f"Direct GIF detected - User: {message.author.id} | Embeds: {len(message.embeds)}")

            # Log embed details
            if message.embeds:
                for i, embed in enumerate(message.embeds):
                    logger.info(
                        f"GIF embed {i}: "
                        f"type={getattr(embed, 'type', None)} | "
                        f"url={getattr(embed, 'url', None)}"
                    )

    # Enforce GIF posting limits for regular users (rate limiting only, forwards already handled above)
    if not message.author.bot and has_gif:
        # Check rate limit for direct GIF posts (forwards already blocked above)
        can_post_gif, seconds_remaining = await check_and_record_gif_post(
            str(message.author.id), message.created_at
        )

        if not can_post_gif:
            user_id = str(message.author.id)
            logger.info(
                f"Rate limited - User: {message.author.id} | Wait: {seconds_remaining}s"
            )

            # Delete the GIF message
            try:
                await message.delete()
                logger.debug(f"Deleted rate-limited GIF message {message.id}")
            except discord.NotFound:
                logger.info(f"GIF message {message.id} already deleted")
            except discord.Forbidden:
                logger.warning(
                    f"Insufficient permissions to delete GIF message {message.id}"
                )
            except Exception as delete_error:
                logger.error(
                    f"Unexpected error deleting GIF message {message.id}: {delete_error}",
                    exc_info=True,
                )

            # Check if user has already been warned recently
            now = datetime.now(timezone.utc)
            user_warning_expiry = _gif_warned_users.get(user_id)

            # Clean up expired warnings
            expired_users = [uid for uid, expiry in _gif_warned_users.items() if expiry <= now]
            for uid in expired_users:
                del _gif_warned_users[uid]

            # Only send warning if user hasn't been warned recently
            if user_warning_expiry is None or user_warning_expiry <= now:
                wait_text = _format_gif_cooldown(seconds_remaining)
                warning_message = (
                    f"{message.author.mention} You can only post one GIF every 5 minutes. "
                    f"Please wait {wait_text} before posting another GIF. "
                    f"This message will be deleted in 30 seconds."
                )

                warning_msg = None
                try:
                    warning_msg = await message.channel.send(warning_message)
                    # Mark user as warned for the next 5 minutes
                    _gif_warned_users[user_id] = now + timedelta(minutes=5)
                    logger.debug(f"User {user_id} warned about GIF limit, will suppress warnings until {_gif_warned_users[user_id]}")
                except discord.Forbidden:
                    logger.warning(
                        f"Insufficient permissions to send GIF warning in channel {message.channel.id}"
                    )
                except Exception as send_error:
                    logger.error(
                        f"Failed to send GIF warning message in channel {message.channel.id}: {send_error}",
                        exc_info=True,
                    )

                if warning_msg:
                    async def delete_warning_after_delay():
                        await asyncio.sleep(GIF_WARNING_DELETE_DELAY)
                        try:
                            await warning_msg.delete()
                        except discord.NotFound:
                            logger.debug(
                                f"GIF warning message {warning_msg.id} already deleted"
                            )
                        except discord.Forbidden:
                            logger.warning(
                                f"Insufficient permissions to delete GIF warning message {warning_msg.id}"
                            )
                        except Exception as warning_delete_error:
                            logger.error(
                                f"Failed to delete GIF warning message {warning_msg.id}: {warning_delete_error}",
                                exc_info=True,
                            )

                    asyncio.create_task(delete_warning_after_delay())
            else:
                logger.debug(f"User {user_id} already warned, silently deleting GIF without additional warning")

            return

    # Log message details - safely handle DMs and different channel types
    guild_name = message.guild.name if message.guild else "DM"

    # Safely get channel name - different channel types might not have a name attribute
    if hasattr(message.channel, 'name'):
        channel_name = message.channel.name
    elif hasattr(message.channel, 'recipient'):
        # This is a DM channel
        channel_name = f"DM with {message.channel.recipient}"
    else:
        channel_name = "Unknown Channel"

    # Use display_name to show user's server nickname when available
    author_display = message.author.display_name if isinstance(message.author, discord.Member) else str(message.author)
    logger.info(f"Message received - Guild: {guild_name} | Channel: {channel_name} | Author: {author_display} | Content: {message.content[:50]}{'...' if len(message.content) > 50 else ''}")

    # Analyze images if present
    image_descriptions_json = None
    try:
        if message.attachments:
            image_analyses = await analyze_message_images(message)
            if image_analyses:
                # Convert to JSON for database storage
                image_descriptions_json = json.dumps(image_analyses)
                logger.info(f"Analyzed {len(image_analyses)} image(s) in message {message.id}")
    except Exception:
        logger.exception("Error analyzing images in message %s", message.id)

    # Store message in database
    try:
        # Determine if this is a command and what type
        is_command = False
        command_type = None

        bot_mention = f'<@{bot.user.id}>'
        bot_mention_alt = f'<@!{bot.user.id}>'
        if message.content.startswith(bot_mention) or message.content.startswith(bot_mention_alt):
            is_command = True
            command_type = "mention"
        elif message.content.startswith('/bot'):
            is_command = True
            command_type = "/bot"
        elif message.content.startswith('/sum-day'):
            is_command = True
            command_type = "/sum-day"
        elif message.content.startswith('/sum-hr'):
            is_command = True
            command_type = "/sum-hr"

        # Store in database
        guild_id = str(message.guild.id) if message.guild else None
        channel_id = str(message.channel.id)

        # Ensure database module is accessible
        if not database:
            logger.error("Database module not properly imported or initialized")
            return

        success = database.store_message(
            message_id=str(message.id),
            author_id=str(message.author.id),
            author_name=str(message.author),
            channel_id=channel_id,
            channel_name=channel_name,
            content=message.content,
            created_at=message.created_at,
            guild_id=guild_id,
            guild_name=guild_name,
            is_bot=message.author.bot,
            is_command=is_command,
            command_type=command_type,
            image_descriptions=image_descriptions_json
        )

        if not success:
            # This is usually because the message already exists (common when bot restarts)
            logger.debug(f"Failed to store message {message.id} in database (likely duplicate)")

        # Note: Automatic URL processing disabled - URLs are now processed on-demand when requested
        # This saves resources and avoids processing URLs that nobody asks about
        # Exception: X/Twitter posts are auto-summarized (see handle_x_post_summary below)
    except Exception as e:
        logger.error(f"Error storing message in database: {str(e)}", exc_info=True)

    # Handle X/Twitter post summarization automatically
    try:
        x_post_handled = await handle_x_post_summary(message)
        if x_post_handled:
            logger.debug(f"X post summary handled for message {message.id}")
    except Exception as e:
        logger.error(f"Error in X post summary handler: {str(e)}", exc_info=True)

    # Handle regular link summarization automatically (non-X.com, non-YouTube URLs)
    try:
        link_handled = await handle_link_summary(message)
        if link_handled:
            logger.debug(f"Link summary handled for message {message.id}")
    except Exception as e:
        logger.error(f"Error in link summary handler: {str(e)}", exc_info=True)

    # Check if this is a command
    bot_mention = f'<@{bot.user.id}>'
    bot_mention_alt = f'<@!{bot.user.id}>'
    is_mention_command = bot_mention in message.content or bot_mention_alt in message.content
    is_sum_day_command = message.content.startswith('/sum-day')
    is_sum_hr_command = message.content.startswith('/sum-hr')

    # Process mention commands in any channel
    if is_mention_command:
        logger.debug(f"Processing mention command in channel #{message.channel.name}")
        await handle_bot_command(message, bot.user, bot)
        return

    # If not a command we recognize, ignore
    if not (is_sum_day_command or is_sum_hr_command):
        return

    # Process commands
    try:
        if is_sum_day_command:
            await handle_sum_day_command(message, bot.user)
        elif is_sum_hr_command:
            await handle_sum_hr_command(message, bot.user)
    except Exception as e:
        logger.error(f"Error processing command in on_message: {e}", exc_info=True)
        # Optionally notify about the error in the channel if it's a user-facing command error
        # await message.channel.send("Sorry, an error occurred while processing your command.")


# Catch GIFs added via message edits (e.g., embeds resolving after initial post)
@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """Re-check edited messages for GIFs to prevent embed-based bypasses."""
    if after.author == bot.user or after.author.bot:
        return

    # Only enforce if the message NOW contains a GIF that wasn't there before
    before_has_gif = message_contains_gif(before)
    after_has_gif = message_contains_gif(after)

    if after_has_gif and not before_has_gif:
        logger.info(f"New GIF detected in edited message - User: {after.author.id}")
        # Reuse the same enforcement logic by treating it as a new message check
        await on_message(after)

# Helper function for slash command handling
async def _handle_slash_command_wrapper(
    interaction: discord.Interaction,
    command_name: str,
    hours: int = 24,
    error_message: Optional[str] = None
) -> None:
    """Unified wrapper for slash command handling with error management."""
    # Only defer if the interaction hasn't been acknowledged yet
    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except discord.NotFound as e:
        # 10062: Unknown interaction (typically expired or invalid token)
        if e.code == 10062:
            logger.error(f"Interaction expired or unknown for {command_name} - cannot defer response")
            return  # Can't safely respond to this interaction anymore
        # Re-raise other NotFound exceptions
        raise
    except discord.HTTPException as e:
        # 40060: Interaction has already been acknowledged
        if e.status == 400 and e.code == 40060:
            logger.warning(f"Interaction already acknowledged for {command_name}, continuing without deferring...")
        else:
            # Re-raise other HTTP exceptions
            raise

    if error_message is None:
        error_message = f"Sorry, an error occurred while processing the {command_name} command. Please try again later."

    # Validate hours parameter for sum-hr command
    if command_name == "sum-hr":
        import config
        if hours < 1 or hours > config.MAX_SUMMARY_HOURS:
            try:
                allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
                await interaction.followup.send(config.ERROR_MESSAGES['invalid_hours_range'], ephemeral=True, allowed_mentions=allowed_mentions)
                return
            except Exception as e:
                logger.error(f"Failed to send validation error for {command_name}: {e}")
                return

        # Warn for large summaries that may take longer
        if hours > config.LARGE_SUMMARY_THRESHOLD:
            error_message = config.ERROR_MESSAGES['large_summary_warning'].format(hours=hours) + " and could impact performance."

    try:
        from command_abstraction import (
            create_context_from_interaction,
            create_response_sender,
            create_thread_manager,
            handle_summary_command
        )

        context = create_context_from_interaction(interaction, f"/{command_name}" + (f" {hours}" if hours != 24 else ""))
        response_sender = create_response_sender(interaction)
        thread_manager = create_thread_manager(interaction)

        await handle_summary_command(context, response_sender, thread_manager, hours=hours, bot_user=bot.user)

    except Exception as e:
        logger.error(f"Error in {command_name} slash command: {e}", exc_info=True)
        try:
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
            await interaction.followup.send(error_message, ephemeral=True, allowed_mentions=allowed_mentions)
        except (discord.HTTPException, discord.Forbidden, discord.NotFound) as followup_error:
            logger.warning(f"Failed to send error followup for {command_name}: {followup_error}")
        except Exception as unexpected_error:
            logger.error(f"Unexpected error sending followup for {command_name}: {unexpected_error}", exc_info=True)

# Slash Commands
@bot.tree.command(name="sum-day", description="Generate a summary of messages from today")
async def sum_day_slash(interaction: discord.Interaction):
    """Slash command version of /sum-day"""
    await _handle_slash_command_wrapper(interaction, "sum-day", hours=24)

@bot.tree.command(name="sum-hr", description="Generate a summary of messages from the past N hours")
async def sum_hr_slash(interaction: discord.Interaction, hours: int):
    """Slash command version of /sum-hr"""
    # Immediately defer to avoid timeout, then do validation in wrapper
    await _handle_slash_command_wrapper(interaction, "sum-hr", hours=hours)

@bot.tree.command(name="points", description="Check your points or another user's points")
async def points_slash(interaction: discord.Interaction, user: discord.User = None):
    """
    Slash command to check points for yourself or another user.

    Args:
        interaction: The Discord interaction
        user: Optional user to check points for (defaults to command user)
    """
    try:
        # Determine which user to check
        target_user = user if user else interaction.user

        # Get guild ID
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)
        user_id = str(target_user.id)

        # Get points from database
        points = database.get_user_points(user_id, guild_id)

        # Format response
        if target_user.id == interaction.user.id:
            message = f"🏆 **Your Points**: {points}"
        else:
            message = f"🏆 **{target_user.display_name}'s Points**: {points}"

        await interaction.response.send_message(message, ephemeral=True)
        logger.info(f"User {interaction.user.name} checked points for {target_user.name}: {points}")

    except Exception as e:
        logger.error(f"Error in /points command: {str(e)}", exc_info=True)
        await interaction.response.send_message(
            "❌ An error occurred while retrieving points. Please try again later.",
            ephemeral=True
        )

@bot.tree.command(name="leaderboard", description="View the top users by points")
async def leaderboard_slash(interaction: discord.Interaction, limit: int = 10):
    """
    Slash command to display the points leaderboard.

    Args:
        interaction: The Discord interaction
        limit: Number of top users to display (default: 10, max: 25)
    """
    try:
        # Validate limit
        if limit < 1:
            await interaction.response.send_message(
                "❌ Limit must be at least 1.",
                ephemeral=True
            )
            return

        if limit > 25:
            await interaction.response.send_message(
                "❌ Limit cannot exceed 25 users.",
                ephemeral=True
            )
            return

        # Get guild ID
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)

        # Get leaderboard from database
        leaderboard = database.get_leaderboard(guild_id, limit)

        if not leaderboard:
            await interaction.response.send_message(
                "📊 No points have been awarded yet. Start contributing to the community!",
                ephemeral=True
            )
            return

        # Format leaderboard message
        message = f"🏆 **Top {len(leaderboard)} Contributors**\n\n"

        for idx, entry in enumerate(leaderboard, 1):
            author_name = entry['author_name']
            total_points = entry['total_points']

            # Add medal emojis for top 3
            if idx == 1:
                medal = "🥇"
            elif idx == 2:
                medal = "🥈"
            elif idx == 3:
                medal = "🥉"
            else:
                medal = f"{idx}."

            message += f"{medal} **{author_name}**: {total_points} points\n"

        await interaction.response.send_message(message, ephemeral=False)
        logger.info(f"User {interaction.user.name} requested leaderboard (top {limit})")

    except Exception as e:
        logger.error(f"Error in /leaderboard command: {str(e)}", exc_info=True)
        await interaction.response.send_message(
            "❌ An error occurred while retrieving the leaderboard. Please try again later.",
            ephemeral=True
        )


@bot.tree.command(name="ask", description="Ask a question using context from past conversations in this server")
async def ask_slash(interaction: discord.Interaction, question: str, hours: int = 24):
    """
    Slash command to ask questions based on database conversation history.

    Args:
        interaction: The Discord interaction
        question: The question to ask
        hours: Number of hours of history to search (default: 24, max: 168)
    """
    try:
        # Validate hours
        if hours < 1:
            await interaction.response.send_message(
                "Hours must be at least 1.",
                ephemeral=True
            )
            return

        if hours > 168:
            hours = 168  # Cap at 7 days

        # Get guild ID
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)
        channel_id = str(interaction.channel.id) if interaction.channel else None
        channel_name = interaction.channel.name if hasattr(interaction.channel, 'name') else "general"

        # Send initial message with processing indicator
        await interaction.response.send_message("🔍 Processing your question, please wait...")
        initial_message = await interaction.original_response()

        # Extract keywords from the question for search
        # Simple keyword extraction: split by spaces, filter short words
        words = question.lower().split()
        keywords = [w.strip('?.,!:;') for w in words if len(w) > 3]

        # Remove common stop words
        stop_words = {'what', 'when', 'where', 'which', 'that', 'this', 'with', 'from', 'have', 'been', 'were', 'they', 'their', 'about', 'could', 'would', 'should', 'there', 'here', 'does', 'more', 'some', 'into', 'just', 'also', 'than', 'then', 'only'}
        keywords = [w for w in keywords if w not in stop_words]

        # Get messages - either by keyword search or recent messages
        messages = []
        if keywords:
            # Search by keywords
            messages = await asyncio.to_thread(
                database.search_messages_by_keywords,
                keywords=keywords[:5],  # Limit to 5 keywords
                guild_id=guild_id,
                hours=hours,
                limit=75
            )

        # If keyword search found few results, supplement with recent messages
        if len(messages) < 20:
            recent_messages = await asyncio.to_thread(
                database.get_recent_messages_for_context,
                guild_id=guild_id,
                hours=hours,
                limit=100 - len(messages)
            )
            # Merge, avoiding duplicates
            existing_ids = {m['id'] for m in messages}
            for msg in recent_messages:
                if msg['id'] not in existing_ids:
                    messages.append(msg)

        # Sort by time (oldest first for conversation flow)
        messages.sort(key=lambda x: x.get('created_at', datetime.min))

        # Call the LLM with database context
        response = await call_llm_with_database_context(
            query=question,
            messages=messages,
            channel_name=channel_name
        )

        # Create a thread attached to the initial message
        thread_name = f"Q: {question[:50]}{'...' if len(question) > 50 else ''}"

        try:
            thread = await initial_message.create_thread(
                name=thread_name,
                auto_archive_duration=1440  # 24 hours
            )
        except discord.HTTPException as e:
            logger.warning(f"Failed to create thread from message: {e}, falling back to channel thread")
            thread = await interaction.channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=1440
            )

        # Send response in the thread
        response_parts = await split_long_message(response, max_length=1900)
        for part in response_parts:
            await thread.send(part)

        # Edit the initial message to show the question
        time_desc = "24 hours" if hours == 24 else f"{hours} hours"
        await initial_message.edit(
            content=f"❓ **Question:** {question}\n*Searched {len(messages)} messages from the past {time_desc}*"
        )

        logger.info(f"User {interaction.user.name} used /ask: '{question[:50]}...' - found {len(messages)} messages")

        # Store the question as a command in the database
        await asyncio.to_thread(
            database.store_message,
            message_id=str(interaction.id),
            author_id=str(interaction.user.id),
            author_name=str(interaction.user),
            channel_id=channel_id or "",
            channel_name=channel_name,
            guild_id=guild_id,
            guild_name=interaction.guild.name if interaction.guild else "",
            content=f"/ask {question}",
            created_at=datetime.now(timezone.utc),
            is_bot=False,
            is_command=True,
            command_type="ask"
        )

    except Exception as e:
        logger.error(f"Error in /ask command: {str(e)}", exc_info=True)
        try:
            await interaction.followup.send(
                "An error occurred while processing your question. Please try again later.",
                ephemeral=True
            )
        except Exception:
            pass


try:
    logger.info("Starting bot...")
    import config # Assuming config.py is in the same directory or accessible

    # Validate configuration using the imported function
    validate_config(config)

    # Log startup (but mask the actual token)
    token_preview = config.token[:5] + "..." + config.token[-5:] if len(config.token) > 10 else "***masked***"
    logger.info(f"Bot token loaded: {token_preview}")
    logger.info("Connecting to Discord...")

    # Run the bot
    bot.run(config.token)
except ImportError:
    logger.critical("Config file not found or token not defined", exc_info=True)
    logger.error("Please create a config.py file with your Discord bot token.")
    logger.error("Example: token = 'YOUR_DISCORD_BOT_TOKEN'")
except discord.LoginFailure:
    logger.critical("Invalid Discord token. Please check your token in config.py", exc_info=True)
except Exception as e:
    logger.critical(f"Unexpected error during bot startup: {e}", exc_info=True)
