import discord
import database
import asyncio
from logging_config import logger
from rate_limiter import check_rate_limit
from llm_handler import call_llm_api, call_llm_for_summary
from message_utils import split_long_message
from datetime import datetime, timezone
import re

async def handle_bot_command(message, client_user):
    """Handles the mention command."""
    bot_mention = f'<@{client_user.id}>'
    bot_mention_alt = f'<@!{client_user.id}>'
    query = message.content.replace(bot_mention, '', 1).replace(bot_mention_alt, '', 1).strip()

    if not query:
        error_msg = "Please provide a query after mentioning the bot."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        return

    logger.info(f"Executing mention command - Requested by {message.author}")

    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        error_msg = f"Please wait {wait_time:.1f} seconds before making another request." if reason == "cooldown" \
            else f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return

    processing_msg = await message.channel.send("Processing your request, please wait...")
    try:
        response = await call_llm_api(query)
        message_parts = await split_long_message(response)

        for part in message_parts:
            bot_response = await message.channel.send(part, allowed_mentions=discord.AllowedMentions.none())
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, part)

        await processing_msg.delete()
        logger.info(f"Command executed successfully: mention - Response length: {len(response)} - Split into {len(message_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing mention command: {str(e)}", exc_info=True)
        error_msg = "Sorry, an error occurred while processing your request. Please try again later."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        try:
            await processing_msg.delete()
        except discord.NotFound: # Message might have been deleted already
            pass
        except Exception as del_e:
            logger.warning(f"Could not delete processing message: {del_e}")


async def handle_sum_day_command(message, client_user):
    """Handles the /sum-day command."""
    logger.info(f"Executing command: /sum-day - Requested by {message.author}")

    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        error_msg = f"Please wait {wait_time:.1f} seconds before making another request." if reason == "cooldown" \
            else f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return

    processing_msg = await message.channel.send("Generating channel summary, please wait... This may take a moment.")
    try:
        today = datetime.now(timezone.utc)
        channel_id_str = str(message.channel.id)
        channel_name_str = message.channel.name

        if not database: # Should not happen if bot initialized correctly
            logger.error("Database module not available in handle_sum_day_command")
            await processing_msg.delete()
            error_msg = "Sorry, a critical error occurred (database unavailable). Please try again later."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            return

        # Check if database connection is working
        if not database.check_database_connection():
            logger.error("Database connection check failed in handle_sum_day_command")
            await processing_msg.delete()
            error_msg = "Sorry, a database connection error occurred. Please try again later."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            return

        # Ensure we wait a moment for any recent messages to be stored in the database
        await asyncio.sleep(0.5)

        # Debug: Store a test message to ensure the database is working
        test_message_id = f"test-{datetime.now().timestamp()}"
        test_message_success = database.store_message(
            message_id=test_message_id,
            author_id=str(message.author.id),
            author_name=str(message.author),
            channel_id=channel_id_str,
            channel_name=channel_name_str,
            content="This is a test message to ensure the database is working.",
            created_at=datetime.now(),
            guild_id=str(message.guild.id) if message.guild else None,
            guild_name=message.guild.name if message.guild else None,
            is_bot=False,
            is_command=False
        )
        logger.info(f"Test message storage result: {'Success' if test_message_success else 'Failed'}")

        # Check if there are any messages in the channel at all
        all_channel_messages = database.get_all_channel_messages(channel_id_str, limit=10)
        logger.info(f"Found {len(all_channel_messages)} total messages in channel {channel_name_str} (recent 10)")
        for idx, msg in enumerate(all_channel_messages):
            logger.info(f"All messages {idx+1}: Author: {msg.get('author_name')}, Content: {msg.get('content')[:30]}..., Created: {msg.get('created_at')}")

        # Get messages for the past 24 hours
        messages_for_summary = database.get_channel_messages_for_day(channel_id_str, today)

        # Log the number of messages found and their details
        logger.info(f"Found {len(messages_for_summary)} messages for summary in channel {channel_name_str} (past 24 hours)")
        for idx, msg in enumerate(messages_for_summary):
            logger.info(f"24h Message {idx+1}: Author: {msg.get('author_name')}, Content: {msg.get('content')[:30]}..., Created: {msg.get('created_at')}")

        if not messages_for_summary:
            logger.info(f"No messages found for /sum-day command in channel {channel_name_str} for the past 24 hours")

            # If we have at least our test message, use it for the summary
            if test_message_success:
                logger.info("Using test message for summary since no other messages were found")
                messages_for_summary = [{
                    'author_name': str(message.author),
                    'content': "This is a test message to ensure the database is working.",
                    'created_at': datetime.now(),
                    'is_bot': False,
                    'is_command': False
                }]
            else:
                # If we don't even have the test message, return an error
                await processing_msg.delete()
                error_msg = f"No messages found in this channel for the past 24 hours."
                bot_response = await message.channel.send(error_msg)
                await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
                return

        summary = await call_llm_for_summary(messages_for_summary, channel_name_str, today)
        summary_parts = await split_long_message(summary)

        if message.guild:
            thread = await message.create_thread(name="Daily Summary")
            for part in summary_parts:
                bot_response = await thread.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, thread, part)
        else:
            for part in summary_parts:
                bot_response = await message.channel.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, message.channel, part)

        await processing_msg.delete()
        logger.info(f"Command executed successfully: /sum-day - Summary length: {len(summary)} - Split into {len(summary_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing /sum-day command: {str(e)}", exc_info=True)
        error_msg = "Sorry, an error occurred while generating the summary. Please try again later."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        try:
            await processing_msg.delete()
        except discord.NotFound: # Message might have been deleted already
            pass
        except Exception as del_e:
            logger.warning(f"Could not delete processing message: {del_e}")

