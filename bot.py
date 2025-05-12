# This example requires the 'message_content' intent.

import discord
from discord.ext import tasks
import logging
import os
import time
import json
import asyncio
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from openai import OpenAI
import database
from firecrawl import FirecrawlApp  # Added Firecrawl import

# Add API key rotator logic
class APIKeyRotator:
    def __init__(self, keys_file):
        with open(keys_file, 'r') as f:
            self.all_keys = json.load(f)
        self.indices = {key_type: 0 for key_type in self.all_keys}

    def get_key(self, key_type: str):
        if key_type not in self.all_keys or not self.all_keys[key_type]:
            logger.error(f"No API keys found for type: {key_type}")
            return None
        keys = self.all_keys[key_type]
        key = keys[self.indices[key_type]]
        return key

    def rotate_key(self, key_type: str):
        if key_type not in self.all_keys or not self.all_keys[key_type]:
            logger.error(f"Cannot rotate keys for type: {key_type}, no keys available.")
            return
        keys = self.all_keys[key_type]
        self.indices[key_type] = (self.indices[key_type] + 1) % len(keys)
        logger.info(f"Rotated API key for {key_type}. New index: {self.indices[key_type]}")

# Initialize API key rotator
api_key_rotator = APIKeyRotator('keys.json')

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
        current_openai_key = api_key_rotator.get_key('openrouter_api_keys')
        if not current_openai_key:
            logger.error("OpenRouter API key not available.")
            return "Error: OpenRouter API key is missing. Please contact the bot administrator."

        # Initialize the OpenAI client with OpenRouter base URL
        openai_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=current_openai_key
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
        if "rate limit" in str(e).lower() or "insufficient_quota" in str(e).lower():
            logger.info("OpenAI rate limit detected. Rotating key.")
            await handle_openai_rate_limit()
        return "Sorry, I encountered an error while processing your request. Please try again later."

# Handle rate limit response
async def handle_openai_rate_limit():
    api_key_rotator.rotate_key('openrouter_api_keys')

def extract_urls(text: str) -> list[str]:
    """Extracts URLs from a given text string."""
    import re
    # Basic URL regex, can be improved for more complex cases
    url_pattern = re.compile(r'https?://[\S]+')
    urls = url_pattern.findall(text)
    return urls

@client.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # --- Begin Firecrawl Integration ---
    urls = extract_urls(message.content)
    if urls:
        firecrawl_api_key = api_key_rotator.get_key('firecrawl_api_keys')
        if not firecrawl_api_key:
            logger.error("Firecrawl API key not available.")
        else:
            app = FirecrawlApp(api_key=firecrawl_api_key)
            for url in urls:
                try:
                    logger.info(f"Processing URL with Firecrawl: {url}")
                    existing_entry = database.get_scraped_link(url)
                    
                    # Scrape the URL for content
                    scraped_data = None
                    try:
                        scraped_data = app.scrape_url(url)
                    except Exception as e:
                        logger.error(f"Firecrawl scrape_url failed for {url}: {e}")
                        if "rate limit" in str(e).lower() or "limit" in str(e).lower() or "quota" in str(e).lower():
                            api_key_rotator.rotate_key('firecrawl_api_keys')
                            firecrawl_api_key = api_key_rotator.get_key('firecrawl_api_keys')
                            if firecrawl_api_key:
                                app = FirecrawlApp(api_key=firecrawl_api_key)  # Re-initialize with new key
                                logger.info(f"Retrying Firecrawl scrape for {url} with new key.")
                                try:
                                    scraped_data = app.scrape_url(url)
                                except Exception as e_retry:
                                    logger.error(f"Firecrawl scrape_url retry failed for {url}: {e_retry}")
                            else:
                                logger.error("No more Firecrawl API keys to try after rate limit.")
                        

                    if scraped_data and scraped_data.get('content'):
                        content_to_store = scraped_data.get('content')  # Or markdown, depending on preference
                        
                        if existing_entry:
                            logger.info(f"Updating existing entry for URL: {url}")
                            updated_content = existing_entry['content'] + "\n\n--- Updated Content ---\n\n" + content_to_store
                            database.update_scraped_link(url, updated_content, json.dumps(scraped_data.get('metadata', {})))
                            await message.channel.send(f"Information for {url} has been updated with new content.")
                        else:
                            logger.info(f"Creating new entry for URL: {url}")
                            database.store_scraped_link(url, content_to_store, json.dumps(scraped_data.get('metadata', {})))
                            await message.channel.send(f"Information for {url} has been scraped and stored.")
                    elif scraped_data and not scraped_data.get('content'):
                        logger.warning(f"Firecrawl returned no content for {url}, metadata: {scraped_data.get('metadata')}")
                    else:
                        logger.warning(f"Firecrawl returned no data for {url}")

                except Exception as e:
                    logger.error(f"Error processing URL {url} with Firecrawl: {e}")
                    if "rate limit" in str(e).lower() or "limit" in str(e).lower() or "quota" in str(e).lower():
                        api_key_rotator.rotate_key('firecrawl_api_keys')
                        logger.info("Rotated Firecrawl API key due to rate limit during processing.")
                    await message.channel.send(f"Sorry, I encountered an error trying to process the link: {url}")
    # --- End Firecrawl Integration ---

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
                return

            # Let the user know we're processing their request
            processing_msg = await message.channel.send("Processing your request, please wait...")

            try:
                # Call the LLM API
                response = await call_llm_api(query)

                # Split the response if it's too long
                message_parts = await split_long_message(response)

                # Send each part of the response
                for part in message_parts:
                    await message.channel.send(part, allowed_mentions=discord.AllowedMentions.none())

                # Delete the processing message
                await processing_msg.delete()

                logger.info(f"Command executed successfully: /bot - Response length: {len(response)} - Split into {len(message_parts)} parts")
            except Exception as e:
                logger.error(f"Error processing /bot command: {str(e)}", exc_info=True)
                error_msg = "Sorry, an error occurred while processing your request. Please try again later."
                await message.channel.send(error_msg)
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
                    await message.channel.send(error_msg)
                    return

                # Get messages for the channel for today
                messages = database.get_channel_messages_for_day(channel_id, today)

                if not messages:
                    await processing_msg.delete()
                    error_msg = f"No messages found in this channel for today ({today.strftime('%Y-%m-%d')})."
                    await message.channel.send(error_msg)
                    return

                # Call the LLM API for summarization
                summary = await call_llm_for_summary(messages, channel_name, today)

                # Split the summary if it's too long
                summary_parts = await split_long_message(summary)

                # Send each part of the summary
                for part in summary_parts:
                    await message.channel.send(part, allowed_mentions=discord.AllowedMentions.none())

                # Delete the processing message
                await processing_msg.delete()

                logger.info(f"Command executed successfully: /sum-day - Summary length: {len(summary)} - Split into {len(summary_parts)} parts")
            except Exception as e:
                logger.error(f"Error processing /sum-day command: {str(e)}", exc_info=True)
                error_msg = "Sorry, an error occurred while generating the summary. Please try again later."
                await message.channel.send(error_msg)
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