# This example requires the 'message_content' intent.

import discord
from discord.ext import tasks
import logging
import os
import time
import sqlite3
import json
import asyncio
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from openai import OpenAI
import database

# Set up logging
log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Create a unique log file name with timestamp
log_filename = f"{log_directory}/bot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('discord_bot')

# Using message_content intent (requires enabling in the Discord Developer Portal)
intents = discord.Intents.default()
intents.message_content = True  # This is required to read message content in guild channels

client = discord.Client(intents=intents)

# Rate limiting configuration
RATE_LIMIT_SECONDS = 10  # Time between allowed requests per user
MAX_REQUESTS_PER_MINUTE = 6  # Maximum requests per user per minute
CLEANUP_INTERVAL = 3600  # Clean up old rate limit data every hour (in seconds)

# Thread safety for rate limiting
import threading
rate_limit_lock = threading.Lock()  # Lock for thread safety

# Rate limiting data structures
user_last_request = {}  # Track last request time per user
user_request_count = defaultdict(list)  # Track request timestamps for per-minute limiting
last_cleanup_time = time.time()  # Track when we last cleaned up old rate limit data

async def split_long_message(message, max_length=1900):
    """
    Split a long message into multiple parts to avoid Discord's 2000 character limit

    Args:
        message (str): The message to split
        max_length (int): Maximum length of each part (default: 1900 to leave room for part indicators)

    Returns:
        list: List of message parts
    """
    if len(message) <= max_length:
        return [message]

    parts = []
    current_part = ""

    # Split by paragraphs first (double newlines)
    paragraphs = message.split("\n\n")

    for paragraph in paragraphs:
        # If adding this paragraph would exceed max_length, start a new part
        if len(current_part) + len(paragraph) + 2 > max_length:
            if current_part:
                parts.append(current_part)
                current_part = paragraph
            else:
                # If a single paragraph is too long, split it by sentences
                sentences = paragraph.split(". ")
                for sentence in sentences:
                    if len(current_part) + len(sentence) + 2 > max_length:
                        if current_part:
                            parts.append(current_part)
                            current_part = sentence + "."
                        else:
                            # If a single sentence is too long, split it by words
                            words = sentence.split(" ")
                            for word in words:
                                if len(current_part) + len(word) + 1 > max_length:
                                    parts.append(current_part)
                                    current_part = word + " "
                                else:
                                    current_part += word + " "
                    else:
                        if current_part:
                            current_part += " " + sentence + "."
                        else:
                            current_part = sentence + "."
        else:
            if current_part:
                current_part += "\n\n" + paragraph
            else:
                current_part = paragraph

    # Add the last part if it's not empty
    if current_part:
        parts.append(current_part)

    # Add part indicators
    for i in range(len(parts)):
        parts[i] = f"[Part {i+1}/{len(parts)}]\n{parts[i]}"

    return parts

async def call_llm_api(query):
    """
    Call the LLM API with the user's query and return the response

    Args:
        query (str): The user's query text

    Returns:
        str: The LLM's response or an error message
    """
    try:
        logger.info(f"Calling LLM API with query: {query[:50]}{'...' if len(query) > 50 else ''}")

        # Import config here to ensure it's loaded
        import config

        # Check if OpenRouter API key exists
        if not hasattr(config, 'openrouter') or not config.openrouter:
            logger.error("OpenRouter API key not found in config.py or is empty")
            return "Error: OpenRouter API key is missing. Please contact the bot administrator."

        # Initialize the OpenAI client with OpenRouter base URL
        openai_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.openrouter
        )

        # Get the model from config or use default
        model = getattr(config, 'llm_model', "x-ai/grok-3-mini-beta")

        # Make the API request
        completion = openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://techfren.net",  # Optional site URL
                "X-Title": "TechFren Discord Bot",  # Optional site title
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": "You are an assistant bot to the techfren community discord server. A community of AI coding, Open source and technology enthusiasts"
                },
                {
                    "role": "user",
                    "content": query
                }
            ],
            max_tokens=1000,
            temperature=0.7
        )

        # Extract the response
        message = completion.choices[0].message.content
        logger.info(f"LLM API response received successfully: {message[:50]}{'...' if len(message) > 50 else ''}")
        return message

    except Exception as e:
        logger.error(f"Error calling LLM API: {str(e)}", exc_info=True)
        return "Sorry, I encountered an error while processing your request. Please try again later."

