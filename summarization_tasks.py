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

async def run_daily_summarization_once(now: datetime | None = None):
    """Run the daily channel summarization logic a single time.

    This is used both by the scheduled daily task and by one-off scripts/tests.
    """
    if not discord_client:
        logger.error("Discord client not set in summarization_tasks. Aborting daily summarization.")
        return

    try:
        logger.info("Starting daily automated channel summarization")

        # Get the current time and 24 hours ago (in UTC)
        if now is None:
            now = datetime.now(timezone.utc)
        yesterday = now - timedelta(hours=24)

        # Get active channels from the past 24 hours
        active_channels = database.get_active_channels(hours=24)

        if not active_channels:
            logger.info("No active channels found in the past 24 hours. Skipping summarization.")
            return

        # If specific channels are configured, filter to just those
        summary_channel_ids = getattr(config, 'summary_channel_ids', None)
        if summary_channel_ids:
            summary_channel_ids_set = {str(cid) for cid in summary_channel_ids}
            active_channels = [
                ch for ch in active_channels
                if str(ch.get('channel_id')) in summary_channel_ids_set
            ]

            if not active_channels:
                logger.info("No configured summary channels had activity in the past 24 hours. Skipping summarization.")
                return

        logger.info(f"Found {len(active_channels)} active channels to summarize")

        # Get messages for each channel
        messages_by_channel = database.get_messages_for_time_range(yesterday, now)

        # Track successful summaries for reporting
        successful_summaries = 0
        total_messages_processed = 0

        # Collect all messages across all channels for point analysis
        all_messages_for_points = []

        # First pass: collect all messages for point analysis
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

            for msg in channel_messages:
                if not msg.get('is_command', False) and not msg.get('is_bot', False):
                    formatted_msg = {
                        'id': msg.get('id', ''),
                        'author_id': msg.get('author_id', ''),
                        'author_name': msg['author_name'],
                        'content': msg['content'],
                        'created_at': msg['created_at'],
                        'is_bot': msg.get('is_bot', False),
                        'is_command': False,
                        'guild_id': guild_id,
                        'channel_id': channel_id,
                        'scraped_url': msg.get('scraped_url'),
                        'scraped_content_summary': msg.get('scraped_content_summary'),
                        'scraped_content_key_points': msg.get('scraped_content_key_points')
                    }
                    all_messages_for_points.append(formatted_msg)

        # Award points based on contributions from the past 24 hours BEFORE posting summaries
        # Define max points per day (configurable)
        max_points_per_day = 50
        point_awards_result = None
        if all_messages_for_points:
            try:
                logger.info(f"Analyzing {len(all_messages_for_points)} messages for point awards")
                point_awards_result = await analyze_messages_for_points(all_messages_for_points, max_points=max_points_per_day)

                if point_awards_result and point_awards_result.get('awards'):
                    # Get guild_id and validate all messages are from the same guild
                    guild_ids = set(msg.get('guild_id') for msg in all_messages_for_points if msg.get('guild_id'))

                    if not guild_ids:
                        logger.warning("No valid guild_id found in messages. Skipping point awards.")
                    elif len(guild_ids) > 1:
                        logger.warning(f"Messages from multiple guilds detected: {guild_ids}. Point awards should be processed per-guild. Using first guild for now.")
                        guild_id = next(iter(guild_ids))
                    else:
                        guild_id = next(iter(guild_ids))

                    if guild_ids:
                        # Check if points have already been awarded for this day
                        existing_awards = database.get_daily_point_awards(guild_id, yesterday)
                        if existing_awards:
                            logger.warning(f"Points already awarded for {yesterday.strftime('%Y-%m-%d')} in guild {guild_id}. Skipping duplicate processing.")
                        else:
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

                        logger.info(f"Point awarding complete. Awarded to {len(point_awards_result['awards'])} users.")
                else:
                    logger.info("No points were awarded today.")
            except Exception as e:
                logger.error(f"Error awarding points: {str(e)}", exc_info=True)

        # Now process each channel and post summaries (with point awards appended to general channel)
        general_channel_id = getattr(config, 'general_channel_id', None)

        # If GENERAL_CHANNEL_ID is not configured, try to find a channel named "general"
        if not general_channel_id and active_channels:
            for channel_data in active_channels:
                if channel_data['channel_name'].lower() == 'general':
                    general_channel_id = channel_data['channel_id']
                    logger.info(f"GENERAL_CHANNEL_ID not configured. Auto-detected general channel: {general_channel_id}")
                    break

        # If still not found, use the first active channel
        if not general_channel_id and active_channels and point_awards_result:
            general_channel_id = active_channels[0]['channel_id']
            logger.info(f"GENERAL_CHANNEL_ID not configured. Using first active channel for point awards: {general_channel_id}")

        for channel_data in active_channels:
            channel_id = channel_data['channel_id']
            channel_name = channel_data['channel_name']

            if channel_id not in messages_by_channel:
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
                        'channel_id': channel_id,
                        'scraped_url': msg.get('scraped_url'),
                        'scraped_content_summary': msg.get('scraped_content_summary'),
                        'scraped_content_key_points': msg.get('scraped_content_key_points')
                    }
                    formatted_messages.append(formatted_msg)

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

                    # If this is the general channel, append point awards to the summary
                    append_points = None
                    if general_channel_id and str(channel_id) == str(general_channel_id) and point_awards_result:
                        append_points = (point_awards_result, max_points_per_day)

                    await post_summary_to_reports_channel(channel_id, channel_name, yesterday, summary_text, append_points)
            except Exception as e:
                logger.error(f"Error generating summary for channel {channel_name}: {str(e)}", exc_info=True)

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


