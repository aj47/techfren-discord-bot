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
        today = datetime.now()
        channel_id_str = str(message.channel.id)
        channel_name_str = message.channel.name

        if not database: # Should not happen if bot initialized correctly
            logger.error("Database module not available in handle_sum_day_command")
            await processing_msg.delete()
            error_msg = "Sorry, a critical error occurred (database unavailable). Please try again later."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            return

        messages_for_summary = database.get_channel_messages_for_day(channel_id_str, today)

        if not messages_for_summary:
            await processing_msg.delete()
            error_msg = f"No messages found in this channel for today ({today.strftime('%Y-%m-%d')})."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            logger.info(f"No messages found for /sum-day command in channel {channel_name_str}")
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

async def handle_sum_week_command(message, client_user):
    """Handles the /sum-week command."""
    logger.info(f"Executing command: /sum-week - Requested by {message.author}")

    is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
    if is_limited:
        error_msg = f"Please wait {wait_time:.1f} seconds before making another request." if reason == "cooldown" \
            else f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
        logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
        return

    processing_msg = await message.channel.send("Generating weekly channel summary, please wait... This may take a moment.")
    try:
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        channel_id_str = str(message.channel.id)
        channel_name_str = message.channel.name

        if not database: # Should not happen if bot initialized correctly
            logger.error("Database module not available in handle_sum_week_command")
            await processing_msg.delete()
            error_msg = "Sorry, a critical error occurred (database unavailable). Please try again later."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            return

        messages_for_summary = database.get_channel_messages_for_week(channel_id_str, week_start)

        if not messages_for_summary:
            await processing_msg.delete()
            error_msg = f"No messages found in this channel for the current week ({week_start.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')})."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            logger.info(f"No messages found for /sum-week command in channel {channel_name_str}")
            return

        summary = await call_llm_for_summary(messages_for_summary, channel_name_str, week_start)
        summary_parts = await split_long_message(summary)

        if message.guild:
            thread = await message.create_thread(name="Weekly Summary")
            for part in summary_parts:
                bot_response = await thread.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, thread, part)
        else:
            for part in summary_parts:
                bot_response = await message.channel.send(part, allowed_mentions=discord.AllowedMentions.none())
                await store_bot_response_db(bot_response, client_user, message.guild, message.channel, part)
            
        await processing_msg.delete()
        logger.info(f"Command executed successfully: /sum-week - Summary length: {len(summary)} - Split into {len(summary_parts)} parts")
    except Exception as e:
        logger.error(f"Error processing /sum-week command: {str(e)}", exc_info=True)
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
