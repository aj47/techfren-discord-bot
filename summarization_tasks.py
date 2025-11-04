import asyncio
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import tasks
import database
from logging_config import logger
from llm_handler import call_llm_for_summary, analyze_messages_for_points
from message_utils import split_long_message
import config # Assuming config.py is accessible

# This variable will be set by the main bot script
discord_client = None

def set_discord_client(client_instance):
    """Sets the discord client instance for use in this module."""
    global discord_client
    discord_client = client_instance

@tasks.loop(hours=24)
async def daily_channel_summarization():
    """
    Task that runs once per day to:
    1. Retrieve messages from the past 24 hours
    2. Generate summaries for each active channel
    3. Store the summaries in the database
    4. Delete old messages
    """
    if not discord_client:
        logger.error("Discord client not set in summarization_tasks. Aborting daily summarization.")
        return

    try:
        logger.info("Starting daily automated channel summarization")

        # Get the current time and 24 hours ago (in UTC)
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(hours=24)

        # Get active channels from the past 24 hours
        active_channels = database.get_active_channels(hours=24)

        if not active_channels:
            logger.info("No active channels found in the past 24 hours. Skipping summarization.")
            return

        logger.info(f"Found {len(active_channels)} active channels to summarize")

        # Get messages for each channel
        messages_by_channel = database.get_messages_for_time_range(yesterday, now)

        # Track successful summaries for reporting
        successful_summaries = 0
        total_messages_processed = 0

        # Collect all messages across all channels for point analysis
        all_messages_for_points = []

        # Process each active channel
        for channel_data in active_channels:
            channel_id = channel_data['channel_id']
            channel_name = channel_data['channel_name']

            if channel_id not in messages_by_channel:
                logger.warning(f"No messages found for channel {channel_name} ({channel_id}) despite being marked as active")
                continue

            channel_messages = messages_by_channel[channel_id]['messages']

            if not channel_messages:
                continue

            guild_id = channel_data['guild_id']
            guild_name = channel_data['guild_name']

            formatted_messages = []
            for msg in channel_messages:
                if not msg.get('is_command', False):
                    formatted_msg = {
                        'id': msg.get('id', ''),
                        'author_id': msg.get('author_id', ''),
                        'author_name': msg['author_name'],
                        'content': msg['content'],
                        'created_at': msg['created_at'],
                        'is_bot': msg.get('is_bot', False),
                        'is_command': False,
                        'guild_id': guild_id,
                        'channel_id': channel_id
                    }
                    formatted_messages.append(formatted_msg)

                    # Add to global message collection for point analysis (exclude bot messages)
                    if not msg.get('is_bot', False):
                        all_messages_for_points.append(formatted_msg)

            if not formatted_messages:
                logger.info(f"No non-command messages found for channel {channel_name}. Skipping summarization.")
                continue

            active_users = list(set(msg['author_name'] for msg in formatted_messages))

            try:
                summary_text = await call_llm_for_summary(formatted_messages, channel_name, yesterday)
                metadata = {
                    'start_time': yesterday.isoformat(),
                    'end_time': now.isoformat(),
                    'summary_type': 'automated_daily'
                }
                success = database.store_channel_summary(
                    channel_id=channel_id,
                    channel_name=channel_name,
                    date=yesterday,
                    summary_text=summary_text,
                    message_count=len(formatted_messages),
                    active_users=active_users,
                    guild_id=guild_id,
                    guild_name=guild_name,
                    metadata=metadata
                )
                if success:
                    successful_summaries += 1
                    total_messages_processed += len(formatted_messages)
                    logger.info(f"Successfully generated and stored summary for channel {channel_name}")
                    await post_summary_to_reports_channel(channel_id, channel_name, yesterday, summary_text)
            except Exception as e:
                logger.error(f"Error generating summary for channel {channel_name}: {str(e)}", exc_info=True)

        # Award points based on contributions from the past 24 hours
        point_awards_result = None
        if all_messages_for_points:
            try:
                logger.info(f"Analyzing {len(all_messages_for_points)} messages for point awards")
                point_awards_result = await analyze_messages_for_points(all_messages_for_points, max_points=50)

                if point_awards_result and point_awards_result.get('awards'):
                    # Get a representative guild_id (use the first one we find)
                    guild_id = all_messages_for_points[0].get('guild_id') if all_messages_for_points else None

                    if guild_id:
                        for award in point_awards_result['awards']:
                            author_id = award.get('author_id')
                            author_name = award.get('author_name')
                            points = award.get('points', 0)
                            reason = award.get('reason', 'Contribution to the community')

                            # Award points to user
                            success = database.award_points_to_user(author_id, author_name, guild_id, points)

                            if success:
                                # Store the daily award record
                                database.store_daily_point_award(
                                    author_id=author_id,
                                    author_name=author_name,
                                    guild_id=guild_id,
                                    date=yesterday,
                                    points=points,
                                    reason=reason
                                )
                                logger.info(f"Awarded {points} points to {author_name} for: {reason}")

                        # Post the point awards summary to general channel
                        await post_daily_summary_with_points(yesterday, point_awards_result)

                    logger.info(f"Point awarding complete. Awarded to {len(point_awards_result['awards'])} users.")
                else:
                    logger.info("No points were awarded today.")
            except Exception as e:
                logger.error(f"Error awarding points: {str(e)}", exc_info=True)

        if successful_summaries > 0:
            try:
                cutoff_time = now - timedelta(hours=24)
                deleted_count = database.delete_messages_older_than(cutoff_time)
                logger.info(f"Deleted {deleted_count} messages older than {cutoff_time}")
            except Exception as e:
                logger.error(f"Error deleting old messages: {str(e)}", exc_info=True)

        logger.info(f"Daily summarization complete. Generated {successful_summaries} summaries covering {total_messages_processed} messages.")
    except Exception as e:
        logger.error(f"Error in daily channel summarization task: {str(e)}", exc_info=True)

