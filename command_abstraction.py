"""
Command abstraction layer to eliminate MockMessage pattern.

This module provides a unified interface for handling both Discord message-based
and interaction-based commands without relying on mocking Discord objects.
"""

from dataclasses import dataclass
from typing import Optional, Union, Protocol
import discord


@dataclass
class CommandContext:
    """Abstraction for command execution context."""
    user_id: int
    user_name: str
    channel_id: int
    channel_name: Optional[str]
    guild_id: Optional[int]
    guild_name: Optional[str]
    content: str
    source_type: str  # 'message' or 'interaction'


class ResponseSender(Protocol):
    """Protocol for sending responses regardless of command source."""
    
    async def send(self, content: str, ephemeral: bool = False) -> None:
        """Send a response message."""
        ...
    
    async def send_in_parts(self, parts: list[str], ephemeral: bool = False) -> None:
        """Send multiple message parts."""
        ...


class MessageResponseSender:
    """Response sender for regular Discord messages."""
    
    def __init__(self, channel: discord.TextChannel):
        self.channel = channel
    
    async def send(self, content: str, ephemeral: bool = False) -> None:
        # `ephemeral` has no meaning for regular messages; we silently ignore it.
        await self.channel.send(content, allowed_mentions=discord.AllowedMentions.none())
    
    async def send_in_parts(self, parts: list[str], ephemeral: bool = False) -> None:
        for part in parts:
            await self.channel.send(part, allowed_mentions=discord.AllowedMentions.none())


class InteractionResponseSender:
    """Response sender for Discord slash command interactions."""
    
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
    
    async def send(self, content: str, ephemeral: bool = False) -> None:
        await self.interaction.followup.send(content, ephemeral=ephemeral)
    
    async def send_in_parts(self, parts: list[str], ephemeral: bool = False) -> None:
        for part in parts:
            await self.interaction.followup.send(part, ephemeral=ephemeral)


class ThreadManager:
    """Handles thread creation for both message and interaction contexts."""
    
    def __init__(self, channel: discord.TextChannel, guild: Optional[discord.Guild] = None):
        self.channel = channel
        self.guild = guild
    
    async def create_thread(self, name: str) -> Optional[discord.Thread]:
        """Create a thread in the channel."""
        if not self.guild:
            return None
        
        try:
            return await self.channel.create_thread(
                name=name, 
                type=discord.ChannelType.public_thread
            )
        except Exception:
            return None


def create_context_from_message(message: discord.Message) -> CommandContext:
    """Create CommandContext from a Discord message."""
    return CommandContext(
        user_id=message.author.id,
        user_name=str(message.author),
        channel_id=message.channel.id,
        channel_name=getattr(message.channel, 'name', None),
        guild_id=message.guild.id if message.guild else None,
        guild_name=message.guild.name if message.guild else None,
        content=message.content,
        source_type='message'
    )


def create_context_from_interaction(interaction: discord.Interaction, content: str) -> CommandContext:
    """Create CommandContext from a Discord interaction."""
    return CommandContext(
        user_id=interaction.user.id,
        user_name=str(interaction.user),
        channel_id=interaction.channel.id,
        channel_name=getattr(interaction.channel, 'name', None),
        guild_id=interaction.guild.id if interaction.guild else None,
        guild_name=interaction.guild.name if interaction.guild else None,
        content=content,
        source_type='interaction'
    )


def create_response_sender(source: Union[discord.Message, discord.Interaction]) -> ResponseSender:
    """Create appropriate response sender based on command source."""
    if isinstance(source, discord.Message):
        return MessageResponseSender(source.channel)
    elif isinstance(source, discord.Interaction):
        return InteractionResponseSender(source)
    else:
        raise ValueError(f"Unsupported source type: {type(source)}")


def create_thread_manager(source: Union[discord.Message, discord.Interaction]) -> ThreadManager:
    """Create thread manager based on command source."""
    if isinstance(source, (discord.Message, discord.Interaction)):
        return ThreadManager(source.channel, source.guild)
    else:
        raise ValueError(f"Unsupported source type: {type(source)}")