async def call_llm_for_summary(messages, channel_name, date):
    """
    Call the LLM API to summarize a list of messages from a channel

    Args:
        messages (list): List of message dictionaries to e
        channel_name (str): Name of the channel
        date (datetime): Date of the messages

    Returns:
        str: The LLM's summary or an error message
    """
    try:
        # Filter out command messages but include bot responses
        filtered_messages = [
            msg for msg in messages
            if not msg['is_command']
        ]

        if not filtered_messages:
            return f"No messages found in #{channel_name} for {date.strftime('%Y-%m-%d')}."

        # Prepare the messages for summarization
        formatted_messages = []
        for msg in filtered_messages:
            time_str = msg['created_at'].strftime('%H:%M:%S')
            formatted_messages.append(f"[{time_str}] {msg['author_name']}: {msg['content']}")

        # Join the messages with newlines
        messages_text = "\n".join(formatted_messages)

        # Create the prompt for the LLM
        prompt = f"""Please summarize the following conversation from the #{channel_name} channel on {date.strftime('%Y-%m-%d')}:

{messages_text}

Provide a concise summary of the main topics discussed, key points made, and any conclusions reached.
Format the summary in a clear, readable way with bullet points for main topics.
"""

        logger.info(f"Calling LLM API for channel summary: #{channel_name} on {date.strftime('%Y-%m-%d')}")

        # Import config here to ensure it's loaded
        import config

        # Check if OpenRouter API key exists
        if not hasattr(config, 'openrouter') or not config.openrouter:
            logger.error("OpenRouter API key not found in config.py or is empty")
            return "Error: OpenRouter API key is missing. Please contact the bot administrator."

        # Initialize the OpenAI client with OpenRouter base URL
        openai_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.openrouter
        )

        # Get the model from config or use default
        model = getattr(config, 'llm_model', "x-ai/grok-3-mini-beta")

        # Make the API request with a higher token limit for summaries
        completion = openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://techfren.net",
                "X-Title": "TechFren Discord Bot",
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that summarizes Discord conversations. Provide clear, concise summaries that capture the main points of discussions."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=1500,  # Increased token limit for summaries
            temperature=0.5   # Lower temperature for more focused summaries
        )

        # Extract the response
        summary = completion.choices[0].message.content
        logger.info(f"LLM API summary received successfully: {summary[:50]}{'...' if len(summary) > 50 else ''}")

        # Add a header to the summary
        final_summary = f"**Summary of #{channel_name} on {date.strftime('%Y-%m-%d')}**\n\n{summary}"
        return final_summary

    except Exception as e:
        logger.error(f"Error calling LLM API for summary: {str(e)}", exc_info=True)
        return "Sorry, I encountered an error while generating the summary. Please try again later."

def check_rate_limit(user_id):
    """
    Check if a user has exceeded the rate limit

    Args:
        user_id (str): The Discord user ID

    Returns:
        tuple: (is_rate_limited, seconds_to_wait, reason)
    """
    global last_cleanup_time
    current_time = time.time()

    # Use lock for thread safety
    with rate_limit_lock:
        # Periodically clean up old rate limit data to prevent memory leaks
        if current_time - last_cleanup_time > CLEANUP_INTERVAL:
            cleanup_rate_limit_data(current_time)
            last_cleanup_time = current_time

        # Check cooldown between requests
        if user_id in user_last_request:
            time_since_last = current_time - user_last_request[user_id]
            if time_since_last < RATE_LIMIT_SECONDS:
                return True, RATE_LIMIT_SECONDS - time_since_last, "cooldown"

        # Check requests per minute
        minute_ago = current_time - 60
        recent_requests = [t for t in user_request_count[user_id] if t > minute_ago]

        if len(recent_requests) >= MAX_REQUESTS_PER_MINUTE:
            oldest = min(recent_requests)
            time_until_reset = oldest + 60 - current_time
            return True, time_until_reset, "max_per_minute"

        # Update tracking
        user_last_request[user_id] = current_time

        # Clean up old timestamps and add the new one (avoid duplicates)
        user_request_count[user_id] = recent_requests + [current_time]

    return False, 0, None

