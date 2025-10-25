"""
Discord bot for TechFren community with summarization, thread memory, and content scraping.
"""

import asyncio
import json
import os
import re
from typing import Optional

import discord
from discord.ext import commands

import database
from logging_config import logger

# from rate_limiter import (
#     check_rate_limit,
#     update_rate_limit_config,
# )  # Import rate limiting functions - commented out as unused
from llm_handler import (
    summarize_scraped_content,
)  # Import LLM functions

# from message_utils import split_long_message  # Import message utility
# functions - commented out as unused
from youtube_handler import (
    is_youtube_url,
    scrape_youtube_content,
)  # Import YouTube functions
from summarization_tasks import (
    daily_channel_summarization,
    set_discord_client,
)  # Import summarization tasks
from config_validator import validate_config  # Import config validator
from command_handler import (
    handle_bot_command,
    handle_sum_day_command,
    handle_sum_hr_command,
    handle_chart_day_command,
    handle_chart_hr_command,
)  # Import command handlers
from thread_memory import process_thread_memory_command
from firecrawl_handler import scrape_url_content  # Import Firecrawl handler
from apify_handler import scrape_twitter_content, is_twitter_url  # Import Apify handler

# Using message_content intent (requires enabling in the Discord Developer Portal)
intents = discord.Intents.default()
intents.message_content = (
    True  # This is required to read message content in guild channels
)

# Use commands.Bot instead of discord.Client to support slash commands
bot = commands.Bot(command_prefix="!", intents=intents)

# Keep client reference for backward compatibility
client = bot

# Track processed messages to prevent duplicate handling
_processed_messages = set()
_PROCESSED_MESSAGES_MAX_SIZE = 1000  # Prevent memory leak
_message_lock = asyncio.Lock()  # Prevent race conditions at message level


async def _handle_youtube_url(url: str) -> str:
    """Handle YouTube URL processing."""
    logger.info("Detected YouTube URL: %s", url)

    scraped_result = await scrape_youtube_content(url)

    if not scraped_result:
        logger.warning(
            "Failed to scrape YouTube content, falling back to Firecrawl: %s",
            url
        )
        scraped_result = await scrape_url_content(url)
    else:
        logger.info("Successfully scraped YouTube content: %s", url)

    return scraped_result.get("markdown") if scraped_result else None


async def _handle_twitter_url(url: str) -> str:
    """Handle Twitter/X.com URL processing."""
    logger.info("Detected Twitter/X.com URL: %s", url)

    from apify_handler import extract_tweet_id

    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        logger.warning(
            "URL appears to be Twitter/X.com but doesn't contain "
            "a valid tweet ID: %s",
            url
        )

        # Handle base Twitter/X.com URLs
        if url.lower() in [
            "https://x.com",
            "https://twitter.com",
            "http://x.com",
            "http://twitter.com",
        ]:
            logger.info(
                "Handling base Twitter/X.com URL with custom response: %s", url
            )
            return (
                f"# Twitter/X.com\n\n" f"This is the main page of Twitter/X.com: {url}"
            )
        scraped_result = await scrape_url_content(url)
        return scraped_result if scraped_result else None

    # Check if Apify API token is configured
    if not hasattr(config, "apify_api_token") or not config.apify_api_token:
        logger.warning(
            "Apify API token not found in config.py or is empty, "
            "falling back to Firecrawl"
        )
        scraped_result = await scrape_url_content(url)
    else:
        scraped_result = await scrape_twitter_content(url)

        if not scraped_result:
            logger.warning(
                "Failed to scrape Twitter/X.com content with Apify, "
                "falling back to Firecrawl: %s",
                url
            )
            scraped_result = await scrape_url_content(url)
        else:
            logger.info(
                "Successfully scraped Twitter/X.com content with Apify: %s", url
            )

    return scraped_result.get("markdown") if scraped_result else None


async def _scrape_url_by_type(url: str):
    """Scrape URL content based on URL type."""
    if await is_youtube_url(url):
        return await _handle_youtube_url(url)
    if await is_twitter_url(url):
        return await _handle_twitter_url(url)
    return await scrape_url_content(url)