async def handle_sum_hr_command(message, client_user):
    """Handles the /sum-hr <num_hours> command."""
    # Parse the hours parameter from the message content
    content = message.content.strip()
    match = re.match(r'/sum-hr\s+(\d+)', content)

    if not match:
        error_msg = "Please provide a valid number of hours. Usage: `/sum-hr <number>` (e.g., `/sum-hr 10`)"
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        return

    hours = int(match.group(1))

    # Validate hours parameter
    if hours <= 0:
        error_msg = "Number of hours must be greater than 0."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        return

    if hours > 168:  # 7 days
        error_msg = "Number of hours cannot exceed 168 (7 days). For longer periods, please use multiple smaller summaries."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        return

    logger.info(f"Executing command: /sum-hr {hours} - Requested by {message.author}")

    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        error_msg = f"Please wait {wait_time:.1f} seconds before making another request." if reason == "cooldown" \
            else f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return

    processing_msg = await message.channel.send(f"Generating channel summary for the past {hours} hours, please wait... This may take a moment.")
    try:
        now = datetime.now(timezone.utc)
        channel_id_str = str(message.channel.id)
        channel_name_str = message.channel.name

        if not database: # Should not happen if bot initialized correctly
            logger.error("Database module not available in handle_sum_hr_command")
            await processing_msg.delete()
            error_msg = "Sorry, a critical error occurred (database unavailable). Please try again later."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            return

        # Check if database connection is working
        if not database.check_database_connection():
            logger.error("Database connection check failed in handle_sum_hr_command")
            await processing_msg.delete()
            error_msg = "Sorry, a database connection error occurred. Please try again later."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            return

        # Ensure we wait a moment for any recent messages to be stored in the database
        await asyncio.sleep(0.5)

        # Get messages for the past specified hours
        messages_for_summary = database.get_channel_messages_for_hours(channel_id_str, now, hours)

        # Log the number of messages found and their details
        logger.info(f"Found {len(messages_for_summary)} messages for summary in channel {channel_name_str} (past {hours} hours)")
        for idx, msg in enumerate(messages_for_summary):
            logger.info(f"{hours}h Message {idx+1}: Author: {msg.get('author_name')}, Content: {msg.get('content')[:30]}..., Created: {msg.get('created_at')}")

        if not messages_for_summary:
            logger.info(f"No messages found for /sum-hr {hours} command in channel {channel_name_str} for the past {hours} hours")
            await processing_msg.delete()
            error_msg = f"No messages found in this channel for the past {hours} hours."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            return

        summary = await call_llm_for_summary(messages_for_summary, channel_name_str, now, hours)
        summary_parts = await split_long_message(summary)

        if message.guild:
            thread_name = f"{hours}h Summary" if hours != 1 else "1h Summary"
            thread = await message.create_thread(name=thread_name)
            for part in summary_parts:
                bot_response = await thread.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, thread, part)
        else:
            for part in summary_parts:
                bot_response = await message.channel.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, message.channel, part)

        await processing_msg.delete()
        logger.info(f"Command executed successfully: /sum-hr {hours} - Summary length: {len(summary)} - Split into {len(summary_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing /sum-hr {hours} command: {str(e)}", exc_info=True)
        error_msg = "Sorry, an error occurred while generating the summary. Please try again later."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        try:
            await processing_msg.delete()
        except discord.NotFound: # Message might have been deleted already
            pass
        except Exception as del_e:
            logger.warning(f"Could not delete processing message: {del_e}")

async def store_bot_response_db(bot_msg_obj, client_user, guild, channel, content_to_store):
    """Helper function to store bot's own messages in the database."""
    try:
        guild_id_str = str(guild.id) if guild else None
        guild_name_str = guild.name if guild else None
        channel_id_str = str(channel.id)
        # Handle DM channel name
        channel_name_str = channel.name if hasattr(channel, 'name') else f"DM with {channel.recipient}"


        success = database.store_message(
            message_id=str(bot_msg_obj.id),
            author_id=str(client_user.id),
            author_name=str(client_user),
            channel_id=channel_id_str,
            channel_name=channel_name_str,
            content=content_to_store,
            created_at=bot_msg_obj.created_at,
            guild_id=guild_id_str,
            guild_name=guild_name_str,
            is_bot=True,
            is_command=False, # Bot responses are not commands themselves
            command_type=None
        )
        if not success:
            logger.warning(f"Failed to store bot response {bot_msg_obj.id} in database")
    except Exception as e:
        logger.error(f"Error storing bot response in database: {str(e)}", exc_info=True)

