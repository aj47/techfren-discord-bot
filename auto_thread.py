"""
Automatic thread creation for extended conversations.

When two users reply back-and-forth N times consecutively in configured channels,
their conversation is automatically moved to a thread to keep the main channel tidy.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

import discord

import config

logger = logging.getLogger('discord_bot.auto_thread')


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class ConversationChain:
    """Tracks a back-and-forth conversation between exactly 2 users."""
    user_a_id: str
    user_b_id: str
    message_ids: List[str] = field(default_factory=list)
    last_replier_id: str = ""
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    first_message_id: str = ""

    def get_users(self) -> Set[str]:
        """Return the set of user IDs in this conversation."""
        return {self.user_a_id, self.user_b_id}

    def is_valid_next_reply(self, author_id: str) -> bool:
        """Check if author_id is the expected next replier (alternating pattern)."""
        if not self.last_replier_id:
            return author_id in self.get_users()
        # Must be one of the two users AND different from last replier
        return author_id in self.get_users() and author_id != self.last_replier_id


# =============================================================================
# Conversation Tracker
# =============================================================================

class ConversationTracker:
    """
    In-memory tracker for ongoing conversations.

    Tracking Strategy:
    - Key conversations by the root message ID (first message in chain)
    - When a reply comes in, find if it's replying to a message in an active chain
    - Maintain a reverse lookup: message_id -> chain_root_id
    """

    def __init__(self, threshold: int = 5, ttl_minutes: int = 60):
        self.threshold = threshold
        self.ttl_minutes = ttl_minutes

        # channel_id -> {root_message_id -> ConversationChain}
        self._chains: Dict[str, Dict[str, ConversationChain]] = {}

        # message_id -> (channel_id, root_message_id) for fast lookup
        self._message_to_chain: Dict[str, Tuple[str, str]] = {}

        # Track conversations being processed to prevent races
        self._processing: Set[str] = set()

    def _cleanup_expired(self, channel_id: str) -> None:
        """Remove expired conversation chains."""
        if channel_id not in self._chains:
            return

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.ttl_minutes)

        expired_roots = [
            root_id for root_id, chain in self._chains[channel_id].items()
            if chain.last_activity < cutoff
        ]

        for root_id in expired_roots:
            chain = self._chains[channel_id].pop(root_id)
            for msg_id in chain.message_ids:
                self._message_to_chain.pop(msg_id, None)
            logger.debug(f"Expired conversation chain {root_id} in channel {channel_id}")

    def track_reply(
        self,
        channel_id: str,
        message_id: str,
        author_id: str,
        reply_to_message_id: str
    ) -> Optional[ConversationChain]:
        """
        Track a reply message and return the chain if threshold is met.

        Returns:
            ConversationChain if threshold reached, None otherwise
        """
        # Periodic cleanup
        self._cleanup_expired(channel_id)

        # Initialize channel dict if needed
        if channel_id not in self._chains:
            self._chains[channel_id] = {}

        # Check if the replied-to message is in an existing chain
        if reply_to_message_id in self._message_to_chain:
            chain_channel, root_id = self._message_to_chain[reply_to_message_id]

            if chain_channel == channel_id and root_id in self._chains[channel_id]:
                chain = self._chains[channel_id][root_id]

                # Skip if this chain is already being processed
                if f"{channel_id}:{root_id}" in self._processing:
                    return None

                # Verify this is a valid alternating reply
                if chain.is_valid_next_reply(author_id):
                    # Add to chain
                    chain.message_ids.append(message_id)
                    chain.last_replier_id = author_id
                    chain.last_activity = datetime.now(timezone.utc)
                    self._message_to_chain[message_id] = (channel_id, root_id)

                    logger.debug(
                        f"Extended chain {root_id}: {len(chain.message_ids)} messages, "
                        f"users {chain.user_a_id} <-> {chain.user_b_id}"
                    )

                    # Check threshold
                    if len(chain.message_ids) >= self.threshold:
                        return chain
                    return None
                else:
                    # Someone else replied or same person replied twice
                    # Don't remove chain - let it expire naturally or continue if valid reply comes
                    logger.debug(
                        f"Chain {root_id} not extended: author {author_id} "
                        f"doesn't match alternating pattern"
                    )
                    return None

        # This reply is not to a tracked message - will be handled by handler
        # which may start a new chain
        return None

    def start_new_chain(
        self,
        channel_id: str,
        original_message_id: str,
        original_author_id: str,
        reply_message_id: str,
        reply_author_id: str
    ) -> None:
        """Start tracking a new conversation chain."""
        if channel_id not in self._chains:
            self._chains[channel_id] = {}

        # Don't start if original message is already in a chain
        if original_message_id in self._message_to_chain:
            return

        chain = ConversationChain(
            user_a_id=original_author_id,
            user_b_id=reply_author_id,
            message_ids=[original_message_id, reply_message_id],
            last_replier_id=reply_author_id,
            first_message_id=original_message_id
        )

        self._chains[channel_id][original_message_id] = chain
        self._message_to_chain[original_message_id] = (channel_id, original_message_id)
        self._message_to_chain[reply_message_id] = (channel_id, original_message_id)

        logger.debug(
            f"Started new chain {original_message_id}: "
            f"{original_author_id} <-> {reply_author_id}"
        )

    def mark_processing(self, channel_id: str, root_id: str) -> bool:
        """Mark a chain as being processed. Returns False if already processing."""
        key = f"{channel_id}:{root_id}"
        if key in self._processing:
            return False
        self._processing.add(key)
        return True

    def unmark_processing(self, channel_id: str, root_id: str) -> None:
        """Remove processing mark."""
        key = f"{channel_id}:{root_id}"
        self._processing.discard(key)

    def remove_chain(self, channel_id: str, root_id: str) -> None:
        """Remove a processed chain."""
        if channel_id in self._chains and root_id in self._chains[channel_id]:
            chain = self._chains[channel_id].pop(root_id)
            for msg_id in chain.message_ids:
                self._message_to_chain.pop(msg_id, None)
        self.unmark_processing(channel_id, root_id)


# =============================================================================
# Auto Thread Handler
# =============================================================================

class AutoThreadHandler:
    """Handles automatic thread creation for extended conversations."""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.tracker = ConversationTracker(
            threshold=getattr(config, 'AUTO_THREAD_REPLY_THRESHOLD', 5),
            ttl_minutes=getattr(config, 'AUTO_THREAD_TTL_MINUTES', 60)
        )

    def is_enabled_channel(self, channel_id: str) -> bool:
        """Check if auto-threading is enabled for this channel."""
        channel_ids = getattr(config, 'auto_thread_channel_ids', None)
        if not channel_ids:
            return False
        return channel_id in channel_ids

    async def handle_message(self, message: discord.Message) -> bool:
        """
        Process a message for auto-threading.

        Returns True if a thread was created, False otherwise.
        """
        # Skip bots
        if message.author.bot:
            return False

        # Skip messages in threads (only track main channel)
        if isinstance(message.channel, discord.Thread):
            return False

        # Check if channel is enabled
        channel_id = str(message.channel.id)
        if not self.is_enabled_channel(channel_id):
            return False

        # Skip if not a reply
        if not message.reference or not message.reference.message_id:
            return False

        reply_to_id = str(message.reference.message_id)
        author_id = str(message.author.id)
        message_id = str(message.id)

        # Try to extend existing chain
        chain = self.tracker.track_reply(
            channel_id=channel_id,
            message_id=message_id,
            author_id=author_id,
            reply_to_message_id=reply_to_id
        )

        if chain:
            # Threshold reached - create thread
            return await self._create_thread_for_chain(message.channel, chain)

        # Check if this starts a new chain (reply to a message not in any chain)
        if reply_to_id not in self.tracker._message_to_chain:
            try:
                ref_message = await self._fetch_referenced_message(message)
                if ref_message and not ref_message.author.bot:
                    ref_author_id = str(ref_message.author.id)
                    ref_message_id = str(ref_message.id)

                    # Only start chain if different users
                    if ref_author_id != author_id:
                        self.tracker.start_new_chain(
                            channel_id=channel_id,
                            original_message_id=ref_message_id,
                            original_author_id=ref_author_id,
                            reply_message_id=message_id,
                            reply_author_id=author_id
                        )
            except Exception as e:
                logger.warning(f"Failed to fetch referenced message: {e}")

        return False

    async def _fetch_referenced_message(
        self,
        message: discord.Message
    ) -> Optional[discord.Message]:
        """Fetch the message this is replying to."""
        if not message.reference or not message.reference.message_id:
            return None

        # Try cache first
        if message.reference.cached_message:
            return message.reference.cached_message

        try:
            return await message.channel.fetch_message(message.reference.message_id)
        except (discord.NotFound, discord.HTTPException) as e:
            logger.debug(f"Could not fetch referenced message: {e}")
            return None

    async def _create_thread_for_chain(
        self,
        channel: discord.TextChannel,
        chain: ConversationChain
    ) -> bool:
        """Create a thread and move the conversation into it."""
        channel_id = str(channel.id)
        root_id = chain.first_message_id

        # Prevent concurrent processing
        if not self.tracker.mark_processing(channel_id, root_id):
            logger.debug(f"Chain {root_id} already being processed")
            return False

        try:
            # Fetch all messages in the chain
            messages: List[discord.Message] = []
            for msg_id in chain.message_ids:
                try:
                    msg = await channel.fetch_message(int(msg_id))
                    messages.append(msg)
                except discord.NotFound:
                    logger.warning(f"Message {msg_id} not found, skipping")
                except discord.HTTPException as e:
                    logger.warning(f"Failed to fetch message {msg_id}: {e}")

            if len(messages) < 2:
                logger.warning("Not enough messages to create thread")
                self.tracker.unmark_processing(channel_id, root_id)
                return False

            # Get participant names for thread title
            user_a = messages[0].author
            user_b = next((m.author for m in messages if m.author.id != user_a.id), None)

            if not user_b:
                logger.warning("Could not find second participant")
                self.tracker.unmark_processing(channel_id, root_id)
                return False

            # Create a standalone thread in the channel (not attached to a message)
            # This allows us to delete ALL original messages from the main channel
            thread_name = f"Conversation: {user_a.display_name} & {user_b.display_name}"
            thread_name = thread_name[:100]  # Discord thread name limit

            try:
                thread = await channel.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=1440  # 24 hours
                )
            except discord.HTTPException as e:
                logger.error(f"Failed to create thread: {e}")
                self.tracker.unmark_processing(channel_id, root_id)
                return False

            # Send introduction message
            intro = (
                f"This conversation between {user_a.mention} and {user_b.mention} "
                f"has been moved to this thread to keep the main channel tidy.\n\n"
                f"**Conversation history:**"
            )
            await thread.send(intro)

            # Copy messages to thread with attribution
            for msg in messages:
                formatted = self._format_message_for_thread(msg)
                await thread.send(formatted, allowed_mentions=discord.AllowedMentions.none())
                await asyncio.sleep(0.5)  # Rate limit protection

            # Final message inviting users to continue
            await thread.send(
                f"\n---\n{user_a.mention} {user_b.mention} "
                f"Feel free to continue your conversation here!"
            )

            # Delete original messages from main channel
            deleted_count = 0
            for msg in messages:
                try:
                    await msg.delete()
                    deleted_count += 1
                    await asyncio.sleep(0.5)  # Rate limit protection
                except discord.NotFound:
                    pass  # Already deleted
                except discord.Forbidden:
                    logger.warning(f"No permission to delete message {msg.id}")
                except discord.HTTPException as e:
                    logger.warning(f"Failed to delete message {msg.id}: {e}")

            logger.info(
                f"Created thread '{thread_name}' with {len(messages)} messages, "
                f"deleted {deleted_count} from channel"
            )

            # Clean up tracking
            self.tracker.remove_chain(channel_id, root_id)
            return True

        except Exception as e:
            logger.error(f"Error creating thread for chain {root_id}: {e}", exc_info=True)
            self.tracker.unmark_processing(channel_id, root_id)
            return False

    def _format_message_for_thread(self, message: discord.Message) -> str:
        """Format a message for reposting in the thread."""
        timestamp = message.created_at.strftime("%H:%M")
        author = message.author.display_name
        content = message.content or "[No text content]"

        # Handle attachments
        attachments_text = ""
        if message.attachments:
            attachment_urls = [a.url for a in message.attachments]
            attachments_text = "\n" + "\n".join(attachment_urls)

        # Handle embeds (simplified - just note their presence)
        embeds_text = ""
        if message.embeds:
            for embed in message.embeds:
                if embed.url:
                    embeds_text += f"\n[Embed: {embed.url}]"

        return f"**{author}** ({timestamp}):\n{content}{attachments_text}{embeds_text}"


# =============================================================================
# Module-level instance (initialized in bot.py)
# =============================================================================

_handler: Optional[AutoThreadHandler] = None


def init_auto_thread(bot: discord.Client) -> AutoThreadHandler:
    """Initialize the auto-thread handler."""
    global _handler
    _handler = AutoThreadHandler(bot)
    logger.info(
        f"Auto-thread handler initialized "
        f"(threshold={_handler.tracker.threshold}, ttl={_handler.tracker.ttl_minutes}min)"
    )
    return _handler


def get_handler() -> Optional[AutoThreadHandler]:
    """Get the initialized handler."""
    return _handler


async def handle_message_for_auto_thread(message: discord.Message) -> bool:
    """Convenience function called from on_message."""
    if _handler:
        return await _handler.handle_message(message)
    return False