async def _extract_markdown_content(scraped_result, url: str) -> str:
    """Extract markdown content from scraped result based on result type."""
    if not scraped_result:
        logger.warning("Failed to scrape content from URL: %s", url)
        return None

    # Check if it's a YouTube URL
    if await is_youtube_url(url):
        if isinstance(scraped_result, dict) and "markdown" in scraped_result:
            return scraped_result.get("markdown", "")
        logger.warning(
            "Invalid scraped result structure for YouTube URL %s: "
            "expected dict with 'markdown' key",
            url
        )
        return None

    # Check if it's a Twitter URL with Apify
    if (
        await is_twitter_url(url)
        and hasattr(config, "apify_api_token")
        and config.apify_api_token
    ):
        if isinstance(scraped_result, dict) and "markdown" in scraped_result:
            return scraped_result.get("markdown", "")
        logger.warning(
            "Invalid scraped result structure for Twitter URL %s: "
            "expected dict with 'markdown' key",
            url
        )
        return None

    # Handle Firecrawl string result
    if isinstance(scraped_result, str):
        return scraped_result

    logger.warning(
        "Invalid scraped result for URL %s: expected string, got %s",
        url,
        type(scraped_result)
    )
    return None


async def process_url(message_id: str, url: str):
    """
    Process a URL found in a message by scraping its content, summarizing it,
    and updating the message in the database with the scraped data.

    Args:
        message_id (str): The ID of the message containing the URL
        url (str): The URL to process
    """
    try:
        logger.info("Processing URL %s from message %s", url, message_id)

        # Step 1: Scrape URL content
        scraped_result = await _scrape_url_by_type(url)
        markdown_content = await _extract_markdown_content(scraped_result, url)

        if not markdown_content:
            return

        # Step 2: Summarize the scraped content
        scraped_data = await summarize_scraped_content(markdown_content, url)
        if not scraped_data:
            logger.warning("Failed to summarize content from URL: %s", url)
            return

        # Step 3: Convert key points to JSON string
        key_points_json = json.dumps(scraped_data.get("key_points", []))

        # Step 4: Update the message in the database with the scraped data
        success = await database.update_message_with_scraped_data(
            message_id, url, scraped_data.get("summary", ""), key_points_json
        )

        if success:
            logger.info(
                "Successfully processed URL %s from message %s", url, message_id
            )
        else:
            logger.warning(
                "Failed to update message %s with scraped data", message_id
            )

    except Exception as e:
        logger.error(
            "Error processing URL %s from message %s: %s",
            url,
            message_id,
            str(e),
            exc_info=True,
        )


def _is_links_dump_channel(message: discord.Message, config) -> bool:
    """Check if message is in the links dump channel."""
    if str(message.channel.id) == config.links_dump_channel_id:
        return True
    if (
        isinstance(message.channel, discord.Thread)
        and str(message.channel.parent_id) == config.links_dump_channel_id
    ):
        logger.info(
            "Message %s is in a thread from links dump channel, allowing",
            message.id
        )
        return False
    return False


def _should_allow_message(message: discord.Message) -> bool:
    """Check if message should be allowed in links dump channel."""
    # Don't handle bot messages or commands
    if message.author.bot:
        return True

    # Check for URLs in the message content
    url_pattern = r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?"
    urls = re.findall(url_pattern, message.content)

    # If message contains URLs, allow it
    if urls:
        logger.info(
            "Message %s in links dump channel contains URL, allowing", message.id
        )
        return True

    # Always allow forwarded messages from other channels
    if (
        message.reference
        and message.reference.message_id
        and (message.reference.channel_id != message.channel.id)
    ):
        logger.info(
            "Message %s is forwarded from another channel, allowing", message.id
        )
        return True

    return False


