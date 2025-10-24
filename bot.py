# This example requires the 'message_content' intent.

import discord
from discord.ext import commands
import asyncio
import re
import os
import json
from typing import Optional
import database
from logging_config import logger  # Import the logger from the new module
# from rate_limiter import (
#     check_rate_limit,
#     update_rate_limit_config,
# )  # Import rate limiting functions - commented out as unused
from llm_handler import (
    summarize_scraped_content,
)  # Import LLM functions
# from message_utils import split_long_message  # Import message utility functions - commented out as unused
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


async def _handle_youtube_url(url: str) -> str:
    """Handle YouTube URL processing."""
    logger.info(f"Detected YouTube URL: {url}")

    scraped_result = await scrape_youtube_content(url)

    if not scraped_result:
        logger.warning(f"Failed to scrape YouTube content, falling back to Firecrawl: {url}")
        scraped_result = await scrape_url_content(url)
    else:
        logger.info(f"Successfully scraped YouTube content: {url}")

    return scraped_result.get("markdown") if scraped_result else None


async def _handle_twitter_url(url: str) -> str:
    """Handle Twitter/X.com URL processing."""
    logger.info(f"Detected Twitter/X.com URL: {url}")

    from apify_handler import extract_tweet_id

    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        logger.warning(f"URL appears to be Twitter/X.com but doesn't contain a valid tweet ID: {url}")

        # Handle base Twitter/X.com URLs
        if url.lower() in ["https://x.com", "https://twitter.com", "http://x.com", "http://twitter.com"]:
            logger.info(f"Handling base Twitter/X.com URL with custom response: {url}")
            return f"# Twitter/X.com\n\nThis is the main page of Twitter/X.com: {url}"
        else:
            scraped_result = await scrape_url_content(url)
            return scraped_result if scraped_result else None
    else:
        # Check if Apify API token is configured
        if not hasattr(config, "apify_api_token") or not config.apify_api_token:
            logger.warning("Apify API token not found in config.py or is empty, falling back to Firecrawl")
            scraped_result = await scrape_url_content(url)
        else:
            scraped_result = await scrape_twitter_content(url)

            if not scraped_result:
                logger.warning(f"Failed to scrape Twitter/X.com content with Apify, falling back to Firecrawl: {url}")
                scraped_result = await scrape_url_content(url)
            else:
                logger.info(f"Successfully scraped Twitter/X.com content with Apify: {url}")

        return scraped_result.get("markdown") if scraped_result else None


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

        # Process URL based on type
        if await is_youtube_url(url):
            markdown_content = await _handle_youtube_url(url)
        elif await is_twitter_url(url):
            markdown_content = await _handle_twitter_url(url)
        else:
            # For other URLs, use Firecrawl
            scraped_result = await scrape_url_content(url)
            markdown_content = scraped_result.get("markdown") if scraped_result else None
            markdown_content = scraped_result  # Firecrawl returns markdown directly

        # Check if scraping was successful
        if not scraped_result:
            logger.warning(f"Failed to scrape content from URL: {url}")
            return

        # Handle different types of scraped results
        if await is_youtube_url(url):
            # YouTube handler returns a dict with 'markdown' key
            if isinstance(scraped_result, dict) and "markdown" in scraped_result:
                markdown_content = scraped_result.get("markdown", "")
            else:
                logger.warning(
                    f"Invalid scraped result structure for YouTube URL {url}: expected dict with 'markdown' key"
                )
                return
        elif (
            await is_twitter_url(url)
            and hasattr(config, "apify_api_token")
            and config.apify_api_token
        ):
            # Twitter/X.com URLs scraped with Apify return a dict with 'markdown' key
            if isinstance(scraped_result, dict) and "markdown" in scraped_result:
                markdown_content = scraped_result.get("markdown", "")
            else:
                logger.warning(
                    f"Invalid scraped result structure for Twitter URL {url}: expected dict with 'markdown' key"
                )
                return
        else:
            # Firecrawl returns markdown directly as a string
            if isinstance(scraped_result, str):
                markdown_content = scraped_result
            else:
                logger.warning(
                    f"Invalid scraped result for URL {url}: expected string, got {type(scraped_result)}"
                )
                return

        # Step 2: Summarize the scraped content
        scraped_data = await summarize_scraped_content(markdown_content, url)
        if not scraped_data:
            logger.warning(f"Failed to summarize content from URL: {url}")
            return

        # Step 3: Convert key points to JSON string
        key_points_json = json.dumps(scraped_data.get("key_points", []))

        # Step 4: Update the message in the database with the scraped data
        success = await database.update_message_with_scraped_data(
            message_id, url, scraped_data.get("summary", ""), key_points_json
        )

        if success:
            logger.info(f"Successfully processed URL {url} from message {message_id}")
        else:
            logger.warning(f"Failed to update message {message_id} with scraped data")

    except Exception as e:
        logger.error(
            f"Error processing URL {url} from message {message_id}: {str(e)}",
            exc_info=True,
        )


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

        # Check if this is the links dump channel or a thread within it
        is_links_dump_channel = False

        if str(message.channel.id) == config.links_dump_channel_id:
            # Direct message in the links dump channel
            is_links_dump_channel = True
        elif (
            isinstance(message.channel, discord.Thread)
            and str(message.channel.parent_id) == config.links_dump_channel_id
        ):
            # Message in a thread created from the links dump channel - allow these
            logger.info(
                f"Message {message.id} is in a thread from links dump channel, allowing"
            )
            return False

        if not is_links_dump_channel:
            return False

        # Don't handle bot messages or commands
        if message.author.bot:
            return False

        # Check for URLs in the message content using the same regex as process_url
        url_pattern = (
            r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?"
        )
        urls = re.findall(url_pattern, message.content)

        # If message contains URLs, allow it
        if urls:
            logger.info(
                f"Message {message.id} in links dump channel contains URL, allowing"
            )
            return False

        # Always allow forwarded messages from other channels
        if (
            message.reference
            and message.reference.message_id
            and (message.reference.channel_id != message.channel.id)
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
                logger.info(
                    f"Deleted original message {message.id} from links dump channel"
                )
            except discord.NotFound:
                logger.info(f"Original message {message.id} already deleted")
            except discord.Forbidden:
                logger.warning(f"No permission to delete original message {message.id}")
            except Exception as e:
                logger.error(f"Error deleting original message {message.id}: {e}")

            try:
                await warning_msg.delete()
                logger.info(
                    f"Deleted warning message {warning_msg.id} from links dump channel"
                )
            except discord.NotFound:
                logger.info(f"Warning message {warning_msg.id} already deleted")
            except discord.Forbidden:
                logger.warning(
                    f"No permission to delete warning message {warning_msg.id}"
                )
            except Exception as e:
                logger.error(f"Error deleting warning message {warning_msg.id}: {e}")

        # Create background task for deletion
        asyncio.create_task(delete_messages())

        return True  # Message was handled

    except Exception as e:
        logger.error(
            f"Error handling links dump channel message {message.id}: {e}",
            exc_info=True,
        )
        return False


@bot.event
async def on_ready():
    set_discord_client(bot)  # Set the client instance for summarization tasks
    logger.info(f"Bot has successfully connected as {bot.user}")
    logger.info(f"Bot ID: {bot.user.id}")
    logger.info(f"Connected to {len(bot.guilds)} guilds")

    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

    # Initialize the database - critical for bot operation
    try:
        database.init_database()

        # Check if database connection is working
        if not database.check_database_connection():
            logger.critical("Database connection check failed. Shutting down.")
            await bot.close()
            return

        message_count = database.get_message_count()
        logger.info(
            f"Database initialized successfully. Current message count: {message_count}"
        )

        # Log database file information
        db_file_path = os.path.join(os.getcwd(), database.DB_FILE)
        if os.path.exists(db_file_path):
            logger.info(f"Database file exists at: {db_file_path}")
            logger.info(f"Database file size: {os.path.getsize(db_file_path)} bytes")
        else:
            logger.critical(f"Database file does not exist at: {db_file_path}")
            await bot.close()
            return
    except Exception as e:
        logger.critical(f"Failed to initialize database: {str(e)}", exc_info=True)
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
            f"Connected to guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members"
        )