def cleanup_rate_limit_data(current_time):
    """
    Clean up old rate limit data to prevent memory leaks

    Args:
        current_time (float): The current time
    """
    # This function is called from within check_rate_limit which already holds the lock
    # No need to acquire the lock again

    # Remove users who haven't made a request in the last hour
    inactive_threshold = current_time - 3600

    # Clean up user_last_request
    inactive_users = [user_id for user_id, last_time in user_last_request.items()
                     if last_time < inactive_threshold]
    for user_id in inactive_users:
        del user_last_request[user_id]
        if user_id in user_request_count:
            del user_request_count[user_id]

    if inactive_users:
        logger.debug(f"Cleaned up rate limit data for {len(inactive_users)} inactive users")

# Daily automated summarization task
@tasks.loop(hours=24)
async def daily_channel_summarization():
    """
    Task that runs once per day to:
    1. Retrieve messages from the past 24 hours
    2. Generate summaries for each active channel
    3. Store the summaries in the database
    4. Delete old messages
    """
    try:
        logger.info("Starting daily automated channel summarization")

        # Get the current time and 24 hours ago
        now = datetime.now()
        yesterday = now - timedelta(hours=24)

        # Get active channels from the past 24 hours
        active_channels = database.get_active_channels(hours=24)

        if not active_channels:
            logger.info("No active channels found in the past 24 hours. Skipping summarization.")
            return

        logger.info(f"Found {len(active_channels)} active channels to summarize")

        # Get messages for each channel
        messages_by_channel = database.get_messages_for_time_range(yesterday, now)

        # Track successful summaries for reporting
        successful_summaries = 0
        total_messages_processed = 0

        # Process each active channel
        for channel_data in active_channels:
            channel_id = channel_data['channel_id']
            channel_name = channel_data['channel_name']

            # Skip if no messages found for this channel
            if channel_id not in messages_by_channel:
                logger.warning(f"No messages found for channel {channel_name} ({channel_id}) despite being marked as active")
                continue

            channel_messages = messages_by_channel[channel_id]['messages']

            # Skip if no messages (shouldn't happen but just in case)
            if not channel_messages:
                continue

            # Get guild information
            guild_id = channel_data['guild_id']
            guild_name = channel_data['guild_name']

            # Format messages for summarization
            formatted_messages = []
            for msg in channel_messages:
                if not msg.get('is_command', False):  # Skip command messages
                    formatted_messages.append({
                        'author_name': msg['author_name'],
                        'content': msg['content'],
                        'created_at': msg['created_at'],
                        'is_bot': msg.get('is_bot', False),
                        'is_command': False
                    })

            # Skip if no non-command messages
            if not formatted_messages:
                logger.info(f"No non-command messages found for channel {channel_name}. Skipping summarization.")
                continue

            # Get unique active users
            active_users = list(set(msg['author_name'] for msg in formatted_messages))

            # Generate summary using the existing function
            try:
                summary_text = await call_llm_for_summary(formatted_messages, channel_name, yesterday)

                # Store the summary in the database
                metadata = {
                    'start_time': yesterday.isoformat(),
                    'end_time': now.isoformat(),
                    'summary_type': 'automated_daily'
                }

                success = database.store_channel_summary(
                    channel_id=channel_id,
                    channel_name=channel_name,
                    date=yesterday,
                    summary_text=summary_text,
                    message_count=len(formatted_messages),
                    active_users=active_users,
                    guild_id=guild_id,
                    guild_name=guild_name,
                    metadata=metadata
                )

                if success:
                    successful_summaries += 1
                    total_messages_processed += len(formatted_messages)
                    logger.info(f"Successfully generated and stored summary for channel {channel_name}")

                    # Optionally post to a reports channel if configured
                    await post_summary_to_reports_channel(channel_id, channel_name, yesterday, summary_text)

            except Exception as e:
                logger.error(f"Error generating summary for channel {channel_name}: {str(e)}", exc_info=True)

        # Delete old messages (older than 24 hours) after successful summarization
        if successful_summaries > 0:
            try:
                # Calculate cutoff time (24 hours ago)
                cutoff_time = now - timedelta(hours=24)
                deleted_count = database.delete_messages_older_than(cutoff_time)
                logger.info(f"Deleted {deleted_count} messages older than {cutoff_time}")
            except Exception as e:
                logger.error(f"Error deleting old messages: {str(e)}", exc_info=True)

        logger.info(f"Daily summarization complete. Generated {successful_summaries} summaries covering {total_messages_processed} messages.")

    except Exception as e:
        logger.error(f"Error in daily channel summarization task: {str(e)}", exc_info=True)

