# This example requires the 'message_content' intent.

import discord
from discord.ext import tasks
import time
import sqlite3
import json
import asyncio
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import database
from logging_config import logger # Import the logger from the new module
from rate_limiter import check_rate_limit, update_rate_limit_config # Import rate limiting functions
from llm_handler import call_llm_api, call_llm_for_summary # Import LLM functions
from message_utils import split_long_message # Import message utility functions
from summarization_tasks import daily_channel_summarization, set_discord_client, before_daily_summarization # Import summarization tasks
from config_validator import validate_config # Import config validator
from command_handler import handle_bot_command, handle_sum_day_command, handle_sum_week_command # Import command handlers
from error_handler import handle_error, ErrorCategory, categorize_exception # Import error handler

# Using message_content intent (requires enabling in the Discord Developer Portal)
intents = discord.Intents.default()
intents.message_content = True  # This is required to read message content in guild channels

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    set_discord_client(client) # Set the client instance for summarization tasks
    logger.info(f'Bot has successfully connected as {client.user}')
    logger.info(f'Bot ID: {client.user.id}')
    logger.info(f'Connected to {len(client.guilds)} guilds')

    # Initialize the database - critical for bot operation
    try:
        database.init_database() 
        message_count = database.get_message_count()
        logger.info(f'Database initialized successfully. Current message count: {message_count}')
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
            logger.warning(f'Guild {guild.name} does not have a #bot-talk channel. The /bot command will not work in this guild, but /sum-day will still function in all channels.')

@client.event
async def on_guild_join(guild):
    """Log when the bot joins a new guild"""
    logger.info(f'Bot joined new guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members')
    # Check if bot-talk channel exists
    bot_talk_exists = any(channel.name == 'bot-talk' for channel in guild.text_channels)
    if not bot_talk_exists:
        logger.warning(f'Guild {guild.name} does not have a #bot-talk channel. The /bot command will not work in this guild, but /sum-day will still function in all channels.')

@client.event
async def on_guild_remove(guild):
    """Log when the bot is removed from a guild"""
    logger.info(f'Bot removed from guild: {guild.name} (ID: {guild.id})')

@client.event
async def on_error(event, *args, **kwargs):
    """Handle Discord API errors using the standardized error handler"""
    error = args[0] if args else None
    if isinstance(error, Exception):
        # Create context for logging
        context = {
            'event': event
        }
        
        # Add additional context if available
        if len(args) > 1:
            # For message events, add message details
            if isinstance(args[1], discord.Message):
                message = args[1]
                context.update({
                    'message_id': message.id,
                    'author': str(message.author),
                    'channel': str(message.channel),
                    'guild': str(message.guild) if message.guild else 'DM'
                })
        
        # Categorize the error
        error_category = categorize_exception(error)
        
        # Handle the error
        await handle_error(
            error=error,
            error_category=error_category,
            log_message=f"Discord error in {event}",
            notify_user=False,  # Don't notify users about internal Discord API errors
            context=context
        )
    else:
        # Fallback to basic logging if we don't have an exception object
        logger.error(f'Discord error in {event}', exc_info=True)
        if args:
            logger.error(f'Error context args: {args}')
        if kwargs:
            logger.error(f'Error context kwargs: {kwargs}')

def identify_command(message, client_user):
    """
    Identify if a message is a command and what type of command it is.
    
    Args:
        message: The Discord message object
        client_user: The bot's user object
        
    Returns:
        tuple: (is_command, command_type)
    """
    bot_mention = f'<@{client_user.id}>'
    bot_mention_alt = f'<@!{client_user.id}>'
    
    if message.content.startswith(bot_mention) or message.content.startswith(bot_mention_alt):
        return True, "mention"
    elif message.content.startswith('/sum-day'):
        return True, "/sum-day"
    elif message.content.startswith('/sum-week'):
        return True, "/sum-week"
    
    return False, None

async def process_command(message, client_user, command_type):
    """
    Process a command based on its type.
    
    Args:
        message: The Discord message object
        client_user: The bot's user object
        command_type: The type of command to process
    """
    try:
        if command_type == "mention":
            logger.debug(f"Processing mention command in channel #{message.channel.name if hasattr(message.channel, 'name') else 'DM'}")
            await handle_bot_command(message, client_user)
        elif command_type == "/sum-day":
            logger.debug(f"Processing /sum-day command in channel #{message.channel.name if hasattr(message.channel, 'name') else 'DM'}")
            await handle_sum_day_command(message, client_user)
        elif command_type == "/sum-week":
            logger.debug(f"Processing /sum-week command in channel #{message.channel.name if hasattr(message.channel, 'name') else 'DM'}")
            await handle_sum_week_command(message, client_user)
    except Exception as e:
        logger.error(f"Error processing {command_type} command: {e}", exc_info=True)
        # Notify the user about the error
        try:
            await message.channel.send("Sorry, an error occurred while processing your command. Please try again later.")
        except Exception as send_error:
            logger.error(f"Could not send error message to channel: {send_error}")

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
    logger.info(f"Message received - Guild: {guild_name} | Channel: {channel_name} | Author: {author_display} | Content: {message.content[:50]}{'...' if len(message.content) > 50 else ''}")

    # Identify if this is a command
    is_command, command_type = identify_command(message, client.user)

    # Store message in database
    try:
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
    except Exception as e:
        # Use the error handler for database errors
        context = {
            'message_id': str(message.id),
            'author': str(message.author),
            'channel': channel_name,
            'guild': guild_name
        }
        
        await handle_error(
            error=e,
            error_category=ErrorCategory.DATABASE,
            log_message="Error storing message in database",
            notify_user=False,  # Don't notify users about database errors
            context=context
        )

    # Process command if identified
    if is_command:
        await process_command(message, client.user, command_type)

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