async def _store_dm_responses(summary_parts: list[str], context: CommandContext, bot_user=None) -> None:
    """Store bot responses in database for DM conversations."""
    try:
        import database
        from datetime import datetime

        # Get bot user ID from the provided bot_user or use a default
        bot_user_id = str(bot_user.id) if bot_user else "0"
        bot_user_name = str(bot_user) if bot_user else "TechFren Bot"

        for i, part in enumerate(summary_parts):
            # Generate a unique message ID for each part
            message_id = f"bot_dm_response_{context.user_id}_{datetime.now().timestamp()}_{i}"

            database.store_message(
                message_id=message_id,
                author_id=bot_user_id,
                author_name=bot_user_name,
                channel_id=str(context.channel_id),
                channel_name=context.channel_name or "DM",
                content=part,
                created_at=datetime.now(),
                guild_id=None,  # DMs don't have guilds
                guild_name=None,
                is_bot=True,
                is_command=False,
                command_type=None
            )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to store DM response in database: {str(e)}")


async def handle_summary_command(
    context: CommandContext,
    response_sender: ResponseSender,
    thread_manager: ThreadManager,
    hours: int = 24,
    bot_user=None
) -> None:
    """
    Core logic for summary commands, abstracted from Discord-specific handling.
    
    Args:
        context: Command execution context
        response_sender: Interface for sending responses
        thread_manager: Interface for thread creation
        hours: Number of hours to summarize (default 24)
    """
    from datetime import datetime, timezone
    from rate_limiter import check_rate_limit
    from database import check_database_connection
    from llm_handler import call_llm_for_summary
    from message_utils import split_long_message
    import database
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Rate limiting
    is_limited, wait_time, reason = check_rate_limit(str(context.user_id))
    if is_limited:
        error_msg = f"Please wait {wait_time:.1f} seconds before making another request." if reason == "cooldown" \
            else f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
        await response_sender.send(error_msg, ephemeral=True)
        logger.info(f"Rate limited user {context.user_name} ({reason}): wait time {wait_time:.1f}s")
        return
    
    # Send initial response
    await response_sender.send("Generating channel summary, please wait... This may take a moment.")
    
    try:
        today = datetime.now(timezone.utc)
        channel_id_str = str(context.channel_id)
        channel_name_str = context.channel_name or "DM"
        
        # Database checks
        if not database:
            logger.error("Database module not available in handle_summary_command")
            await response_sender.send("Sorry, a critical error occurred (database unavailable). Please try again later.", ephemeral=True)
            return
        
        if not check_database_connection():
            logger.error("Database connection check failed in handle_summary_command")
            await response_sender.send("Sorry, a database connection error occurred. Please try again later.", ephemeral=True)
            return
        
        # Get messages for the specified time period
        messages_for_summary = database.get_channel_messages_for_hours(
            channel_id_str,
            today,
            hours
        )
        
        logger.info(f"Found {len(messages_for_summary)} messages for summary in channel {channel_name_str} (past {hours} hours)")
        
        if not messages_for_summary:
            logger.info(f"No messages found for summary command in channel {channel_name_str} for the past {hours} hours")
            await response_sender.send(f"No messages found in this channel for the past {hours} hours." if hours != 24 else "No messages found in this channel for the past 24 hours.", ephemeral=True)
            return
        
        # Generate summary
        summary = await call_llm_for_summary(messages_for_summary, channel_name_str, today)
        summary_parts = await split_long_message(summary)
        
        # Create thread if in a guild
        thread = None
        if context.guild_id:
            thread_name = f"Summary - {channel_name_str} - {today.strftime('%Y-%m-%d')}"
            thread = await thread_manager.create_thread(thread_name)
        
        # Send summary
        if thread:
            thread_sender = MessageResponseSender(thread)
            await thread_sender.send_in_parts(summary_parts)
            await response_sender.send(f"Summary posted in thread: {thread.mention}")
        else:
            await response_sender.send_in_parts(summary_parts)

            # Store bot responses in database for DMs
            if context.source_type == 'message' and not context.guild_id:
                await _store_dm_responses(summary_parts, context, bot_user)
        
        # Store summary in database
        try:
            # Extract unique users from messages for active_users list
            active_users = list(set(msg.get('author_name', 'Unknown') for msg in messages_for_summary if not msg.get('is_bot', False)))

            database.store_channel_summary(
                channel_id=channel_id_str,
                channel_name=channel_name_str,
                date=today,
                summary_text=summary,
                message_count=len(messages_for_summary),
                active_users=active_users,
                guild_id=str(context.guild_id) if context.guild_id else None,
                guild_name=context.guild_name,
                metadata={"hours_summarized": hours, "requested_by": str(context.user_id)}
            )
        except Exception as e:
            logger.error(f"Failed to store summary in database: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error in handle_summary_command: {str(e)}", exc_info=True)
        await response_sender.send("Sorry, an error occurred while generating the summary. Please try again later.", ephemeral=True)