async def post_summary_to_reports_channel(_, channel_name, __, summary_text):
    """
    Post a summary to a designated reports channel if configured

    Args:
        _ (str): ID of the summarized channel (unused)
        channel_name (str): Name of the summarized channel
        __ (datetime): Date of the summary (unused)
        summary_text (str): The summary text
    """
    try:
        # Import config to check if reports channel is configured
        import config

        # Check if reports channel is configured
        if not hasattr(config, 'reports_channel_id') or not config.reports_channel_id:
            # No reports channel configured, skip posting
            return

        # Get the reports channel
        reports_channel = client.get_channel(int(config.reports_channel_id))
        if not reports_channel:
            logger.warning(f"Reports channel with ID {config.reports_channel_id} not found")
            return

        # Split the summary if it's too long
        summary_parts = await split_long_message(summary_text)

        # Send each part of the summary
        for part in summary_parts:
            await reports_channel.send(part)

        logger.info(f"Posted summary for channel {channel_name} to reports channel")

    except Exception as e:
        logger.error(f"Error posting summary to reports channel: {str(e)}", exc_info=True)
        # Don't raise the exception - this is an optional feature

# Configure when the daily task should run (default: midnight UTC)
@daily_channel_summarization.before_loop
async def before_daily_summarization():
    """Wait until a specific time to start the daily summarization task"""
    try:
        # Import config to check for custom summarization time
        import config

        # Get the hour and minute for summarization from config or use default (0:00 UTC)
        summary_hour = getattr(config, 'summary_hour', 0)
        summary_minute = getattr(config, 'summary_minute', 0)

        # Log the scheduled time
        logger.info(f"Daily summarization scheduled for {summary_hour:02d}:{summary_minute:02d} UTC")

        # Wait until the bot is ready
        await client.wait_until_ready()

        # Calculate the time to wait
        now = datetime.now(timezone.utc)
        future = datetime(now.year, now.month, now.day, summary_hour, summary_minute, tzinfo=timezone.utc)

        # If the time has already passed today, schedule for tomorrow
        if now.hour > summary_hour or (now.hour == summary_hour and now.minute >= summary_minute):
            future += timedelta(days=1)

        # Wait until the scheduled time
        seconds_to_wait = (future - now).total_seconds()
        logger.info(f"Waiting {seconds_to_wait:.1f} seconds until first daily summarization")
        await asyncio.sleep(seconds_to_wait)

    except Exception as e:
        logger.error(f"Error in before_daily_summarization: {str(e)}", exc_info=True)
        # Default to waiting 60 seconds before starting
        await asyncio.sleep(60)