@tasks.loop(hours=24)
async def daily_channel_summarization():
    """Scheduled task wrapper that runs the daily summarization once per day."""
    await run_daily_summarization_once()

async def post_summary_to_reports_channel(channel_id, channel_name, date, summary_text, point_awards_data=None):
    """
    Post a summary into a thread in the channel that was summarized.
    Creates a master message and then posts the summary inside a thread.

    Args:
        channel_id: The channel to post in
        channel_name: The name of the channel
        date: The date of the summary
        summary_text: The summary content
        point_awards_data: Optional tuple of (point_awards_result, max_points) to append to the thread
    """
    if not discord_client:
        logger.error("Discord client not set in summarization_tasks. Cannot post summary to channel.")
        return

    try:
        target_channel = discord_client.get_channel(int(channel_id))
        if not target_channel:
            logger.warning(f"Channel with ID {channel_id} not found; cannot post summary for {channel_name}")
            return

        # Format the date for the master message
        date_str = date.strftime("%B %d, %Y") if date else "Recent Activity"

        # Create a master message
        master_message_content = f"📊 **Daily Summary for {date_str}**"
        master_message = await target_channel.send(
            master_message_content,
            allowed_mentions=discord.AllowedMentions.none(),
            suppress_embeds=True
        )
        logger.info(f"Created master message {master_message.id} for daily summary in {channel_name}")

        # Create a thread from the master message
        thread_name = f"Daily Summary - {date_str}"
        try:
            thread = await master_message.create_thread(
                name=thread_name,
                auto_archive_duration=1440  # 24 hours
            )
            logger.info(f"Created thread {thread.id} for daily summary in {channel_name}")

            # Post the summary parts inside the thread
            summary_parts = await split_long_message(summary_text)
            for part in summary_parts:
                await thread.send(part, allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)

            # If point awards data is provided, append it to the thread
            if point_awards_data:
                point_awards_result, max_points = point_awards_data
                awards = point_awards_result.get('awards', [])
                summary_text_points = point_awards_result.get('summary', 'Daily point awards based on community contributions.')
                total_awarded = sum(award.get('points', 0) for award in awards)

                # Build point awards message
                points_message = f"\n\n---\n\n**🏆 Daily Community Points**\n\n{summary_text_points}\n\n**Point Awards ({total_awarded}/{max_points} points distributed):**\n\n"

                for award in awards:
                    author_name = award.get('author_name', 'Unknown')
                    points = award.get('points', 0)
                    reason = award.get('reason', 'Contribution to the community')
                    points_message += f"• **{author_name}**: +{points} points - {reason}\n"

                # Split and send point awards in the thread
                points_parts = await split_long_message(points_message)
                for part in points_parts:
                    await thread.send(part, allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)

                logger.info(f"Posted point awards to thread {thread.id} in channel {channel_name}")

            logger.info(f"Posted summary for channel {channel_name} in thread {thread.id}")
        except discord.errors.HTTPException as e:
            logger.error(f"Failed to create thread for summary in {channel_name}: {str(e)}", exc_info=True)
            # Fallback: post summary parts directly in the channel
            logger.info(f"Falling back to posting summary directly in channel {channel_name}")
            summary_parts = await split_long_message(summary_text)
            for part in summary_parts:
                await target_channel.send(part, allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)

            # If point awards data is provided, append it to the channel
            if point_awards_data:
                point_awards_result, max_points = point_awards_data
                awards = point_awards_result.get('awards', [])
                summary_text_points = point_awards_result.get('summary', 'Daily point awards based on community contributions.')
                total_awarded = sum(award.get('points', 0) for award in awards)

                # Build point awards message
                points_message = f"\n\n---\n\n**🏆 Daily Community Points**\n\n{summary_text_points}\n\n**Point Awards ({total_awarded}/{max_points} points distributed):**\n\n"

                for award in awards:
                    author_name = award.get('author_name', 'Unknown')
                    points = award.get('points', 0)
                    reason = award.get('reason', 'Contribution to the community')
                    points_message += f"• **{author_name}**: +{points} points - {reason}\n"

                # Split and send point awards in the channel
                points_parts = await split_long_message(points_message)
                for part in points_parts:
                    await target_channel.send(part, allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)

                logger.info(f"Posted point awards to channel {channel_name}")
    except Exception as e:
        logger.error(f"Error posting summary to channel {channel_name}: {str(e)}", exc_info=True)

