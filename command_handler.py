import discord
import database
from logging_config import logger
from rate_limiter import check_rate_limit
from llm_handler import call_llm_api
from message_utils import split_long_message
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
    """Handles the /sum-day command using the abstraction layer."""
    try:
        # Use the abstraction layer for unified command handling
        from command_abstraction import (
            create_context_from_message,
            create_response_sender,
            create_thread_manager,
            handle_summary_command
        )

        context = create_context_from_message(message)
        response_sender = create_response_sender(message)
        thread_manager = create_thread_manager(message)

        await handle_summary_command(context, response_sender, thread_manager, hours=24)

    except Exception as e:
        logger.error(f"Error in handle_sum_day_command: {str(e)}", exc_info=True)
        error_msg = "Sorry, an error occurred while generating the summary. Please try again later."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)

async def handle_sum_hr_command(message, client_user):
    """Handles the /sum-hr <num_hours> command using the abstraction layer."""
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

    try:
        # Use the abstraction layer for unified command handling
        from command_abstraction import (
            create_context_from_message,
            create_response_sender,
            create_thread_manager,
            handle_summary_command
        )

        context = create_context_from_message(message)
        response_sender = create_response_sender(message)
        thread_manager = create_thread_manager(message)

        await handle_summary_command(context, response_sender, thread_manager, hours=hours)

    except Exception as e:
        logger.error(f"Error in handle_sum_hr_command: {str(e)}", exc_info=True)
        error_msg = "Sorry, an error occurred while generating the summary. Please try again later."
        bot_response = await message.channel.send(error_msg)
        await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)

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




