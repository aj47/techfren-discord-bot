# This example requires the 'message_content' intent.

import discord
from discord.ext import tasks, commands
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
from command_handler import handle_bot_command, handle_sum_day_command, handle_sum_hr_command, validate_hours_parameter # Import command handlers
from firecrawl_handler import scrape_url_content # Import Firecrawl handler
from apify_handler import scrape_twitter_content, is_twitter_url # Import Apify handler

# Using message_content intent (requires enabling in the Discord Developer Portal)
intents = discord.Intents.default()
intents.message_content = True  # This is required to read message content in guild channels

client = commands.Bot(command_prefix='!', intents=intents)

class MockMessage:
    """Mock message object for compatibility with existing command handlers"""
    def __init__(self, interaction, command="sum-day", hours=None):
        self.author = interaction.user
        self.channel = interaction.channel
        self.guild = interaction.guild
        if command == "sum-hr" and hours is not None:
            self.content = f"/sum-hr {hours}"
        else:
            self.content = "/sum-day"

    async def create_thread(self, name):
        return await self.channel.create_thread(name=name)

# Slash command definitions
@client.tree.command(name="sum-day", description="Generate a summary of the past 24 hours in this channel")
async def sum_day_slash(interaction: discord.Interaction):
    """Slash command for daily channel summary"""
    await interaction.response.defer()

    mock_message = MockMessage(interaction)

    # Use existing handler logic
    try:
        await handle_sum_day_command(mock_message, client.user)
        # If no exception, the command succeeded
        try:
            await interaction.followup.send("✅ Daily summary has been generated!", ephemeral=True)
        except discord.HTTPException as e:
            logger.warning(f"Failed to send followup message: {e}")
    except Exception as e:
        logger.error(f"Error in sum-day slash command: {e}")
        try:
            await interaction.followup.send("❌ An error occurred while generating the summary.", ephemeral=True)
        except discord.HTTPException as e:
            logger.warning(f"Failed to send error followup message: {e}")

@client.tree.command(name="sum-hr", description="Generate a summary of the past N hours in this channel")
async def sum_hr_slash(interaction: discord.Interaction, hours: int):
    """Slash command for hourly channel summary"""
    await interaction.response.defer()

    # Validate hours parameter using shared validation function
    is_valid, error_message = validate_hours_parameter(hours)
    if not is_valid:
        await interaction.followup.send(f"❌ {error_message}", ephemeral=True)
        return

    mock_message = MockMessage(interaction, command="sum-hr", hours=hours)

    # Use existing handler logic, skip validation since we already validated
    try:
        await handle_sum_hr_command(mock_message, client.user, skip_validation=True)
        # If no exception, the command succeeded
        try:
            await interaction.followup.send(f"✅ {hours}-hour summary has been generated!", ephemeral=True)
        except discord.HTTPException as e:
            logger.warning(f"Failed to send followup message: {e}")
    except Exception as e:
        logger.error(f"Error in sum-hr slash command: {e}")
        try:
            await interaction.followup.send("❌ An error occurred while generating the summary.", ephemeral=True)
        except discord.HTTPException as e:
            logger.warning(f"Failed to send error followup message: {e}")

@client.event
async def on_ready():
    set_discord_client(client) # Set the client instance for summarization tasks
    logger.info(f'Bot has successfully connected as {client.user}')
    logger.info(f'Bot ID: {client.user.id}')
    logger.info(f'Connected to {len(client.guilds)} guilds')

    # Sync slash commands
    try:
        logger.info("Starting slash command synchronization...")
        synced = await client.tree.sync()
        logger.info(f"Successfully synced {len(synced)} slash command(s):")
        for cmd in synced:
            logger.info(f"  - /{cmd.name}: {cmd.description}")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

    # Initialize the database - critical for bot operation
    try:
        database.init_database()

        # Check if database connection is working
        if not database.check_database_connection():
            logger.critical('Database connection check failed. Shutting down.')
            await client.close()
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
    for guild in client.guilds:
        logger.info(f'Connected to guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members')
        # Check if bot-talk channel exists
        bot_talk_exists = any(channel.name == 'bot-talk' for channel in guild.text_channels)
        if not bot_talk_exists:
            logger.warning(f'Guild {guild.name} does not have a #bot-talk channel. While the bot\'s mention-based query functionality (e.g., @botname <query>) currently works in all channels, a #bot-talk channel was originally intended as a dedicated space for these interactions. The /sum-day command will still function in all channels.')