async def _delete_non_link_message(message: discord.Message):
    """Delete non-link message with warning."""
    logger.info(
        "Deleting non-link message %s in links dump channel", message.id
    )

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
            logger.info(
                "Deleted original message %s from links dump channel", message.id
            )
        except discord.NotFound:
            logger.info("Original message %s already deleted", message.id)
        except discord.Forbidden:
            logger.warning(
                "No permission to delete original message %s", message.id
            )
        except Exception as e:
            logger.error(
                "Error deleting original message %s: %s", message.id, e
            )

        try:
            await warning_msg.delete()
            logger.info("Deleted warning message %s", warning_msg.id)
        except discord.NotFound:
            logger.info("Warning message %s already deleted", warning_msg.id)
        except discord.Forbidden:
            logger.warning(
                "No permission to delete warning message %s", warning_msg.id
            )
        except Exception as e:
            logger.error("Error deleting warning message %s: %s", warning_msg.id, e)

    # Start the deletion task
    asyncio.create_task(delete_messages())


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
        if (
            not hasattr(config, "links_dump_channel_id")
            or not config.links_dump_channel_id
        ):
            return False

        # Check if this is the links dump channel
        is_links_dump = _is_links_dump_channel(message, config)
        if not is_links_dump:
            return False

        # Check if message should be allowed
        if _should_allow_message(message):
            return False

        # Message doesn't contain URLs, delete it with warning
        await _delete_non_link_message(message)
        return True  # Message was handled (will be deleted)

    except Exception as e:
        logger.error(
            "Error handling links dump channel message %s: %s",
            message.id,
            e,
            exc_info=True,
        )
        return False


@bot.event
async def on_ready():
    """Handle bot ready event - initialize database and start tasks."""
    set_discord_client(bot)  # Set the client instance for summarization tasks
    logger.info("Bot has successfully connected as %s", bot.user)
    logger.info("Bot ID: %s", bot.user.id)
    logger.info("Connected to %d guilds", len(bot.guilds))

    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        logger.info("Synced %d command(s)", len(synced))
    except Exception as e:
        logger.error("Failed to sync commands: %s", e)

    # Initialize the database - critical for bot operation
    try:
        await database.init_database()

        # Check if database connection is working
        if not await database.check_database_connection():
            logger.critical("Database connection check failed. Shutting down.")
            await bot.close()
            return

        message_count = await database.get_message_count()
        logger.info(
            "Database initialized successfully. Current message count: %d",
            message_count
        )

        # Log database file information
        db_file_path = os.path.join(os.getcwd(), database.DB_FILE)
        if os.path.exists(db_file_path):
            logger.info("Database file exists at: %s", db_file_path)
            logger.info(
                "Database file size: %d bytes", os.path.getsize(db_file_path)
            )
        else:
            logger.critical("Database file does not exist at: %s", db_file_path)
            await bot.close()
            return
    except Exception as e:
        logger.critical(
            "Failed to initialize database: %s", str(e), exc_info=True
        )
        logger.critical(
            "Database initialization is required for bot operation. Shutting down."
        )
        await bot.close()
        return

    # Start the daily summarization task if not already running
    if not daily_channel_summarization.is_running():
        daily_channel_summarization.start()
        logger.info("Started daily channel summarization task")

    # Log details about each connected guild
    for guild in bot.guilds:
        logger.info(
            "Connected to guild: %s (ID: %d) - %d members",
            guild.name,
            guild.id,
            len(guild.members)
        )


@bot.event
async def on_guild_join(guild):
    """Log when the bot joins a new guild"""
    logger.info(
        "Bot joined new guild: %s (ID: %d) - %d members",
        guild.name,
        guild.id,
        len(guild.members)
    )


@bot.event
async def on_guild_remove(guild):
    """Log when the bot is removed from a guild"""
    logger.info("Bot removed from guild: %s (ID: %d)", guild.name, guild.id)


@bot.event
async def on_error(event, *args, **kwargs):
    """Log Discord API errors"""
    logger.error("Discord error in %s", event, exc_info=True)
    # Log additional context if available
    if args:
        logger.error("Error context args: %s", args)
    if kwargs:
        logger.error("Error context kwargs: %s", kwargs)


def _get_channel_info(message):
    """Get channel and guild information from message."""
    guild_name = message.guild.name if message.guild else "DM"

    if hasattr(message.channel, "name"):
        channel_name = message.channel.name
    elif hasattr(message.channel, "recipient"):
        channel_name = f"DM with {message.channel.recipient}"
    else:
        channel_name = "Unknown Channel"

    return guild_name, channel_name


def _get_author_display(message):
    """Get author display name from message."""
    return (
        message.author.display_name
        if isinstance(message.author, discord.Member)
        else str(message.author)
    )


