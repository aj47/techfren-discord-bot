import asyncio
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import tasks
import database
from logging_config import logger
from llm_handler import call_llm_for_summary
from message_utils import split_long_message
import config  # Assuming config.py is accessible

# This variable will be set by the main bot script
discord_client = None


def set_discord_client(client_instance):
    """Sets the discord client instance for use in this module."""
    global discord_client
    discord_client = client_instance


def _validate_discord_client():
    """Validate that discord client is available."""
    if not discord_client:
        logger.error(
            "Discord client not set in summarization_tasks. Aborting daily summarization."  # noqa: E501
        )
        return False
    return True


def _format_channel_messages(channel_messages, guild_id, channel_id):
    """Format messages for summarization."""
    formatted_messages = []
    for msg in channel_messages:
        if not msg.get("is_command", False):
            formatted_messages.append(
                {
                    "id": msg.get("id", ""),
                    "author_name": msg["author_name"],
                    "content": msg["content"],
                    "created_at": msg["created_at"],
                    "is_bot": msg.get("is_bot", False),
                    "is_command": False,
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                }
            )
    return formatted_messages


async def _process_channel_summary(channel_data, channel_messages, now):
    """Process summary for a single channel."""
    channel_id = channel_data["channel_id"]
    channel_name = channel_data["channel_name"]
    guild_id = channel_data["guild_id"]
    guild_name = channel_data["guild_name"]

    formatted_messages = _format_channel_messages(
        channel_messages, guild_id, channel_id)

    if not formatted_messages:
        logger.info(
            f"No non-command messages found for channel {channel_name}. Skipping summarization.")  # noqa: E501
        return 0, 0

    try:
        summary, chart_data = await call_llm_for_summary(
            formatted_messages, channel_name, now, hours=24, force_charts=False
        )

        if not summary or "No messages found" in summary:
            logger.info("No meaningful summary generated for channel %s", channel_name)
            return 0, 0

        # Extract unique users from messages and sort them by activity
        from sorting_utils import insertion_sort

        # Convert to list of dicts for sorting by activity
        user_counts = {}
        for msg in formatted_messages:
            if not msg["is_bot"]:
                user = msg["author_name"]
                user_counts[user] = user_counts.get(user, 0) + 1

        # Sort users by message count (most active first)
        user_list = [{"name": user, "count": count}
                     for user, count in user_counts.items()]
        if len(user_list) < 20:
            sorted_users = insertion_sort(user_list, key="count", reverse=True)
        else:
            from sorting_utils import quick_sort
            sorted_users = quick_sort(user_list, key="count", reverse=True)

        active_users = [user["name"] for user in sorted_users]

        # Store the summary in the database
        await database.store_channel_summary(
            channel_id=channel_id,
            channel_name=channel_name,
            date=now,
            summary_text=summary,
            message_count=len(formatted_messages),
            active_users=active_users,
            guild_id=guild_id,
            guild_name=guild_name,
            metadata={"automated": True, "chart_data": chart_data is not None},
        )

        logger.info(
            f"Successfully summarized channel {channel_name} ({
                len(formatted_messages)} messages)")

        # Post to reports channel if configured
        try:
            await post_summary_to_reports_channel(
                channel_id, channel_name, now, summary
            )
        except Exception as report_error:
            logger.warning("Failed to post summary to reports channel: %s", report_error)

        return 1, len(formatted_messages)

    except Exception as e:
        logger.error("Error summarizing channel %s: %s", channel_name, e, exc_info=True)
        return 0, 0


async def _get_active_channels_data():
    """Get active channels and their time range."""
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)
    active_channels = await database.get_active_channels(hours=24)

    if not active_channels:
        logger.info(
            "No active channels found in the past 24 hours. Skipping summarization.")
        return None, None, None

    logger.info("Found %d active channels to summarize", len(active_channels))
    return active_channels, yesterday, now


async def _process_all_channels(active_channels, messages_by_channel, now):
    """Process summaries for all active channels."""
    successful_summaries = 0
    total_messages_processed = 0

    for channel_data in active_channels:
        channel_id = channel_data["channel_id"]
        channel_name = channel_data["channel_name"]

        if channel_id not in messages_by_channel:
            logger.warning(
                f"No messages found for channel {channel_name} ({channel_id}) despite being marked as active")  # noqa: E501
            continue

        channel_messages = messages_by_channel[channel_id]["messages"]
        if not channel_messages:
            continue

        success_count, message_count = await _process_channel_summary(
            channel_data, channel_messages, now
        )
        successful_summaries += success_count
        total_messages_processed += message_count

    return successful_summaries, total_messages_processed