async def post_summary_to_reports_channel(_, channel_name, __, summary_text):
    """
    Post a summary to a designated reports channel if configured.
    """
    if not discord_client:
        logger.error("Discord client not set in summarization_tasks. Cannot post summary to reports channel.")
        return

    try:
        if not hasattr(config, 'reports_channel_id') or not config.reports_channel_id:
            return

        reports_channel = discord_client.get_channel(int(config.reports_channel_id))
        if not reports_channel:
            logger.warning(f"Reports channel with ID {config.reports_channel_id} not found")
            return

        summary_parts = await split_long_message(summary_text)
        for part in summary_parts:
            await reports_channel.send(part, allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)
        logger.info(f"Posted summary for channel {channel_name} to reports channel")
    except Exception as e:
        logger.error(f"Error posting summary to reports channel: {str(e)}", exc_info=True)

async def post_daily_summary_with_points(date, point_awards_result):
    """
    Post the daily point awards summary to the general channel (or configured channel).
    """
    if not discord_client:
        logger.error("Discord client not set in summarization_tasks. Cannot post daily summary.")
        return

    try:
        # Check for general_channel_id, fallback to reports_channel_id
        channel_id = getattr(config, 'general_channel_id', None) or getattr(config, 'reports_channel_id', None)

        if not channel_id:
            logger.warning("No general_channel_id or reports_channel_id configured. Skipping daily summary post.")
            return

        general_channel = discord_client.get_channel(int(channel_id))
        if not general_channel:
            logger.warning(f"General channel with ID {channel_id} not found")
            return

        # Build the summary message
        date_str = date.strftime('%Y-%m-%d')
        awards = point_awards_result.get('awards', [])
        total_awarded = point_awards_result.get('total_awarded', 0)
        summary_text = point_awards_result.get('summary', 'Daily point awards have been distributed.')

        if not awards:
            message = f"**Daily Community Points - {date_str}**\n\nNo points were awarded today."
        else:
            message = f"**Daily Community Points - {date_str}**\n\n{summary_text}\n\n**Point Awards ({total_awarded}/50 points distributed):**\n\n"

            # Sort awards by points (highest first)
            sorted_awards = sorted(awards, key=lambda x: x.get('points', 0), reverse=True)

            for award in sorted_awards:
                author_name = award.get('author_name', 'Unknown')
                points = award.get('points', 0)
                reason = award.get('reason', 'Contribution to the community')

                message += f"• **{author_name}**: +{points} points\n  _{reason}_\n\n"

            # Add leaderboard teaser
            message += "\n_Type `/leaderboard` to see the all-time top contributors!_"

        # Split if too long and send
        message_parts = await split_long_message(message)
        for part in message_parts:
            await general_channel.send(part, allowed_mentions=discord.AllowedMentions.none())

        logger.info(f"Posted daily summary with points to general channel")
    except Exception as e:
        logger.error(f"Error posting daily summary with points: {str(e)}", exc_info=True)

@daily_channel_summarization.before_loop
async def before_daily_summarization():
    """Wait until a specific time to start the daily summarization task."""
    if not discord_client:
        logger.error("Discord client not set in summarization_tasks. Cannot start before_daily_summarization.")
        # Fallback to prevent loop from erroring out immediately if client isn't ready
        await asyncio.sleep(60)
        return

    try:
        summary_hour = getattr(config, 'summary_hour', 0)
        summary_minute = getattr(config, 'summary_minute', 0)
        logger.info(f"Daily summarization scheduled for {summary_hour:02d}:{summary_minute:02d} UTC")

        await discord_client.wait_until_ready()

        now = datetime.now(timezone.utc)
        future = datetime(now.year, now.month, now.day, summary_hour, summary_minute, tzinfo=timezone.utc)
        if now.hour > summary_hour or (now.hour == summary_hour and now.minute >= summary_minute):
            future += timedelta(days=1)

        seconds_to_wait = (future - now).total_seconds()
        logger.info(f"Waiting {seconds_to_wait:.1f} seconds until first daily summarization")
        await asyncio.sleep(seconds_to_wait)
    except Exception as e:
        logger.error(f"Error in before_daily_summarization: {str(e)}", exc_info=True)
        await asyncio.sleep(60)