@client.event
async def on_guild_join(guild):
    """Log when the bot joins a new guild"""
    logger.info(f'Bot joined new guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members')
    # Check if bot-talk channel exists
    bot_talk_exists = any(channel.name == 'bot-talk' for channel in guild.text_channels)
    if not bot_talk_exists:
        logger.warning(f'Guild {guild.name} does not have a #bot-talk channel. While the bot\'s mention-based query functionality (e.g., @botname <query>) currently works in all channels, a #bot-talk channel was originally intended as a dedicated space for these interactions. The /sum-day command will still function in all channels.')

@client.event
async def on_guild_remove(guild):
    """Log when the bot is removed from a guild"""
    logger.info(f'Bot removed from guild: {guild.name} (ID: {guild.id})')

@client.event
async def on_error(event, *args, **kwargs):
    """Log Discord API errors"""
    logger.error(f'Discord error in {event}', exc_info=True)
    # Log additional context if available
    if args:
        logger.error(f'Error context args: {args}')
    if kwargs:
        logger.error(f'Error context kwargs: {kwargs}')

@client.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == client.user:
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
    
    # Safely handle Unicode characters in message content for logging
    try:
        content_preview = message.content[:50] + ('...' if len(message.content) > 50 else '')
        logger.info(f"Message received - Guild: {guild_name} | Channel: {channel_name} | Author: {author_display} | Content: {content_preview}")
    except UnicodeEncodeError:
        # Fallback: log without the message content if there are encoding issues
        logger.info(f"Message received - Guild: {guild_name} | Channel: {channel_name} | Author: {author_display} | Content: [Unicode content]")

    # Store message in database
    try:
        # Determine if this is a command and what type
        is_command = False
        command_type = None

        bot_mention = f'<@{client.user.id}>'
        bot_mention_alt = f'<@!{client.user.id}>'
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
    bot_mention = f'<@{client.user.id}>'
    bot_mention_alt = f'<@!{client.user.id}>'
    is_mention_command = message.content.startswith(bot_mention) or message.content.startswith(bot_mention_alt)
    is_sum_day_command = message.content.startswith('/sum-day')
    is_sum_hr_command = message.content.startswith('/sum-hr')

    # Process mention commands in any channel
    if is_mention_command:
        logger.debug(f"Processing mention command in channel #{message.channel.name}")
        await handle_bot_command(message, client.user)
        return

    # If not a command we recognize, ignore
    if not (is_sum_day_command or is_sum_hr_command):
        return

    # Process commands
    try:
        if is_sum_day_command:
            await handle_sum_day_command(message, client.user)
        elif is_sum_hr_command:
            await handle_sum_hr_command(message, client.user)
    except Exception as e:
        logger.error(f"Error processing command in on_message: {e}", exc_info=True)
        # Optionally notify about the error in the channel if it's a user-facing command error
        # await message.channel.send("Sorry, an error occurred while processing your command.")

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
    client.run(config.token)
except ImportError:
    logger.critical("Config file not found or token not defined", exc_info=True)
    logger.error("Please create a config.py file with your Discord bot token.")
    logger.error("Example: token = 'YOUR_DISCORD_BOT_TOKEN'")
except discord.LoginFailure:
    logger.critical("Invalid Discord token. Please check your token in config.py", exc_info=True)
except Exception as e:
    logger.critical(f"Unexpected error during bot startup: {e}", exc_info=True)
