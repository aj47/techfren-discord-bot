# This example requires the 'message_content' intent.

import discord
import logging
import os
import time
import sqlite3
from datetime import datetime
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
user_last_request = {}  # Track last request time per user
user_request_count = defaultdict(list)  # Track request timestamps for per-minute limiting

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

        # Make the API request
        completion = openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://techfren.net",  # Optional site URL
                "X-Title": "TechFren Discord Bot",  # Optional site title
            },
            model="x-ai/grok-3-mini-beta",  # You can change this to any model supported by OpenRouter
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
        messages (list): List of message dictionaries to summarize
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

        # Make the API request with a higher token limit for summaries
        completion = openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://techfren.net",
                "X-Title": "TechFren Discord Bot",
            },
            model="x-ai/grok-3-mini-beta",  # You can change this to any model supported by OpenRouter
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
    current_time = time.time()

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
    user_request_count[user_id].append(current_time)

    # Clean up old timestamps
    user_request_count[user_id] = recent_requests + [current_time]

    return False, 0, None

@client.event
async def on_ready():
    logger.info(f'Bot has successfully connected as {client.user}')
    logger.info(f'Bot ID: {client.user.id}')
    logger.info(f'Connected to {len(client.guilds)} guilds')

    # Initialize the database
    try:
        database.init_database()
        message_count = database.get_message_count()
        logger.info(f'Database initialized successfully. Current message count: {message_count}')
    except Exception as e:
        logger.error(f'Failed to initialize database: {str(e)}', exc_info=True)

    # Log details about each connected guild
    for guild in client.guilds:
        logger.info(f'Connected to guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members')
        # Check if bot-talk channel exists
        bot_talk_exists = any(channel.name == 'bot-talk' for channel in guild.text_channels)
        if not bot_talk_exists:
            logger.warning(f'Guild {guild.name} does not have a #bot-talk channel. Bot will not respond to any messages in this guild.')

@client.event
async def on_guild_join(guild):
    """Log when the bot joins a new guild"""
    logger.info(f'Bot joined new guild: {guild.name} (ID: {guild.id}) - {len(guild.members)} members')
    # Check if bot-talk channel exists
    bot_talk_exists = any(channel.name == 'bot-talk' for channel in guild.text_channels)
    if not bot_talk_exists:
        logger.warning(f'Guild {guild.name} does not have a #bot-talk channel. Bot will not respond to any messages in this guild.')

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

    # Log message details
    guild_name = message.guild.name if message.guild else "DM"
    channel_name = message.channel.name if hasattr(message.channel, 'name') else "Direct Message"
    logger.info(f"Message received - Guild: {guild_name} | Channel: {channel_name} | Author: {message.author} | Content: {message.content[:50]}{'...' if len(message.content) > 50 else ''}")

    # Store message in database
    try:
        # Determine if this is a command and what type
        is_command = False
        command_type = None

        if message.content.startswith('$hello'):
            is_command = True
            command_type = "$hello"
        elif message.content.startswith('/bot '):
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

    # Only respond in the #bot-talk channel
    if hasattr(message.channel, 'name') and message.channel.name != 'bot-talk':
        logger.debug(f"Ignoring message in channel #{message.channel.name} - bot only responds in #bot-talk")
        return

    # Process commands
    try:
        # Handle $hello command
        if message.content.startswith('$hello'):
            logger.info(f"Executing command: $hello - Requested by {message.author}")

            # Send the message to the channel
            bot_response = await message.channel.send('Hello!')

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
                    content='Hello!',
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

            logger.info(f"Command executed successfully: $hello")

        # Handle /bot command for LLM queries
        elif message.content.startswith('/bot '):
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

try:
    logger.info("Starting bot...")
    import config

    # Check if token exists and is valid
    if not hasattr(config, 'token') or not config.token:
        logger.error("Token not found in config.py or is empty")
        raise ValueError("Bot token is missing or empty")

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