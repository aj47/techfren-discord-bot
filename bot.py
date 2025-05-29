# This example requires the 'message_content' intent.

import discord
from discord.ext import commands, tasks
import asyncio
import re
import os
import json
from datetime import datetime, timedelta, timezone
import database
from logging_config import logger # Import the logger from the new module
from rate_limiter import check_rate_limit, update_rate_limit_config # Import rate limiting functions
from llm_handler import call_llm_api, call_llm_for_summary, summarize_scraped_content # Import LLM functions
from message_utils import split_long_message # Import message utility functions
from summarization_tasks import daily_channel_summarization, set_discord_client, before_daily_summarization # Import summarization tasks
from config_validator import validate_config # Import config validator
from command_handler import handle_bot_command, handle_sum_day_command, handle_sum_hr_command # Import command handlers
from firecrawl_handler import scrape_url_content # Import Firecrawl handler
from apify_handler import scrape_twitter_content, is_twitter_url # Import Apify handler

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

        # Check if the URL is from Twitter/X.com
        if await is_twitter_url(url):
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
            # For non-Twitter/X.com URLs, use Firecrawl
            scraped_result = await scrape_url_content(url)
            markdown_content = scraped_result  # Firecrawl returns markdown directly

        # Check if scraping was successful
        if not scraped_result:
            logger.warning(f"Failed to scrape content from URL: {url}")
            return

        # For Twitter/X.com URLs scraped with Apify, we already have the markdown content
        if await is_twitter_url(url) and hasattr(config, 'apify_api_token') and config.apify_api_token:
            markdown_content = scraped_result.get('markdown')
        else:
            markdown_content = scraped_result  # Firecrawl returns markdown directly

        # Step 2: Summarize the scraped content
        scraped_data = await summarize_scraped_content(markdown_content, url)
        if not scraped_data:
            logger.warning(f"Failed to summarize content from URL: {url}")
            return

        # Step 3: Convert key points to JSON string
        key_points_json = json.dumps(scraped_data.get('key_points', []))

        # Step 4: Update the message in the database with the scraped data
        success = await database.update_message_with_scraped_data(
            message_id,
            url,
            scraped_data.get('summary', ''),
            key_points_json
        )

        if success:
            logger.info(f"Successfully processed URL {url} from message {message_id}")
        else:
            logger.warning(f"Failed to update message {message_id} with scraped data")

    except Exception as e:
        logger.error(f"Error processing URL {url} from message {message_id}: {str(e)}", exc_info=True)

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
            await client.close()
            return
    except Exception as e:
        logger.critical(f'Failed to initialize database: {str(e)}', exc_info=True)
        logger.critical('Database initialization is required for bot operation. Shutting down.')
        await client.close()
        return

    # Start the daily summarization task if not already running
    if not daily_channel_summarization.is_running():
        daily_channel_summarization.start()
        logger.info("Started daily channel summarization task")

    # Log details about each connected guild
    for guild in bot.guilds:
        logger.info(f'Connected to guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members')
        # Check if bot-talk channel exists
        bot_talk_exists = any(channel.name == 'bot-talk' for channel in guild.text_channels)
        if not bot_talk_exists:
            logger.warning(f'Guild {guild.name} does not have a #bot-talk channel. While the bot\'s mention-based query functionality (e.g., @botname <query>) currently works in all channels, a #bot-talk channel was originally intended as a dedicated space for these interactions. The /sum-day command will still function in all channels.')

@bot.event
async def on_guild_join(guild):
    """Log when the bot joins a new guild"""
    logger.info(f'Bot joined new guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members')
    # Check if bot-talk channel exists
    bot_talk_exists = any(channel.name == 'bot-talk' for channel in guild.text_channels)
    if not bot_talk_exists:
        logger.warning(f'Guild {guild.name} does not have a #bot-talk channel. While the bot\'s mention-based query functionality (e.g., @botname <query>) currently works in all channels, a #bot-talk channel was originally intended as a dedicated space for these interactions. The /sum-day command will still function in all channels.')

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
            command_type=command_type
        )

        if not success:
            logger.warning(f"Failed to store message {message.id} in database")

        # Check for URLs in the message content
        if not is_command and not message.author.bot and success:
            # URL regex pattern - capture the full URL including path and query parameters
            url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?'
            urls = re.findall(url_pattern, message.content)

            if urls:
                # Process the first URL found
                url = urls[0]
                logger.info(f"Found URL in message {message.id}: {url}")

                # Create a background task to process the URL
                asyncio.create_task(process_url(message.id, url))
    except Exception as e:
        logger.error(f"Error storing message in database: {str(e)}", exc_info=True)

    # Check if this is a command
    bot_mention = f'<@{bot.user.id}>'
    bot_mention_alt = f'<@!{bot.user.id}>'
    is_mention_command = message.content.startswith(bot_mention) or message.content.startswith(bot_mention_alt)
    is_sum_day_command = message.content.startswith('/sum-day')
    is_sum_hr_command = message.content.startswith('/sum-hr')

    # Process mention commands in any channel
    if is_mention_command:
        logger.debug(f"Processing mention command in channel #{message.channel.name}")
        await handle_bot_command(message, bot.user)
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

# Slash Commands
@bot.tree.command(name="sum-day", description="Generate a summary of messages from today")
async def sum_day_slash(interaction: discord.Interaction):
    """Slash command version of /sum-day"""
    await interaction.response.defer()

    try:
        # Create a mock message object for compatibility with existing handler
        class MockMessage:
            def __init__(self, interaction):
                self.author = interaction.user
                self.guild = interaction.guild
                self.channel = interaction.channel
                self.content = "/sum-day"

            async def create_thread(self, name):
                return await self.channel.create_thread(name=name, message=None)

        mock_message = MockMessage(interaction)

        # Use existing handler logic but send responses via interaction
        from command_handler import handle_sum_day_command_interaction
        await handle_sum_day_command_interaction(mock_message, bot.user, interaction)

    except Exception as e:
        logger.error(f"Error in sum-day slash command: {e}", exc_info=True)
        try:
            await interaction.followup.send("Sorry, an error occurred while generating the summary. Please try again later.", ephemeral=True)
        except:
            pass

@bot.tree.command(name="sum-hr", description="Generate a summary of messages from the past N hours")
async def sum_hr_slash(interaction: discord.Interaction, hours: int):
    """Slash command version of /sum-hr"""
    await interaction.response.defer()

    try:
        # Validate hours parameter
        if hours < 1 or hours > 168:  # Max 1 week
            await interaction.followup.send("Please provide a number between 1 and 168 hours.", ephemeral=True)
            return

        # Create a mock message object for compatibility with existing handler
        class MockMessage:
            def __init__(self, interaction, hours):
                self.author = interaction.user
                self.guild = interaction.guild
                self.channel = interaction.channel
                self.content = f"/sum-hr {hours}"

            async def create_thread(self, name):
                return await self.channel.create_thread(name=name, message=None)

        mock_message = MockMessage(interaction, hours)

        # Use existing handler logic but send responses via interaction
        from command_handler import handle_sum_hr_command_interaction
        await handle_sum_hr_command_interaction(mock_message, bot.user, interaction)

    except Exception as e:
        logger.error(f"Error in sum-hr slash command: {e}", exc_info=True)
        try:
            await interaction.followup.send("Sorry, an error occurred while generating the summary. Please try again later.", ephemeral=True)
        except:
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
