import discord
import database
from logging_config import logger
from rate_limiter import check_rate_limit
from llm_handler import call_llm_api, call_llm_for_summary
from message_utils import split_long_message
from datetime import datetime, timedelta

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


async def handle_sum_command(message, client_user, start_date, end_date, summary_type):
    """Handles summarization commands with parameters for the timeframe."""
    logger.info(f"Executing command: {summary_type} - Requested by {message.author}")

    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        error_msg = f"Please wait {wait_time:.1f} seconds before making another request." if reason == "cooldown" \
            else f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return

    processing_msg = await message.channel.send(f"Generating {summary_type} summary, please wait... This may take a moment.")
    try:
        channel_id_str = str(message.channel.id)
        channel_name_str = message.channel.name

        if not database: # Should not happen if bot initialized correctly
            logger.error(f"Database module not available in {summary_type} command")
            await processing_msg.delete()
            error_msg = "Sorry, a critical error occurred (database unavailable). Please try again later."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            return

        messages_for_summary = database.get_channel_messages_for_timeframe(channel_id_str, start_date, end_date)

        if not messages_for_summary:
            await processing_msg.delete()
            error_msg = f"No messages found in this channel for the specified timeframe ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            logger.info(f"No messages found for {summary_type} command in channel {channel_name_str}")
            return

        summary = await call_llm_for_summary(messages_for_summary, channel_name_str, start_date)
        summary_parts = await split_long_message(summary)

        if message.guild:
            thread = await message.create_thread(name=f"{summary_type.capitalize()} Summary")
            for part in summary_parts:
                bot_response = await thread.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, thread, part)
        else:
            for part in summary_parts:
                bot_response = await message.channel.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, message.channel, part)
            
        await processing_msg.delete()
        logger.info(f"Command executed successfully: {summary_type} - Summary length: {len(summary)} - Split into {len(summary_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing {summary_type} command: {str(e)}", exc_info=True)
        error_msg = "Sorry, an error occurred while generating the summary. Please try again later."
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
    today = datetime.now()
    start_date = datetime(today.year, today.month, today.day, 0, 0, 0)
    end_date = datetime(today.year, today.month, today.day, 23, 59, 59, 999999)
    await handle_sum_command(message, client_user, start_date, end_date, "/sum-day")

async def handle_sum_week_command(message, client_user):
    """Handles the /sum-week command."""
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    start_date = datetime(week_start.year, week_start.month, week_start.day, 0, 0, 0)
    end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
    await handle_sum_command(message, client_user, start_date, end_date, "/sum-week")

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
