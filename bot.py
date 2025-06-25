# This example requires the 'message_content' intent.

import discord
from discord.ext import commands
import asyncio
import re
import os
import json
from typing import Optional, Dict, Any, Union
from datetime import datetime, timedelta, timezone
import database
from logging_config import logger # Import the logger from the new module
from rate_limiter import check_rate_limit, update_rate_limit_config # Import rate limiting functions
from llm_handler import call_llm_api, call_llm_for_summary, summarize_scraped_content # Import LLM functions
from message_utils import split_long_message, is_message_link_only # Import message utility functions
from summarization_tasks import daily_channel_summarization, set_discord_client, before_daily_summarization # Import summarization tasks
from config_validator import validate_config # Import config validator
from command_handler import handle_bot_command, handle_sum_day_command, handle_sum_hr_command, handle_firecrawl_command # Import command handlers
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
        
        scraped_result: Optional[Union[str, Dict[str, Any]]] = None
        markdown_content: Optional[str] = None

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
            if isinstance(scraped_result, str):
                markdown_content = scraped_result  # Firecrawl returns markdown directly
            else:
                logger.warning(f"Expected string from Firecrawl but got {type(scraped_result)} for URL {url}")
                return

        # Check if scraping was successful
        if not scraped_result:
            logger.warning(f"Failed to scrape content from URL: {url}")
            return

        # For Twitter/X.com URLs scraped with Apify, we already have the markdown content
        if await is_twitter_url(url) and hasattr(config, 'apify_api_token') and config.apify_api_token:
            if isinstance(scraped_result, dict) and 'markdown' in scraped_result:
                markdown_content = scraped_result.get("markdown", "")
            else:
                logger.warning(f"Invalid scraped result structure for Twitter URL {url}: expected dict with 'markdown' key")
                return
        else:
            if isinstance(scraped_result, str):
                markdown_content = scraped_result  # Firecrawl returns markdown directly
            else:
                logger.warning(f"Invalid scraped result for URL {url}: expected string, got {type(scraped_result)}")
                return

        # Step 2: Summarize the scraped content
        if not markdown_content:
            logger.warning(f"No markdown content available for URL: {url}")
            return
            
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