def _detect_command_type(message, bot_user_id):
    """Detect if message is a command and return command type."""
    is_command = False
    command_type = None

    bot_mention = f"<@{bot_user_id}>"
    bot_mention_alt = f"<@!{bot_user_id}>"

    if message.content.startswith(bot_mention) or message.content.startswith(
        bot_mention_alt
    ):
        is_command = True
        command_type = "mention"
    elif message.content.startswith("/bot"):
        is_command = True
        command_type = "/bot"
    elif message.content.startswith("/sum-day"):
        is_command = True
        command_type = "/sum-day"
    elif message.content.startswith("/sum-hr"):
        is_command = True
        command_type = "/sum-hr"
    elif message.content.startswith("/chart-day"):
        is_command = True
        command_type = "/chart-day"
    elif message.content.startswith("/chart-hr"):
        is_command = True
        command_type = "/chart-hr"
    elif message.content.startswith("/thread-memory"):
        is_command = True
        command_type = "/thread-memory"

    return is_command, command_type


async def _store_message_in_database(
    message, guild_name, channel_name, is_command, command_type
):
    """Store message in database."""
    try:
        guild_id = str(message.guild.id) if message.guild else None
        channel_id = str(message.channel.id)

        if not database:
            logger.error("Database module not properly imported or initialized")
            return

        success = await database.store_message(
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
        )

        if not success:
            logger.debug(
                "Failed to store message %s in database (likely duplicate)",
                message.id
            )
    except Exception as e:
        logger.error(
            "Error storing message in database: %s", str(e), exc_info=True
        )


def _check_command_types(message, bot_user_id):
    """Check what type of commands the message contains."""
    bot_mention = f"<@{bot_user_id}>"
    bot_mention_alt = f"<@!{bot_user_id}>"

    return {
        "is_mention_command": bot_mention in message.content
        or bot_mention_alt in message.content,
        "is_sum_day_command": message.content.startswith("/sum-day"),
        "is_sum_hr_command": message.content.startswith("/sum-hr"),
        "is_chart_day_command": message.content.startswith("/chart-day"),
        "is_chart_hr_command": message.content.startswith("/chart-hr"),
        "is_thread_memory_command": message.content.startswith("/thread-memory"),
    }


async def _should_process_message(message) -> bool:
    """Check if message should be processed."""
    if message.author == bot.user:
        return False

    handled_by_links_dump = await handle_links_dump_channel(message)
    return not handled_by_links_dump


async def _log_message_info(
    message, guild_name: str, channel_name: str, author_display: str
):
    """Log message information."""
    content_preview = (
        message.content[:50] + "..." if len(message.content) > 50 else message.content
    )
    logger.info(
        "Message received - Guild: %s | Channel: %s | Author: %s | Content: %s",
        guild_name,
        channel_name,
        author_display,
        content_preview
    )


async def _is_recognized_command(commands: dict) -> bool:
    """Check if any recognized command is present."""
    return any(
        [
            commands["is_sum_day_command"],
            commands["is_sum_hr_command"],
            commands["is_chart_day_command"],
            commands["is_chart_hr_command"],
            commands["is_thread_memory_command"],
        ]
    )


async def _is_channel_allowed(message) -> bool:
    """Check if message is in an allowed channel."""
    if not message.guild or not hasattr(message.channel, "name"):
        return True

    allowed_channels = [config.ALLOWED_CHANNEL_NAME]
    if message.channel.name not in allowed_channels:
        logger.debug(
            "Command ignored - channel #%s not in allowed channels: %s",
            message.channel.name,
            allowed_channels
        )
        return False
    return True


async def _process_command(message, commands: dict):
    """Process the recognized command."""
    if commands["is_sum_day_command"]:
        await handle_sum_day_command(message, bot.user)
    elif commands["is_sum_hr_command"]:
        await handle_sum_hr_command(message, bot.user)
    elif commands["is_chart_day_command"]:
        await handle_chart_day_command(message, bot.user)
    elif commands["is_chart_hr_command"]:
        await handle_chart_hr_command(message, bot.user)
    elif commands["is_thread_memory_command"]:
        try:
            command_parts = message.content.split()
            response = await process_thread_memory_command(message, command_parts)
            await message.channel.send(response)
        except Exception as e:
            logger.error("Error processing thread memory command: %s", e)
            await message.channel.send(
                "Sorry, an error occurred while processing the thread memory command."
            )