@client.event
async def on_ready():
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

    logger.info(f"Message received - Guild: {guild_name} | Channel: {channel_name} | Author: {message.author} | Content: {message.content[:50]}{'...' if len(message.content) > 50 else ''}")

    # Store message in database
    try:
        # Determine if this is a command and what type
        is_command = False
        command_type = None

        if message.content.startswith('/bot '):
            is_command = True
            command_type = "/bot"
        elif message.content.startswith('/sum-day'):
            is_command = True
            command_type = "/sum-day"

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
        logger.error(f"Error storing message in database: {str(e)}", exc_info=True)

    # Check if this is a command
    is_bot_command = message.content.startswith('/bot ')
    is_sum_day_command = message.content.startswith('/sum-day')

    # Only process /bot command in the #bot-talk channel
    if is_bot_command and hasattr(message.channel, 'name') and message.channel.name != 'bot-talk':
        logger.debug(f"Ignoring /bot command in channel #{message.channel.name} - /bot only works in #bot-talk")
        return

    # If not a command we recognize, ignore
    if not is_bot_command and not is_sum_day_command:
        return

    # Process commands
    try:
        # Handle /bot command for LLM queries
        if message.content.startswith('/bot '):
            # Extract the query (everything after "/bot ")
            query = message.content[5:].strip()

            if not query:
                error_msg = "Please provide a query after `/bot`."
                bot_response = await message.channel.send(error_msg)

                # Store the error message in the database
                try:
                    # Get guild and channel information
                    guild_id = str(message.guild.id) if message.guild else None
                    guild_name = message.guild.name if message.guild else None
                    channel_id = str(message.channel.id)
                    channel_name = message.channel.name if hasattr(message.channel, 'name') else "Direct Message"

                    # Store the bot's response in the database
                    success = database.store_message(
                        message_id=str(bot_response.id),
                        author_id=str(client.user.id),
                        author_name=str(client.user),
                        channel_id=channel_id,
                        channel_name=channel_name,
                        content=error_msg,
                        created_at=bot_response.created_at,
                        guild_id=guild_id,
                        guild_name=guild_name,
                        is_bot=True,
                        is_command=False,
                        command_type=None
                    )

                    if not success:
                        logger.warning(f"Failed to store bot error response {bot_response.id} in database")
                except Exception as e:
                    logger.error(f"Error storing bot error response in database: {str(e)}", exc_info=True)
                return

            logger.info(f"Executing command: /bot - Requested by {message.author}")

            # Check rate limiting
            is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
            if is_limited:
                if reason == "cooldown":
                    error_msg = f"Please wait {wait_time:.1f} seconds before making another request."
                    bot_response = await message.channel.send(error_msg)
                else:  # max_per_minute
                    error_msg = f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
                    bot_response = await message.channel.send(error_msg)

                # Store the error message in the database
                try:
                    # Get guild and channel information
                    guild_id = str(message.guild.id) if message.guild else None
                    guild_name = message.guild.name if message.guild else None
                    channel_id = str(message.channel.id)
                    channel_name = message.channel.name if hasattr(message.channel, 'name') else "Direct Message"

                    # Store the bot's response in the database
                    success = database.store_message(
                        message_id=str(bot_response.id),
                        author_id=str(client.user.id),
                        author_name=str(client.user),
                        channel_id=channel_id,
                        channel_name=channel_name,
                        content=error_msg,
                        created_at=bot_response.created_at,
                        guild_id=guild_id,
                        guild_name=guild_name,
                        is_bot=True,
                        is_command=False,
                        command_type=None
                    )

                    if not success:
                        logger.warning(f"Failed to store bot error response {bot_response.id} in database")
                except Exception as e:
                    logger.error(f"Error storing bot error response in database: {str(e)}", exc_info=True)

                logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
                return

            # Let the user know we're processing their request
            processing_msg = await message.channel.send("Processing your request, please wait...")

            try:
                # Call the LLM API
                response = await call_llm_api(query)

                # Split the response if it's too long
                message_parts = await split_long_message(response)

                # Send each part of the response and store in database
                for part in message_parts:
                    # Send the message to the channel
                    bot_response = await message.channel.send(part)

                    # Store the bot's response in the database
                    try:
                        # Get guild and channel information
                        guild_id = str(message.guild.id) if message.guild else None
                        guild_name = message.guild.name if message.guild else None
                        channel_id = str(message.channel.id)
                        channel_name = message.channel.name if hasattr(message.channel, 'name') else "Direct Message"

                        # Store the bot's response in the database
                        success = database.store_message(
                            message_id=str(bot_response.id),
                            author_id=str(client.user.id),
                            author_name=str(client.user),
                            channel_id=channel_id,
                            channel_name=channel_name,
                            content=part,
                            created_at=bot_response.created_at,
                            guild_id=guild_id,
                            guild_name=guild_name,
                            is_bot=True,
                            is_command=False,
                            command_type=None
                        )

                        if not success:
                            logger.warning(f"Failed to store bot response {bot_response.id} in database")
                    except Exception as e:
                        logger.error(f"Error storing bot response in database: {str(e)}", exc_info=True)

                # Delete the processing message
                await processing_msg.delete()

                logger.info(f"Command executed successfully: /bot - Response length: {len(response)} - Split into {len(message_parts)} parts")
            except Exception as e:
                logger.error(f"Error processing /bot command: {str(e)}", exc_info=True)
                error_msg = "Sorry, an error occurred while processing your request. Please try again later."
                bot_response = await message.channel.send(error_msg)

                # Store the error message in the database
                try:
                    # Get guild and channel information
                    guild_id = str(message.guild.id) if message.guild else None
                    guild_name = message.guild.name if message.guild else None
                    channel_id = str(message.channel.id)
                    channel_name = message.channel.name if hasattr(message.channel, 'name') else "Direct Message"

                    # Store the bot's response in the database
                    success = database.store_message(
                        message_id=str(bot_response.id),
                        author_id=str(client.user.id),
                        author_name=str(client.user),
                        channel_id=channel_id,
                        channel_name=channel_name,
                        content=error_msg,
                        created_at=bot_response.created_at,
                        guild_id=guild_id,
                        guild_name=guild_name,
                        is_bot=True,
                        is_command=False,
                        command_type=None
                    )

                    if not success:
                        logger.warning(f"Failed to store bot error response {bot_response.id} in database")
                except Exception as e:
                    logger.error(f"Error storing bot error response in database: {str(e)}", exc_info=True)
                try:
                    await processing_msg.delete()
                except:
                    pass

        # Handle /sum-day command for channel summarization
        elif message.content.startswith('/sum-day'):
            logger.info(f"Executing command: /sum-day - Requested by {message.author}")

            # Check rate limiting
            is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
            if is_limited:
                if reason == "cooldown":
                    error_msg = f"Please wait {wait_time:.1f} seconds before making another request."
                    bot_response = await message.channel.send(error_msg)
                else:  # max_per_minute
                    error_msg = f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
                    bot_response = await message.channel.send(error_msg)

                # Store the error message in the database
                try:
                    # Get guild and channel information
                    guild_id = str(message.guild.id) if message.guild else None
                    guild_name = message.guild.name if message.guild else None
                    channel_id = str(message.channel.id)
                    channel_name = message.channel.name if hasattr(message.channel, 'name') else "Direct Message"

                    # Store the bot's response in the database
                    success = database.store_message(
                        message_id=str(bot_response.id),
                        author_id=str(client.user.id),
                        author_name=str(client.user),
                        channel_id=channel_id,
                        channel_name=channel_name,
                        content=error_msg,
                        created_at=bot_response.created_at,
                        guild_id=guild_id,
                        guild_name=guild_name,
                        is_bot=True,
                        is_command=False,
                        command_type=None
                    )

                    if not success:
                        logger.warning(f"Failed to store bot error response {bot_response.id} in database")
                except Exception as e:
                    logger.error(f"Error storing bot error response in database: {str(e)}", exc_info=True)

                logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
                return

            # Let the user know we're processing their request
            processing_msg = await message.channel.send("Generating channel summary, please wait... This may take a moment.")

            try:
                # Get today's date
                today = datetime.now()

                # Get the channel ID and name
                channel_id = str(message.channel.id)
                channel_name = message.channel.name

                # Ensure database module is accessible
                if not database:
                    logger.error("Database module not properly imported or initialized")
                    await processing_msg.delete()
                    error_msg = "Sorry, an error occurred while accessing the database. Please try again later."
                    bot_response = await message.channel.send(error_msg)

                    # Store the error message in the database
                    try:
                        # Get guild and channel information
                        guild_id = str(message.guild.id) if message.guild else None
                        guild_name = message.guild.name if message.guild else None
                        channel_id = str(message.channel.id)
                        channel_name = message.channel.name if hasattr(message.channel, 'name') else "Direct Message"

                        # Store the bot's response in the database
                        success = database.store_message(
                            message_id=str(bot_response.id),
                            author_id=str(client.user.id),
                            author_name=str(client.user),
                            channel_id=channel_id,
                            channel_name=channel_name,
                            content=error_msg,
                            created_at=bot_response.created_at,
                            guild_id=guild_id,
                            guild_name=guild_name,
                            is_bot=True,
                            is_command=False,
                            command_type=None
                        )

                        if not success:
                            logger.warning(f"Failed to store bot error response {bot_response.id} in database")
                    except Exception as e:
                        logger.error(f"Error storing bot error response in database: {str(e)}", exc_info=True)
                    return

                # Get messages for the channel for today
                messages = database.get_channel_messages_for_day(channel_id, today)

                if not messages:
                    await processing_msg.delete()
                    error_msg = f"No messages found in this channel for today ({today.strftime('%Y-%m-%d')})."
                    bot_response = await message.channel.send(error_msg)

                    # Store the error message in the database
                    try:
                        # Get guild and channel information
                        guild_id = str(message.guild.id) if message.guild else None
                        guild_name = message.guild.name if message.guild else None
                        channel_id = str(message.channel.id)
                        channel_name = message.channel.name if hasattr(message.channel, 'name') else "Direct Message"

                        # Store the bot's response in the database
                        success = database.store_message(
                            message_id=str(bot_response.id),
                            author_id=str(client.user.id),
                            author_name=str(client.user),
                            channel_id=channel_id,
                            channel_name=channel_name,
                            content=error_msg,
                            created_at=bot_response.created_at,
                            guild_id=guild_id,
                            guild_name=guild_name,
                            is_bot=True,
                            is_command=False,
                            command_type=None
                        )

                        if not success:
                            logger.warning(f"Failed to store bot error response {bot_response.id} in database")
                    except Exception as e:
                        logger.error(f"Error storing bot error response in database: {str(e)}", exc_info=True)
                    logger.info(f"No messages found for /sum-day command in channel {channel_name}")
                    return

                # Call the LLM API for summarization
                summary = await call_llm_for_summary(messages, channel_name, today)

                # Split the summary if it's too long
                summary_parts = await split_long_message(summary)

                # Send each part of the summary and store in database
                for part in summary_parts:
                    # Send the message to the channel
                    bot_response = await message.channel.send(part)

                    # Store the bot's response in the database
                    try:
                        # Get guild and channel information
                        guild_id = str(message.guild.id) if message.guild else None
                        guild_name = message.guild.name if message.guild else None
                        channel_id = str(message.channel.id)
                        channel_name = message.channel.name if hasattr(message.channel, 'name') else "Direct Message"

                        # Store the bot's response in the database
                        success = database.store_message(
                            message_id=str(bot_response.id),
                            author_id=str(client.user.id),
                            author_name=str(client.user),
                            channel_id=channel_id,
                            channel_name=channel_name,
                            content=part,
                            created_at=bot_response.created_at,
                            guild_id=guild_id,
                            guild_name=guild_name,
                            is_bot=True,
                            is_command=False,
                            command_type=None
                        )

                        if not success:
                            logger.warning(f"Failed to store bot response {bot_response.id} in database")
                    except Exception as e:
                        logger.error(f"Error storing bot response in database: {str(e)}", exc_info=True)

                # Delete the processing message
                await processing_msg.delete()

                logger.info(f"Command executed successfully: /sum-day - Summary length: {len(summary)} - Split into {len(summary_parts)} parts")
            except Exception as e:
                logger.error(f"Error processing /sum-day command: {str(e)}", exc_info=True)
                error_msg = "Sorry, an error occurred while generating the summary. Please try again later."
                bot_response = await message.channel.send(error_msg)

                # Store the error message in the database
                try:
                    # Get guild and channel information
                    guild_id = str(message.guild.id) if message.guild else None
                    guild_name = message.guild.name if message.guild else None
                    channel_id = str(message.channel.id)
                    channel_name = message.channel.name if hasattr(message.channel, 'name') else "Direct Message"

                    # Store the bot's response in the database
                    success = database.store_message(
                        message_id=str(bot_response.id),
                        author_id=str(client.user.id),
                        author_name=str(client.user),
                        channel_id=channel_id,
                        channel_name=channel_name,
                        content=error_msg,
                        created_at=bot_response.created_at,
                        guild_id=guild_id,
                        guild_name=guild_name,
                        is_bot=True,
                        is_command=False,
                        command_type=None
                    )

                    if not success:
                        logger.warning(f"Failed to store bot error response {bot_response.id} in database")
                except Exception as e:
                    logger.error(f"Error storing bot error response in database: {str(e)}", exc_info=True)
                try:
                    await processing_msg.delete()
                except:
                    pass
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        # Optionally notify about the error in the channel
        # await message.channel.send("Sorry, an error occurred while processing your command.")