@bot.event
async def on_guild_join(guild):
    """Log when the bot joins a new guild"""
    logger.info(
        f"Bot joined new guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members"
    )


@bot.event
async def on_guild_remove(guild):
    """Log when the bot is removed from a guild"""
    logger.info(f"Bot removed from guild: {guild.name} (ID: {guild.id})")


@bot.event
async def on_error(event, *args, **kwargs):
    """Log Discord API errors"""
    logger.error(f"Discord error in {event}", exc_info=True)
    # Log additional context if available
    if args:
        logger.error(f"Error context args: {args}")
    if kwargs:
        logger.error(f"Error context kwargs: {kwargs}")


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

    if message.content.startswith(bot_mention) or message.content.startswith(bot_mention_alt):
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


async def _store_message_in_database(message, guild_name, channel_name, is_command, command_type):
    """Store message in database."""
    try:
        guild_id = str(message.guild.id) if message.guild else None
        channel_id = str(message.channel.id)

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
        )

        if not success:
            logger.debug(
                f"Failed to store message {message.id} in database (likely duplicate)"
            )
    except Exception as e:
        logger.error(f"Error storing message in database: {str(e)}", exc_info=True)


def _check_command_types(message, bot_user_id):
    """Check what type of commands the message contains."""
    bot_mention = f"<@{bot_user_id}>"
    bot_mention_alt = f"<@!{bot_user_id}>"

    return {
        "is_mention_command": bot_mention in message.content or bot_mention_alt in message.content,
        "is_sum_day_command": message.content.startswith("/sum-day"),
        "is_sum_hr_command": message.content.startswith("/sum-hr"),
        "is_chart_day_command": message.content.startswith("/chart-day"),
        "is_chart_hr_command": message.content.startswith("/chart-hr"),
        "is_thread_memory_command": message.content.startswith("/thread-memory"),
    }