async def post_daily_summary_with_points(date, point_awards_result, max_points=50):
    """
    Post the daily point awards summary to the general channel (or configured channel).

    Args:
        date: The date for the summary
        point_awards_result: Dictionary containing awards and summary
        max_points: Maximum points available per day (default: 50)
    """
    if not discord_client:
        logger.error("Discord client not set in summarization_tasks. Cannot post point summary.")
        return

    try:
        # Get the general channel ID from config
        general_channel_id = getattr(config, 'general_channel_id', None)
        if not general_channel_id:
            logger.warning("GENERAL_CHANNEL_ID not configured. Skipping point summary post.")
            return

        general_channel = discord_client.get_channel(int(general_channel_id))
        if not general_channel:
            logger.warning(f"General channel with ID {general_channel_id} not found; cannot post point summary")
            return

        # Format the date
        date_str = date.strftime("%B %d, %Y") if date else "Recent Activity"

        # Build the message
        awards = point_awards_result.get('awards', [])
        summary_text = point_awards_result.get('summary', 'Daily point awards based on community contributions.')

        total_awarded = sum(award.get('points', 0) for award in awards)

        message = f"**Daily Community Points - {date_str}**\n\n{summary_text}\n\n**Point Awards ({total_awarded}/{max_points} points distributed):**\n\n"

        for award in awards:
            author_name = award.get('author_name', 'Unknown')
            points = award.get('points', 0)
            reason = award.get('reason', 'Contribution to the community')
            message += f"• **{author_name}**: +{points} points - {reason}\n"

        # Split and send if message is too long
        message_parts = await split_long_message(message)
        for part in message_parts:
            await general_channel.send(part, allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)

        logger.info(f"Posted daily point summary to general channel")
    except Exception as e:
        logger.error(f"Error posting daily point summary: {str(e)}", exc_info=True)

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


# ==================== Daily Role Color Charging ====================