def validate_config(config):
    """
    Validate the configuration file

    Args:
        config: The config module

    Returns:
        bool: True if the configuration is valid

    Raises:
        ValueError: If the configuration is invalid
    """
    global RATE_LIMIT_SECONDS, MAX_REQUESTS_PER_MINUTE

    # Check Discord token
    if not hasattr(config, 'token') or not config.token:
        logger.error("Discord token not found in config.py or is empty")
        raise ValueError("Bot token is missing or empty")

    if not isinstance(config.token, str) or len(config.token) < 50:
        logger.warning("Discord token appears to be invalid (too short)")

    # Check OpenRouter API key
    if not hasattr(config, 'openrouter') or not config.openrouter:
        logger.error("OpenRouter API key not found in config.py or is empty")
        raise ValueError("OpenRouter API key is missing or empty")

    if not isinstance(config.openrouter, str) or len(config.openrouter) < 20:
        logger.warning("OpenRouter API key appears to be invalid (too short)")

    # Check optional rate limiting configuration
    if hasattr(config, 'rate_limit_seconds'):
        try:
            RATE_LIMIT_SECONDS = int(config.rate_limit_seconds)
            logger.info(f"Using custom rate limit seconds: {RATE_LIMIT_SECONDS}")
        except (ValueError, TypeError):
            logger.warning("Invalid rate_limit_seconds in config, using default")

    if hasattr(config, 'max_requests_per_minute'):
        try:
            MAX_REQUESTS_PER_MINUTE = int(config.max_requests_per_minute)
            logger.info(f"Using custom max requests per minute: {MAX_REQUESTS_PER_MINUTE}")
        except (ValueError, TypeError):
            logger.warning("Invalid max_requests_per_minute in config, using default")

    return True

try:
    logger.info("Starting bot...")
    import config

    # Validate configuration
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