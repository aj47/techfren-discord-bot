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


async def handle_summary_command(message, client_user, timeframe, get_messages_func, reference_date, thread_name):
    """
    Generic handler for summary commands.

    Args:
        message: The Discord message that triggered the command
        client_user: The bot's user object
        timeframe: String describing the timeframe (e.g., "day", "week")
        get_messages_func: Function to retrieve messages for the timeframe
        reference_date: The date to use for the summary
        thread_name: Name for the thread if created
    """
    logger.info(f"Executing command: /sum-{timeframe} - Requested by {message.author}")

    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        error_msg = f"Please wait {wait_time:.1f} seconds before making another request." if reason == "cooldown" \
            else f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return

    processing_msg = await message.channel.send(f"Generating {timeframe}ly channel summary, please wait... This may take a moment.")
    try:
        channel_id_str = str(message.channel.id)
        channel_name_str = message.channel.name

        if not database: # Should not happen if bot initialized correctly
            logger.error(f"Database module not available in handle_sum_{timeframe}_command")
            await processing_msg.delete()
            error_msg = "Sorry, a critical error occurred (database unavailable). Please try again later."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            return

        messages_for_summary = get_messages_func(channel_id_str, reference_date)

        if not messages_for_summary:
            await processing_msg.delete()

            # Format error message based on timeframe
            if timeframe == "day":
                date_str = reference_date.strftime('%Y-%m-%d')
                error_msg = f"No messages found in this channel for today ({date_str})."
            elif timeframe == "week":
                today = datetime.now()
                date_str = f"{reference_date.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}"
                error_msg = f"No messages found in this channel for the current week ({date_str})."

            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            logger.info(f"No messages found for /sum-{timeframe} command in channel {channel_name_str}")
            return

        summary = await call_llm_for_summary(messages_for_summary, channel_name_str, reference_date)
        summary_parts = await split_long_message(summary)

        if message.guild:
            thread = await message.create_thread(name=thread_name)
            for part in summary_parts:
                bot_response = await thread.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, thread, part)
        else:
            for part in summary_parts:
                bot_response = await message.channel.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, message.channel, part)

        await processing_msg.delete()
        logger.info(f"Command executed successfully: /sum-{timeframe} - Summary length: {len(summary)} - Split into {len(summary_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing /sum-{timeframe} command: {str(e)}", exc_info=True)
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
    await handle_summary_command(
        message=message,
        client_user=client_user,
        timeframe="day",
        get_messages_func=database.get_channel_messages_for_day,
        reference_date=today,
        thread_name="Daily Summary"
    )

async def handle_sum_week_command(message, client_user):
    """Handles the /sum-week command."""
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    await handle_summary_command(
        message=message,
        client_user=client_user,
        timeframe="week",
        get_messages_func=database.get_channel_messages_for_week,
        reference_date=week_start,
        thread_name="Weekly Summary"
    )

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