async def cleanup_links_channel():
    """
    Clean up orphaned messages in the links channel that weren't deleted due to bot restarts.
    This removes non-link messages and orphaned bot enforcement messages.
    """
    try:
        import config
        
        # Check if cleanup is enabled and links channel is configured
        if not config.links_cleanup_on_startup or not config.links_channel_id:
            return
        
        # Get the links channel
        try:
            channel_id = int(config.links_channel_id)
            channel = bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"Links channel {channel_id} not found for cleanup")
                return
        except ValueError:
            logger.error(f"Invalid links channel ID: {config.links_channel_id}")
            return
        
        # Calculate cutoff time for cleanup
        from datetime import datetime, timedelta, timezone
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=config.links_cleanup_max_age_hours)
        
        logger.info(f"Starting cleanup of links channel {channel.name} for messages newer than {cutoff_time}")
        
        # Fetch recent messages from main channel and threads
        messages_to_delete = []
        bot_messages_to_delete = []
        
        # Helper function to process messages from a channel or thread
        async def process_channel_messages(channel_to_scan, is_thread=False):
            async for message in channel_to_scan.history(limit=200, after=cutoff_time):
                # Skip if message is too old
                if message.created_at < cutoff_time:
                    continue
                
                # Check if it's a bot enforcement message
                if (message.author == bot.user and 
                    "We only allow sharing of links in this" in message.content):
                    bot_messages_to_delete.append(message)
                    continue
                
                # Skip bot messages that aren't enforcement messages
                if message.author.bot:
                    continue
                
                # Check if user message violates link-only rule
                if not is_message_link_only(message.content):
                    messages_to_delete.append(message)
        
        # Process main channel
        await process_channel_messages(channel, is_thread=False)
        
        # Process threads created from the links channel
        try:
            for thread in channel.threads:
                if thread.parent_id == channel.id:
                    await process_channel_messages(thread, is_thread=True)
        except AttributeError:
            # Some channel types might not have threads attribute
            pass
        except Exception as e:
            logger.warning(f"Error processing threads for cleanup: {e}")
        
        # Also check archived threads
        try:
            async for thread in channel.archived_threads(limit=50):
                if thread.parent_id == channel.id:
                    await process_channel_messages(thread, is_thread=True)
        except Exception as e:
            logger.warning(f"Error processing archived threads for cleanup: {e}")
        
        # Delete non-compliant messages
        deleted_count = 0
        for message in messages_to_delete:
            try:
                await message.delete()
                deleted_count += 1
                logger.info(f"Cleaned up non-link message {message.id} from {message.author}")
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
            except discord.NotFound:
                logger.debug(f"Message {message.id} already deleted")
            except discord.Forbidden:
                logger.warning(f"No permission to delete message {message.id}")
            except Exception as e:
                logger.error(f"Error deleting message {message.id}: {e}")
        
        # Delete orphaned bot enforcement messages
        bot_deleted_count = 0
        for message in bot_messages_to_delete:
            try:
                await message.delete()
                bot_deleted_count += 1
                logger.info(f"Cleaned up orphaned bot enforcement message {message.id}")
                await asyncio.sleep(0.5)
            except discord.NotFound:
                logger.debug(f"Bot message {message.id} already deleted")
            except discord.Forbidden:
                logger.warning(f"No permission to delete bot message {message.id}")
            except Exception as e:
                logger.error(f"Error deleting bot message {message.id}: {e}")
        
        if deleted_count > 0 or bot_deleted_count > 0:
            logger.info(f"Links channel and threads cleanup completed: {deleted_count} user messages, {bot_deleted_count} bot messages deleted")
        else:
            logger.info("Links channel and threads cleanup completed: no orphaned messages found")
    
    except Exception as e:
        logger.error(f"Error during links channel cleanup: {e}", exc_info=True)

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

    # Clean up orphaned messages in links channel
    asyncio.create_task(cleanup_links_channel())

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

    # Check for links channel enforcement
    try:
        import config
        if config.links_channel_id and not message.author.bot:
            # Check if message is in links channel or a thread created from it
            is_links_channel = str(message.channel.id) == config.links_channel_id
            is_links_thread = (
                message.channel.type in (discord.ChannelType.public_thread, discord.ChannelType.private_thread) and
                str(getattr(message.channel, 'parent_id', None)) == config.links_channel_id
            )
            
            # Enhanced logging for debugging thread detection
            logger.info(f"Links channel enforcement check for message {message.id}:")
            logger.info(f"  - Message channel ID: {message.channel.id}")
            logger.info(f"  - Message channel type: {message.channel.type}")
            logger.info(f"  - Message channel name: {getattr(message.channel, 'name', 'N/A')}")
            logger.info(f"  - Configured links channel ID: {config.links_channel_id}")
            logger.info(f"  - Parent channel ID: {getattr(message.channel, 'parent_id', 'N/A')}")
            logger.info(f"  - is_links_channel: {is_links_channel}")
            logger.info(f"  - is_links_thread: {is_links_thread}")
            
            if is_links_channel or is_links_thread:
                # Check if message contains only links
                if not is_message_link_only(message.content):
                    # Determine channel type for logging
                    channel_type = "thread" if is_links_thread else "channel"
                    
                    logger.info(f"Message {message.id} violates links-only rule in {channel_type} {message.channel.name}")
                    logger.info(f"  - Message content: {message.content[:100]}{'...' if len(message.content) > 100 else ''}")
                    logger.info(f"  - Will send enforcement message to channel ID: {message.channel.id}")
                    
                    # Log detailed permission information for debugging
                    await log_permission_details(message)
                    
                    # Send enforcement message
                    enforcement_msg = await message.channel.send(
                        f"{message.author.mention} We only allow sharing of links in this {channel_type}. "
                        f"If you want to comment on a link, please put it in a thread. "
                        f"Otherwise, please type your message in the appropriate channel.\n\n"
                        f"*Both this message and your original message will be deleted in {config.links_channel_delete_delay // 60} minutes.*"
                    )
                    
                    logger.info(f"Sent enforcement message {enforcement_msg.id} to {channel_type} {message.channel.name}")
                    
                    # Schedule deletion of both messages
                    async def delete_messages():
                        try:
                            logger.info(f"Starting scheduled deletion for message {message.id} and enforcement message {enforcement_msg.id} in {channel_type} {message.channel.name}")
                            
                            await asyncio.sleep(config.links_channel_delete_delay)
                            
                            # Delete original message
                            logger.info(f"Attempting to delete original message {message.id} from {channel_type} {message.channel.name} (channel ID: {message.channel.id})")
                            await message.delete()
                            logger.info(f"Successfully deleted original message {message.id}")
                            
                            # Delete enforcement message
                            logger.info(f"Attempting to delete enforcement message {enforcement_msg.id} from {channel_type} {message.channel.name} (channel ID: {message.channel.id})")
                            await enforcement_msg.delete()
                            logger.info(f"Successfully deleted enforcement message {enforcement_msg.id}")
                            
                            logger.info(f"Completed deletion of non-link message {message.id} and enforcement message from links {channel_type}")
                        except discord.NotFound as e:
                            logger.debug(f"Messages already deleted or not found: {e}")
                        except discord.Forbidden as e:
                            logger.warning(f"Bot lacks permission to delete messages in links {channel_type}: {e}")
                        except Exception as e:
                            logger.error(f"Error deleting messages from links {channel_type}: {e}", exc_info=True)
                    
                    # Create background task for deletion
                    asyncio.create_task(delete_messages())
                    
                    logger.info(f"Enforced links-only rule for message {message.id} in {channel_type} {message.channel.name}")
                    return  # Don't process this message further
                else:
                    logger.info(f"Message {message.id} in {message.channel.name} contains only links, allowing it")
    except Exception as e:
        logger.error(f"Error in links channel enforcement: {e}", exc_info=True)

    # Check if this is a command
    bot_mention = f'<@{bot.user.id}>'
    bot_mention_alt = f'<@!{bot.user.id}>'
    is_mention_command = bot_mention in message.content or bot_mention_alt in message.content
    is_sum_day_command = message.content.startswith('/sum-day')
    is_sum_hr_command = message.content.startswith('/sum-hr')
    is_firecrawl_command = message.content.startswith('!firecrawl')

    # Process mention commands in any channel
    if is_mention_command:
        logger.debug(f"Processing mention command in channel #{message.channel.name}")
        await handle_bot_command(message, bot.user, bot)
        return

    # Process firecrawl commands in any channel (they have their own permission checks)
    if is_firecrawl_command:
        logger.debug(f"Processing firecrawl command in channel #{message.channel.name}")
        await handle_firecrawl_command(message, bot.user)
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