@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Handle links dump channel logic first
    handled_by_links_dump = await handle_links_dump_channel(message)
    if handled_by_links_dump:
        return  # Message was handled (deleted), stop processing

    # Get channel and author information
    guild_name, channel_name = _get_channel_info(message)
    author_display = _get_author_display(message)

    logger.info(
        f"Message received - Guild: {guild_name} | Channel: {channel_name} | Author: {author_display} | Content: {message.content[:50]}{'...' if len(message.content) > 50 else ''}"
    )

    # Detect command type and store message in database
    is_command, command_type = _detect_command_type(message, bot.user.id)
    await _store_message_in_database(message, guild_name, channel_name, is_command, command_type)

    # Check command types
    commands = _check_command_types(message, bot.user.id)

    # Process mention commands in any channel
    if commands["is_mention_command"]:
        logger.debug(f"Processing mention command in channel #{channel_name}")
        await handle_bot_command(message, bot.user, bot)
        return

    # If not a command we recognize, ignore
    if not any([
        commands["is_sum_day_command"],
        commands["is_sum_hr_command"],
        commands["is_chart_day_command"],
        commands["is_chart_hr_command"],
        commands["is_thread_memory_command"]
    ]):
        return

    # Check allowed channels for non-mention commands
    if message.guild and hasattr(message.channel, "name"):
        allowed_channels = [ALLOWED_CHANNEL_NAME]
        if message.channel.name not in allowed_channels:
            logger.debug(
                f"Command ignored - channel #{message.channel.name} not in allowed channels: {allowed_channels}"
            )
            return

    # Process the command
    if commands["is_sum_day_command"]:
        await handle_summary_command(message, 24, False, bot.user)
    elif commands["is_sum_hr_command"]:
        await handle_summary_command(message, 1, False, bot.user)
    elif commands["is_chart_day_command"]:
        await handle_summary_command(message, 24, True, bot.user)
    elif commands["is_chart_hr_command"]:
        await handle_summary_command(message, 1, True, bot.user)
    elif commands["is_thread_memory_command"]:
        try:
            command_parts = message.content.split()
            response = await process_thread_memory_command(message, command_parts)
            await message.channel.send(response)
        except Exception as e:
            logger.error(f"Error processing thread memory command: {e}")
            await message.channel.send(
                "Sorry, an error occurred while processing the thread memory command."
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
    # Note: Interaction should already be deferred by the slash command handler
    # This is just a safety check in case it wasn't
    if not interaction.response.is_done():
        logger.warning(
            f"Interaction for {command_name} was not deferred by command handler, deferring now"
        )
        try:
            await interaction.response.defer()
        except discord.errors.NotFound as e:
            logger.error(
                f"Interaction for {command_name} not found during safety defer: {e}"
            )
            return
        except Exception as e:
            logger.error(f"Failed to defer interaction for {command_name}: {e}")
            return

    if error_message is None:
        error_message = f"Sorry, an error occurred while processing the {command_name} command. Please try again later."

    # Validate hours parameter for sum-hr and chart-hr commands
    if command_name in ["sum-hr", "chart-hr"]:
        import config

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
                return
            except Exception as e:
                logger.error(f"Failed to send validation error for {command_name}: {e}")
                return

        # Warn for large summaries that may take longer
        if hours > config.LARGE_SUMMARY_THRESHOLD:
            error_message = (
                config.ERROR_MESSAGES["large_summary_warning"].format(hours=hours)
                + " and could impact performance."
            )

    # Similar validation for chart-day command
    if command_name == "chart-day":
        hours = 24  # Ensure hours is set for chart-day

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
        logger.error(f"Error in {command_name} slash command: {e}", exc_info=True)
        # Only try to send followup if interaction is still valid
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
                    f"Failed to send error followup for {command_name}: {followup_error}"
                )
            except Exception as unexpected_error:
                logger.error(
                    f"Unexpected error sending followup for {command_name}: {unexpected_error}",
                    exc_info=True,
                )
        else:
            logger.warning(
                f"Interaction for {command_name} has expired, cannot send error followup"
            )