async def process_daily_role_color_charges():
    """
    Process daily point charges for users with active role colors.
    Removes colors from users who don't have enough points.
    """
    if not discord_client:
        logger.error("Discord client not set. Cannot process role color charges.")
        return

    try:
        logger.info("Starting daily role color charge processing")

        today_str = datetime.now().strftime('%Y-%m-%d')

        # Get all guilds that have active role colors
        guild_ids = database.get_all_guilds_with_role_colors()

        if not guild_ids:
            logger.info("No active role colors to process")
            return

        total_charged = 0
        total_removed = 0

        for guild_id in guild_ids:
            # Get all active role colors for this guild
            active_colors = database.get_all_active_role_colors(guild_id)

            for color_record in active_colors:
                author_id = color_record['author_id']
                author_name = color_record['author_name']
                role_id = color_record['role_id']
                points_per_day = color_record['points_per_day']
                last_charged = color_record['last_charged_date']

                # Skip if already charged today
                if last_charged == today_str:
                    logger.debug(f"User {author_name} already charged today, skipping")
                    continue

                # Check if user has enough points
                current_points = database.get_user_points(author_id, guild_id)

                if current_points >= points_per_day:
                    # Deduct points
                    if database.deduct_user_points(author_id, guild_id, points_per_day):
                        # Update last charged date
                        database.update_role_color_last_charged(author_id, guild_id, today_str)
                        total_charged += 1
                        logger.info(f"Charged {points_per_day} points from {author_name} for color role")
                else:
                    # User doesn't have enough points - remove their color role
                    logger.info(f"User {author_name} has insufficient points ({current_points} < {points_per_day}). Removing color role.")

                    # Try to remove the role from Discord
                    try:
                        guild = discord_client.get_guild(int(guild_id))
                        if guild:
                            role = guild.get_role(int(role_id))
                            if role:
                                await role.delete(reason=f"User {author_name} ran out of points for color role")
                                logger.info(f"Deleted role {role.name} from guild {guild.name}")
                    except discord.Forbidden:
                        logger.warning(f"No permission to delete role {role_id} in guild {guild_id}")
                    except Exception as e:
                        logger.error(f"Error deleting role: {str(e)}")

                    # Remove from database
                    database.remove_user_role_color(author_id, guild_id)
                    total_removed += 1

        logger.info(f"Daily role color charging complete. Charged: {total_charged}, Removed: {total_removed}")

    except Exception as e:
        logger.error(f"Error processing daily role color charges: {str(e)}", exc_info=True)


@tasks.loop(hours=24)
async def daily_role_color_charging():
    """Scheduled task to charge users for their color roles daily."""
    await process_daily_role_color_charges()


@daily_role_color_charging.before_loop
async def before_daily_role_color_charging():
    """Wait until a specific time to start the daily role color charging task."""
    if not discord_client:
        logger.error("Discord client not set. Cannot start before_daily_role_color_charging.")
        await asyncio.sleep(60)
        return

    try:
        # Run role color charging at the same time as the summarization
        summary_hour = getattr(config, 'summary_hour', 0)
        summary_minute = getattr(config, 'summary_minute', 0)

        charge_hour = summary_hour
        charge_minute = summary_minute

        logger.info(f"Daily role color charging scheduled for {charge_hour:02d}:{charge_minute:02d} UTC")

        await discord_client.wait_until_ready()

        now = datetime.now(timezone.utc)
        future = datetime(now.year, now.month, now.day, charge_hour, charge_minute, tzinfo=timezone.utc)
        if now.hour > charge_hour or (now.hour == charge_hour and now.minute >= charge_minute):
            future += timedelta(days=1)

        seconds_to_wait = (future - now).total_seconds()
        logger.info(f"Waiting {seconds_to_wait:.1f} seconds until first daily role color charging")
        await asyncio.sleep(seconds_to_wait)
    except Exception as e:
        logger.error(f"Error in before_daily_role_color_charging: {str(e)}", exc_info=True)
        await asyncio.sleep(60)