@bot.event
async def on_message(message):
    """Handle incoming messages and process commands."""
    # Check if message should be processed
    if not await _should_process_message(message):
        return

    # Check for duplicate message processing with async lock to prevent race conditions
    # Because Discord sends the same message in both channel and auto-created thread
    async with _message_lock:
        message_key = message.id  # Only use message ID, not (message.id, channel.id)
        if message_key in _processed_messages:
            logger.warning(
                "DUPLICATE DETECTED: Skipping duplicate processing of "
                "message %s (channel: %s, type: %s)",
                message.id,
                message.channel.id,
                type(message.channel).__name__
            )
            return

        # Add to processed set and maintain size limit
        logger.info(
            "✅ Message %s not in cache, processing (channel: %s, cache size: %d)",
            message.id,
            message.channel.id,
            len(_processed_messages)
        )
        _processed_messages.add(message_key)
        if len(_processed_messages) > _PROCESSED_MESSAGES_MAX_SIZE:
            # Remove oldest half of messages to prevent memory leak
            to_remove = list(_processed_messages)[:_PROCESSED_MESSAGES_MAX_SIZE // 2]
            for key in to_remove:
                _processed_messages.discard(key)

    # Get channel and author information
    guild_name, channel_name = _get_channel_info(message)
    author_display = _get_author_display(message)
    await _log_message_info(message, guild_name, channel_name, author_display)

    # Detect command type and store message in database
    is_command, command_type = _detect_command_type(message, bot.user.id)
    await _store_message_in_database(
        message, guild_name, channel_name, is_command, command_type
    )

    # Check command types
    commands = _check_command_types(message, bot.user.id)

    # Process mention commands in any channel
    if commands["is_mention_command"]:
        logger.debug("Processing mention command in channel #%s", channel_name)
        await handle_bot_command(message, bot.user, bot)
        return

    # Check if recognized command exists
    if not await _is_recognized_command(commands):
        return

    # Check if channel is allowed
    if not await _is_channel_allowed(message):
        return

    # Process the command
    await _process_command(message, commands)


async def _ensure_interaction_deferred(
    interaction: discord.Interaction, command_name: str
) -> bool:
    """Ensure interaction is deferred, return False if failed."""
    if not interaction.response.is_done():
        logger.debug(
            "Interaction for %s not yet deferred, deferring now", command_name
        )
        try:
            await interaction.response.defer()
        except discord.errors.NotFound as e:
            logger.error(
                "Interaction for %s expired before defer: %s", command_name, e
            )
            return False
        except Exception as e:
            logger.error(
                "Failed to defer interaction for %s: %s", command_name, e
            )
            return False
    return True


async def _validate_hours_parameter(
    interaction: discord.Interaction, command_name: str, hours: int
) -> tuple[bool, int, str]:
    """
    Validate hours parameter for commands.

    Returns (is_valid, hours, error_message).
    """
    import config

    if command_name == "chart-day":
        hours = 24  # Ensure hours is set for chart-day

    if command_name in ["sum-hr", "chart-hr"]:
        if hours < 1 or hours > config.MAX_SUMMARY_HOURS:
            try:
                allowed_mentions = discord.AllowedMentions(
                    everyone=False, roles=False, users=True
                )
                await interaction.followup.send(
                    config.ERROR_MESSAGES["invalid_hours_range"],
                    ephemeral=True,
                    allowed_mentions=allowed_mentions,
                )
                return False, hours, ""
            except Exception as e:
                logger.error(
                    "Failed to send validation error for %s: %s", command_name, e
                )
                return False, hours, ""

        # Warn for large summaries that may take longer
        error_message = ""
        if hours > config.LARGE_SUMMARY_THRESHOLD:
            error_message = (
                config.ERROR_MESSAGES["large_summary_warning"].format(hours=hours)
                + " and could impact performance."
            )
        return True, hours, error_message

    return True, hours, ""


async def _send_error_followup(
    interaction: discord.Interaction, command_name: str, error_message: str
):
    """Send error followup if interaction is still valid."""
    if not interaction.is_expired():
        try:
            allowed_mentions = discord.AllowedMentions(
                everyone=False, roles=False, users=True
            )
            await interaction.followup.send(
                error_message, ephemeral=True, allowed_mentions=allowed_mentions
            )
        except (
            discord.HTTPException,
            discord.Forbidden,
            discord.NotFound,
        ) as followup_error:
            logger.warning(
                "Failed to send error followup for %s: %s",
                command_name,
                followup_error
            )
        except Exception as unexpected_error:
            logger.error(
                "Unexpected error sending followup for %s: %s",
                command_name,
                unexpected_error,
                exc_info=True,
            )


# Helper function for slash command handling
async def _handle_slash_command_wrapper(
    interaction: discord.Interaction,
    command_name: str,
    hours: int = 24,
    error_message: Optional[str] = None,
    force_charts: bool = False,
) -> None:
    """Unified wrapper for slash command handling with error management."""
    # Ensure interaction is deferred
    if not await _ensure_interaction_deferred(interaction, command_name):
        return

    if error_message is None:
        error_message = (
            f"Sorry, an error occurred while processing the {command_name} "
            "command. Please try again later."
        )

    # Validate hours parameter
    is_valid, hours, validation_error = await _validate_hours_parameter(
        interaction, command_name, hours
    )
    if not is_valid:
        return
    if validation_error:
        error_message = validation_error

    try:
        from command_abstraction import (
            create_context_from_interaction,
            create_response_sender,
            create_thread_manager,
            handle_summary_command,
        )

        context = create_context_from_interaction(
            interaction, f"/{command_name}" + (f" {hours}" if hours != 24 else "")
        )
        response_sender = create_response_sender(interaction)
        thread_manager = create_thread_manager(interaction)

        await handle_summary_command(
            context,
            response_sender,
            thread_manager,
            hours=hours,
            bot_user=bot.user,
            force_charts=force_charts,
        )

    except Exception as e:
        logger.error(
            "Error in %s slash command: %s", command_name, e, exc_info=True
        )
        await _send_error_followup(interaction, command_name, error_message)


# Slash Commands
@bot.tree.command(
    name="sum-day", description="Generate a summary of messages from today"
)
async def sum_day_slash(interaction: discord.Interaction):
    """Slash command version of /sum-day"""
    await interaction.response.defer()
    await _handle_slash_command_wrapper(interaction, "sum-day", hours=24)


@bot.tree.command(
    name="sum-hr", description="Generate a summary of messages from the past N hours"
)
async def sum_hr_slash(interaction: discord.Interaction, hours: int):
    """Slash command version of /sum-hr"""
    await interaction.response.defer()
    await _handle_slash_command_wrapper(interaction, "sum-hr", hours=hours)


@bot.tree.command(
    name="chart-day",
    description="Generate data analysis with charts for today's messages",
)
async def chart_day_slash(interaction: discord.Interaction):
    """Slash command version of /chart-day for data visualization"""
    await interaction.response.defer()
    await _handle_slash_command_wrapper(
        interaction, "chart-day", hours=24, force_charts=True
    )


@bot.tree.command(
    name="chart-hr",
    description="Generate data analysis with charts for the past N hours",
)
async def chart_hr_slash(interaction: discord.Interaction, hours: int):
    """Slash command version of /chart-hr for data visualization"""
    await interaction.response.defer()
    await _handle_slash_command_wrapper(
        interaction, "chart-hr", hours=hours, force_charts=True
    )


try:
    logger.info("Starting bot...")
    import config  # Assuming config.py is in the same directory or accessible

    # Validate configuration using the imported function
    validate_config(config)

    # Log startup (but mask the actual token)
    token_preview = (
        config.token[:5] + "..." + config.token[-5:]
        if len(config.token) > 10
        else "***masked***"
    )
    logger.info("Bot token loaded: %s", token_preview)
    logger.info("Connecting to Discord...")

    # Run the bot
    bot.run(config.token)
except ImportError:
    logger.critical("Config file not found or token not defined", exc_info=True)
    logger.error("Please create a config.py file with your Discord bot token.")
    logger.error("Example: token = 'YOUR_DISCORD_BOT_TOKEN'")
except discord.LoginFailure:
    logger.critical(
        "Invalid Discord token. Please check your token in config.py", exc_info=True
    )
except Exception as e:
    logger.critical("Unexpected error during bot startup: %s", e, exc_info=True)