async def handle_sum_day_command_interaction(message, client_user, interaction):
    """Handles the /sum-day command for slash command interactions."""
    logger.info(f"Executing slash command: /sum-day - Requested by {message.author}")

    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        error_msg = f"Please wait {wait_time:.1f} seconds before making another request." if reason == "cooldown" \
            else f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
        await interaction.followup.send(error_msg, ephemeral=True)
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return

    await interaction.followup.send("Generating channel summary, please wait... This may take a moment.")
    try:
        today = datetime.now(timezone.utc)
        channel_id_str = str(message.channel.id)
        channel_name_str = message.channel.name

        if not database:
            logger.error("Database module not available in handle_sum_day_command_interaction")
            await interaction.followup.send("Sorry, a critical error occurred (database unavailable). Please try again later.", ephemeral=True)
            return

        if not database.check_database_connection():
            logger.error("Database connection check failed in handle_sum_day_command_interaction")
            await interaction.followup.send("Sorry, a database connection error occurred. Please try again later.", ephemeral=True)
            return

        await asyncio.sleep(0.5)

        # Get messages for the past 24 hours
        messages_for_summary = database.get_channel_messages_for_day(channel_id_str, today)
        logger.info(f"Found {len(messages_for_summary)} messages for summary in channel {channel_name_str} (past 24 hours)")

        if not messages_for_summary:
            logger.info(f"No messages found for /sum-day command in channel {channel_name_str} for the past 24 hours")
            await interaction.followup.send(f"No messages found in this channel for the past 24 hours.", ephemeral=True)
            return

        summary = await call_llm_for_summary(messages_for_summary, channel_name_str, today)
        summary_parts = await split_long_message(summary)

        if message.guild:
            thread = await message.create_thread(name="Daily Summary")
            for part in summary_parts:
                bot_response = await thread.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, thread, part)
        else:
            for part in summary_parts:
                await interaction.followup.send(part)

        logger.info(f"Slash command executed successfully: /sum-day - Summary length: {len(summary)} - Split into {len(summary_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing /sum-day slash command: {str(e)}", exc_info=True)
        await interaction.followup.send("Sorry, an error occurred while generating the summary. Please try again later.", ephemeral=True)

async def handle_sum_hr_command_interaction(message, client_user, interaction):
    """Handles the /sum-hr command for slash command interactions."""
    # Parse the hours parameter from the message content
    content = message.content.strip()
    match = re.match(r'/sum-hr\s+(\d+)', content)

    if not match:
        await interaction.followup.send("Invalid command format.", ephemeral=True)
        return

    hours = int(match.group(1))

    logger.info(f"Executing slash command: /sum-hr {hours} - Requested by {message.author}")

    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        error_msg = f"Please wait {wait_time:.1f} seconds before making another request." if reason == "cooldown" \
            else f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
        await interaction.followup.send(error_msg, ephemeral=True)
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return

    await interaction.followup.send(f"Generating channel summary for the past {hours} hours, please wait... This may take a moment.")
    try:
        now = datetime.now(timezone.utc)
        channel_id_str = str(message.channel.id)
        channel_name_str = message.channel.name

        if not database:
            logger.error("Database module not available in handle_sum_hr_command_interaction")
            await interaction.followup.send("Sorry, a critical error occurred (database unavailable). Please try again later.", ephemeral=True)
            return

        if not database.check_database_connection():
            logger.error("Database connection check failed in handle_sum_hr_command_interaction")
            await interaction.followup.send("Sorry, a database connection error occurred. Please try again later.", ephemeral=True)
            return

        await asyncio.sleep(0.5)

        # Get messages for the past specified hours
        messages_for_summary = database.get_channel_messages_for_hours(channel_id_str, now, hours)
        logger.info(f"Found {len(messages_for_summary)} messages for summary in channel {channel_name_str} (past {hours} hours)")

        if not messages_for_summary:
            logger.info(f"No messages found for /sum-hr {hours} command in channel {channel_name_str} for the past {hours} hours")
            await interaction.followup.send(f"No messages found in this channel for the past {hours} hours.", ephemeral=True)
            return

        summary = await call_llm_for_summary(messages_for_summary, channel_name_str, now, hours)
        summary_parts = await split_long_message(summary)

        if message.guild:
            thread_name = f"{hours}h Summary" if hours != 1 else "1h Summary"
            thread = await message.create_thread(name=thread_name)
            for part in summary_parts:
                bot_response = await thread.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, thread, part)
        else:
            for part in summary_parts:
                await interaction.followup.send(part)

        logger.info(f"Slash command executed successfully: /sum-hr {hours} - Summary length: {len(summary)} - Split into {len(summary_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing /sum-hr {hours} slash command: {str(e)}", exc_info=True)
        await interaction.followup.send("Sorry, an error occurred while generating the summary. Please try again later.", ephemeral=True)