# Slash Commands
@bot.tree.command(
    name="sum-day", description="Generate a summary of messages from today"
)
async def sum_day_slash(interaction: discord.Interaction):
    """Slash command version of /sum-day"""
    # Defer IMMEDIATELY to avoid 3-second timeout
    try:
        await interaction.response.defer()
    except discord.errors.NotFound as e:
        logger.error(f"sum-day interaction not found during defer: {e}")
        return
    except Exception as e:
        logger.error(f"Failed to defer sum-day interaction: {e}")
        return
    await _handle_slash_command_wrapper(interaction, "sum-day", hours=24)


@bot.tree.command(
    name="sum-hr", description="Generate a summary of messages from the past N hours"
)
async def sum_hr_slash(interaction: discord.Interaction, hours: int):
    """Slash command version of /sum-hr"""
    # Defer IMMEDIATELY to avoid 3-second timeout
    try:
        await interaction.response.defer()
    except discord.errors.NotFound as e:
        logger.error(f"sum-hr interaction not found during defer: {e}")
        return
    except Exception as e:
        logger.error(f"Failed to defer sum-hr interaction: {e}")
        return
    await _handle_slash_command_wrapper(interaction, "sum-hr", hours=hours)


@bot.tree.command(
    name="chart-day",
    description="Generate data analysis with charts for today's messages",
)
async def chart_day_slash(interaction: discord.Interaction):
    """Slash command version of /chart-day for data visualization"""
    # Defer IMMEDIATELY to avoid 3-second timeout
    try:
        await interaction.response.defer()
    except discord.errors.NotFound as e:
        logger.error(f"chart-day interaction not found during defer: {e}")
        return
    except Exception as e:
        logger.error(f"Failed to defer chart-day interaction: {e}")
        return
    await _handle_slash_command_wrapper(
        interaction, "chart-day", hours=24, force_charts=True
    )


@bot.tree.command(
    name="chart-hr",
    description="Generate data analysis with charts for the past N hours",
)
async def chart_hr_slash(interaction: discord.Interaction, hours: int):
    """Slash command version of /chart-hr for data visualization"""
    # Defer IMMEDIATELY to avoid 3-second timeout
    try:
        await interaction.response.defer()
    except discord.errors.NotFound as e:
        logger.error(f"chart-hr interaction not found during defer: {e}")
        return
    except Exception as e:
        logger.error(f"Failed to defer chart-hr interaction: {e}")
        return
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
    logger.info(f"Bot token loaded: {token_preview}")
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
    logger.critical(f"Unexpected error during bot startup: {e}", exc_info=True)