async def log_permission_details(message):
    """
    Log detailed permission information for debugging thread deletion issues.
    """
    try:
        channel = message.channel
        guild = message.guild
        bot_member = guild.me if guild else None
        
        logger.info(f"=== PERMISSION DETAILS for message {message.id} ===")
        logger.info(f"Channel type: {channel.type}")
        logger.info(f"Channel ID: {channel.id}")
        logger.info(f"Channel name: {getattr(channel, 'name', 'N/A')}")
        
        if hasattr(channel, 'parent_id') and channel.parent_id:
            logger.info(f"Parent channel ID: {channel.parent_id}")
            parent_channel = guild.get_channel(channel.parent_id) if guild else None
            if parent_channel:
                logger.info(f"Parent channel name: {parent_channel.name}")
        
        if bot_member:
            # Check guild-level permissions
            guild_perms = bot_member.guild_permissions
            logger.info(f"Guild-level manage_messages permission: {guild_perms.manage_messages}")
            logger.info(f"Guild-level administrator permission: {guild_perms.administrator}")
            
            # Check channel-specific permissions
            channel_perms = channel.permissions_for(bot_member)
            logger.info(f"Channel-level manage_messages permission: {channel_perms.manage_messages}")
            logger.info(f"Channel-level send_messages permission: {channel_perms.send_messages}")
            logger.info(f"Channel-level read_messages permission: {channel_perms.read_messages}")
            logger.info(f"Channel-level administrator permission: {channel_perms.administrator}")
            
            # For threads, also check parent channel permissions
            if channel.type in (discord.ChannelType.public_thread, discord.ChannelType.private_thread):
                if hasattr(channel, 'parent') and channel.parent:
                    parent_perms = channel.parent.permissions_for(bot_member)
                    logger.info(f"Parent channel manage_messages permission: {parent_perms.manage_messages}")
                    logger.info(f"Parent channel send_messages permission: {parent_perms.send_messages}")
        
        logger.info("=== END PERMISSION DETAILS ===")
        
    except Exception as e:
        logger.error(f"Error logging permission details: {e}", exc_info=True)

try:
    logger.info("Starting bot...")
    import config # Assuming config.py is in the same directory or accessible

    # Validate configuration using the imported function
    validate_config(config)

    # Log startup (but mask the actual token)
    if config.token:
        token_preview = config.token[:5] + "..." + config.token[-5:] if len(config.token) > 10 else "***masked***"
        logger.info(f"Bot token loaded: {token_preview}")
        logger.info("Connecting to Discord...")

        # Run the bot
        bot.run(config.token)
    else:
        logger.critical("Bot token is not defined or is empty in config.py")
        logger.error("Please ensure your config.py file has a valid Discord bot token.")
except ImportError:
    logger.critical("Config file not found or token not defined", exc_info=True)
    logger.error("Please create a config.py file with your Discord bot token.")
    logger.error("Example: token = 'YOUR_DISCORD_BOT_TOKEN'")
except discord.LoginFailure:
    logger.critical("Invalid Discord token. Please check your token in config.py", exc_info=True)
except Exception as e:
    logger.critical(f"Unexpected error during bot startup: {e}", exc_info=True)
