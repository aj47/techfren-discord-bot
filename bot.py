# This example requires the 'message_content' intent.

import discord
from discord.ext import commands
import asyncio
import re
import os
import json
from typing import Optional
from datetime import datetime, timedelta, timezone
import database
from logging_config import logger # Import the logger from the new module
from rate_limiter import check_rate_limit, update_rate_limit_config # Import rate limiting functions
from llm_handler import call_llm_api, call_llm_for_summary, summarize_scraped_content # Import LLM functions
from message_utils import split_long_message # Import message utility functions
from youtube_handler import is_youtube_url, scrape_youtube_content # Import YouTube functions
from summarization_tasks import daily_channel_summarization, set_discord_client, before_daily_summarization # Import summarization tasks
from config_validator import validate_config # Import config validator
from command_handler import handle_bot_command, handle_sum_day_command, handle_sum_hr_command # Import command handlers
from firecrawl_handler import scrape_url_content # Import Firecrawl handler
from apify_handler import scrape_twitter_content, is_twitter_url # Import Apify handler
from image_handler import process_and_update_message_with_image_analysis # Import image handler

_background_tasks = set()

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
        elif message.content.startswith('/bot'):
            is_command = True
            command_type = "/bot"
        elif message.content.startswith('/sum-day'):
            is_command = True
            command_type = "/sum-day"
        elif message.content.startswith('/sum-hr'):
            is_command = True
            command_type = "/sum-hr"

        # Process attachments
        attachment_urls = None
        attachment_types = None
        image_analysis = None
        
        if message.attachments:
            attachment_urls_list = []
            attachment_types_list = []
            
            for attachment in message.attachments:
                attachment_urls_list.append(attachment.url)
                attachment_types_list.append(attachment.content_type)
                
                # If it's an image, trigger background analysis after storing the message
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    logger.info(f"Detected image attachment: {attachment.filename} ({attachment.content_type})")
            
            attachment_urls = json.dumps(attachment_urls_list)
            attachment_types = json.dumps(attachment_types_list)

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
            attachment_urls=attachment_urls,
            attachment_types=attachment_types,
            image_analysis=image_analysis
        )

        # If message has image attachments, analyze them
        if message.attachments and any(attachment.content_type and attachment.content_type.startswith('image/') for attachment in message.attachments):
            background_task = asyncio.create_task(
                analyze_image_attachments_background(str(message.id), message)
            )
            _background_tasks.add(background_task)
            background_task.add_done_callback(lambda t: _background_tasks.discard(t))

        if not success:
            # This is usually because the message already exists (common when bot restarts)
            logger.debug(f"Failed to store message {message.id} in database (likely duplicate)")

        # Note: Automatic URL processing disabled - URLs are now processed on-demand when requested
        # This saves resources and avoids processing URLs that nobody asks about
    except Exception as e:
        logger.error(f"Error storing message in database: {str(e)}", exc_info=True)

    # Check if this is a command
    bot_mention = f'<@{bot.user.id}>'
    bot_mention_alt = f'<@!{bot.user.id}>'
    is_mention_command = bot_mention in message.content or bot_mention_alt in message.content
    is_sum_day_command = message.content.startswith('/sum-day')
    is_sum_hr_command = message.content.startswith('/sum-hr')
    is_analyze_images_command = message.content.startswith('/analyze-images')

    # Process mention commands in any channel
    if is_mention_command:
        logger.debug(f"Processing mention command in channel #{message.channel.name}")
        await handle_bot_command(message, bot.user, bot)
        return

    # If not a command we recognize, ignore
    if not (is_sum_day_command or is_sum_hr_command or is_analyze_images_command):
        return

    # Process commands
    try:
        if is_sum_day_command:
            await handle_sum_day_command(message, bot.user)
        elif is_sum_hr_command:
            await handle_sum_hr_command(message, bot.user)
        elif is_analyze_images_command:
            await handle_analyze_images_command(message)
    except Exception as e:
        logger.error(f"Error processing command in on_message: {e}", exc_info=True)
        # Optionally notify about the error in the channel if it's a user-facing command error

async def handle_analyze_images_command(message):
    """Handle the /analyze-images command"""
    await _handle_analyze_images_command(message, slash=False)

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
    except discord.HTTPException as e:
        if e.status == 400 and e.code == 40060:
            # Interaction already acknowledged, continue without deferring
            logger.warning(f"Interaction already acknowledged for {command_name}, continuing...")
        else:
            # Re-raise other HTTP exceptions
            raise
    except discord.NotFound as e:
        if e.code == 10062:
            # Interaction expired (took too long to respond)
            logger.error(f"Interaction expired for {command_name} - took too long to respond")
            return  # Can't do anything with an expired interaction
        else:
            # Re-raise other NotFound exceptions
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