async def _cleanup_old_messages(now, successful_summaries):
    """Delete old messages if summaries were successful."""
    if successful_summaries > 0:
        try:
            cutoff_time = now - timedelta(hours=24)
            deleted_count = await database.delete_messages_older_than(cutoff_time)
            logger.info("Deleted %s messages older than %s", deleted_count, cutoff_time)
        except Exception as e:
            logger.error("Error deleting old messages: %s", str(e), exc_info=True)


@tasks.loop(hours=24)
async def daily_channel_summarization():
    """
    Task that runs once per day to:
    1. Retrieve messages from the past 24 hours
    2. Generate summaries for each active channel
    3. Store the summaries in the database
    4. Delete old messages
    """
    if not _validate_discord_client():
        return

    try:
        logger.info("Starting daily automated channel summarization")

        # Get active channels
        active_channels, yesterday, now = await _get_active_channels_data()
        if not active_channels:
            return

        # Get messages for time range
        messages_by_channel = await database.get_messages_for_time_range(yesterday, now)

        # Process all channels
        successful_summaries, total_messages_processed = await _process_all_channels(
            active_channels, messages_by_channel, now
        )

        # Cleanup old messages
        await _cleanup_old_messages(now, successful_summaries)

        logger.info(
            f"Daily summarization complete. Generated {successful_summaries} summaries covering {total_messages_processed} messages."  # noqa: E501
        )
    except Exception as e:
        logger.error(
            f"Error in daily channel summarization task: {
                str(e)}", exc_info=True)


async def post_summary_to_reports_channel(_, channel_name, __, summary_text):
    """
    Post a summary to a designated reports channel if configured.
    """
    if not discord_client:
        logger.error(
            "Discord client not set in summarization_tasks. Cannot post summary to reports channel."  # noqa: E501
        )
        return

    try:
        if not hasattr(config, "reports_channel_id") or not config.reports_channel_id:
            return

        reports_channel = discord_client.get_channel(int(config.reports_channel_id))
        if not reports_channel:
            logger.warning(
                f"Reports channel with ID {config.reports_channel_id} not found"
            )
            return

        summary_parts = await split_long_message(summary_text)
        for part in summary_parts:
            await reports_channel.send(
                part,
                allowed_mentions=discord.AllowedMentions.none(),
                suppress_embeds=True,
            )
        logger.info("Posted summary for channel %s to reports channel", channel_name)
    except Exception as e:
        logger.error(
            f"Error posting summary to reports channel: {str(e)}", exc_info=True
        )


@daily_channel_summarization.before_loop
async def before_daily_summarization():
    """Wait until a specific time to start the daily summarization task."""
    if not discord_client:
        logger.error(
            "Discord client not set in summarization_tasks. Cannot start before_daily_summarization."  # noqa: E501
        )
        # Fallback to prevent loop from erroring out immediately if client isn't ready
        await asyncio.sleep(60)
        return

    try:
        summary_hour = getattr(config, "summary_hour", 0)
        summary_minute = getattr(config, "summary_minute", 0)
        logger.info(
            f"Daily summarization scheduled for {
                summary_hour:02d}:{
                summary_minute:02d} UTC")

        await discord_client.wait_until_ready()

        now = datetime.now(timezone.utc)
        future = datetime(
            now.year,
            now.month,
            now.day,
            summary_hour,
            summary_minute,
            tzinfo=timezone.utc,
        )
        if now.hour > summary_hour or (
            now.hour == summary_hour and now.minute >= summary_minute
        ):
            future += timedelta(days=1)

        seconds_to_wait = (future - now).total_seconds()
        logger.info(
            f"Waiting {seconds_to_wait:.1f} seconds until first daily summarization"
        )
        await asyncio.sleep(seconds_to_wait)
    except Exception as e:
        logger.error("Error in before_daily_summarization: %s", str(e), exc_info=True)
        await asyncio.sleep(60)