@bot.tree.command(name="analyze-images", description="Analyze recent images in the channel")
async def analyze_images_slash(interaction: discord.Interaction):
    """Slash command to analyze recent images"""
    await _handle_analyze_images_command(interaction, slash=True, target_message=None)

@bot.tree.context_menu(name="Analyze images")
async def analyze_images_context_menu(interaction: discord.Interaction, message: discord.Message):
    """Context menu command to analyze images in a specific message"""
    await _handle_analyze_images_command(interaction, slash=True, target_message=message)

async def _handle_analyze_images_command(interaction, *, slash: bool = False, target_message: discord.Message = None):
    """
    Handle image analysis command (both slash, mention, and context menu).
    
    Args:
        interaction: Discord interaction or message
        slash (bool): Whether this is a slash command
        target_message (discord.Message): Specific message to analyze (from context menu)
    """
    try:
        # Defer the response if it's a slash command
        if slash:
            await interaction.response.defer()
        
        # Get the message to analyze
        if slash:
            # Prefer explicit target (e.g., from context menu)
            if target_message is not None:
                pass  # Use the provided target_message
            else:
                # Look for images in recent messages in the channel
                async for msg in interaction.channel.history(limit=10):
                    if msg.attachments and any(att.content_type and att.content_type.startswith('image/') for att in msg.attachments):
                        target_message = msg
                        break
        else:
            # For mention command, use the message that triggered it
            target_message = interaction
        
        if not target_message:
            error_msg = "No message with images found. Reply to a message with images or use in a channel with recent images."
            if slash:
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.reply(error_msg, mention_author=False)
            return
        
        has_images = target_message.attachments and any(
            att.content_type and att.content_type.startswith('image/')
            for att in target_message.attachments
        )

        if not has_images:
            error_msg = "The selected message does not contain any images to analyze."
            if slash:
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.reply(error_msg, mention_author=False)
            return

        success = await process_and_update_message_with_image_analysis(str(target_message.id), target_message)
        
        if not success:
            error_msg = "Failed to analyze the images in the message. Please try again later."
            if slash:
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.reply(error_msg, mention_author=False)
            return
        
        # Get the updated analysis from database
        message_data = await database.get_message_by_id(str(target_message.id))
        
        if message_data and message_data.get('image_analysis'):
            # Parse the image analysis JSON
            analysis_data = json.loads(message_data['image_analysis'])
            
            if analysis_data and len(analysis_data) > 0:
                # Format the response
                response_parts = ["📷 **Image Analysis Results**:"]
                
                for i, img_data in enumerate(analysis_data, 1):
                    response_parts.append(f"\n**Image {i}: {img_data.get('filename', 'Unknown')}**")
                    response_parts.append(f"{img_data.get('analysis', 'No analysis available')}")
                
                full_response = "\n".join(response_parts)
                
                # Split response into parts if needed
                parts = await split_long_message(full_response)
                if slash:
                    for part in parts:
                        await interaction.followup.send(part)
                else:
                    for idx, part in enumerate(parts):
                        if idx == 0:
                            await interaction.reply(part, mention_author=False)
                        else:
                            await interaction.channel.send(part)
            else:
                no_analysis_msg = "No analysis data available for the images."
                if slash:
                    await interaction.followup.send(no_analysis_msg)
                else:
                    await interaction.reply(no_analysis_msg, mention_author=False)
        else:
            no_analysis_msg = "Image analysis is still in progress. Please wait a moment and try again."
            if slash:
                await interaction.followup.send(no_analysis_msg, ephemeral=True)
            else:
                await interaction.reply(no_analysis_msg, mention_author=False)
                
    except Exception as e:
        logger.error(f"Error in image analysis command: {e}", exc_info=True)
        error_msg = "Sorry, an error occurred while analyzing the images. Please try again later."
        try:
            if slash:
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.reply(error_msg, mention_author=False)
        except Exception as send_exc:
            logger.error(
                "Failed to send error response for image analysis command: %s",
                send_exc,
                exc_info=True,
            )

async def analyze_image_attachments_background(message_id: str, message):
    """
    Background task to analyze image attachments in a message.
    
    Args:
        message_id (str): Discord message ID
        message: Discord message object
    """
    try:
        logger.info(f"Starting background image analysis for message {message_id}")
        success = await process_and_update_message_with_image_analysis(message_id, message)
        if success:
            logger.info(f"Successfully completed image analysis for message {message_id}")
        else:
            logger.warning(f"Failed to complete image analysis for message {message_id}")
    except Exception as e:
        logger.error(f"Background image analysis error for message {message_id}: {e!s}", exc_info=True)

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
