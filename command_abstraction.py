"""
Command abstraction layer to eliminate MockMessage pattern.

This module provides a unified interface for handling both Discord message-based
and interaction-based commands without relying on mocking Discord objects.
"""

from dataclasses import dataclass
from typing import Optional, Union, Protocol, List, Dict
import asyncio
import discord
import logging
import aiohttp
import aiohttp.client_exceptions
import io
from thread_memory import get_thread_context, store_thread_exchange, has_thread_memory


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

    async def send(
        self, content: str, ephemeral: bool = False
    ) -> Optional[discord.Message]:
        """Send a response message."""
        pass

    async def send_in_parts(self, parts: list[str], ephemeral: bool = False) -> None:
        """Send multiple message parts."""
        pass

    async def send_with_charts(
        self, content: str, chart_data: List[Dict], ephemeral: bool = False
    ) -> Optional[discord.Message]:
        """Send a message with chart attachments."""
        pass


class MessageResponseSender:
    """Response sender for regular Discord messages."""

    def __init__(self, channel: discord.TextChannel):
        self.channel = channel
        self.logger = logging.getLogger(__name__)

    async def send(
        self, content: str, ephemeral: bool = False
    ) -> Optional[discord.Message]:
        # `ephemeral` has no meaning for regular messages; we silently ignore it.
        # Allow user mentions but disable everyone/here and role mentions for safety
        allowed_mentions = discord.AllowedMentions(
            everyone=False, roles=False, users=True
        )

        # Check content length and split if necessary
        if len(content) > 2000:
            from message_utils import split_long_message

            parts = await split_long_message(content, max_length=1900)

            # Send first part and return its message object
            first_response = await self.channel.send(
                parts[0], allowed_mentions=allowed_mentions, suppress_embeds=True
            )

            # Send remaining parts
            for part in parts[1:]:
                await self.channel.send(
                    part, allowed_mentions=allowed_mentions, suppress_embeds=True
                )

            return first_response
        else:
            return await self.channel.send(
                content, allowed_mentions=allowed_mentions, suppress_embeds=True
            )

    async def send_in_parts(self, parts: list[str], ephemeral: bool = False) -> None:
        allowed_mentions = discord.AllowedMentions(
            everyone=False, roles=False, users=True
        )
        for part in parts:
            await self.channel.send(
                part, allowed_mentions=allowed_mentions, suppress_embeds=True
            )

    async def _send_with_retry(self, content: str, files: List[discord.File], allowed_mentions, max_retries: int = 3):
        """Send message with retry logic for SSL errors."""
        for attempt in range(max_retries):
            try:
                return await self.channel.send(
                    content,
                    files=files,
                    allowed_mentions=allowed_mentions,
                    suppress_embeds=True,
                )
            except (aiohttp.client_exceptions.ClientOSError, aiohttp.client_exceptions.ClientError) as e:
                if "SSL" in str(e) or "ssl" in str(e).lower():
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        self.logger.warning(
                            "SSL error sending message with charts (attempt %d/%d): %s. Retrying in %ds...",
                            attempt + 1,
                            max_retries,
                            e,
                            wait_time
                        )
                        await asyncio.sleep(wait_time)
                        # Recreate file objects since they may have been consumed
                        files = [discord.File(io.BytesIO(f.fp.getvalue()), filename=f.filename) for f in files]
                    else:
                        self.logger.error(
                            "SSL error persists after %d attempts: %s",
                            max_retries,
                            e,
                            exc_info=True
                        )
                        raise
                else:
                    # Not an SSL error, re-raise immediately
                    raise

    async def send_with_charts(
        self, content: str, chart_data: List[Dict], ephemeral: bool = False
    ) -> Optional[discord.Message]:
        """Send a message with chart image attachments with SSL error retry logic."""
        allowed_mentions = discord.AllowedMentions(
            everyone=False, roles=False, users=True
        )

        try:
            # Download chart images and create Discord file objects
            files = await self._download_chart_files(chart_data)

            if files:
                # Check content length and split if necessary
                if len(content) > 1900:  # Leave room for chart placeholders
                    # Split content into parts and send charts with first part
                    from message_utils import split_long_message

                    parts = await split_long_message(content, max_length=1900)

                    # Send first part with charts (with retry logic)
                    first_response = await self._send_with_retry(
                        parts[0],
                        files,
                        allowed_mentions
                    )

                    # Send remaining parts without charts
                    for part in parts[1:]:
                        await self.channel.send(
                            part,
                            allowed_mentions=allowed_mentions,
                            suppress_embeds=True,
                        )

                    return first_response
                else:
                    # Content is short enough, send with charts (with retry logic)
                    return await self._send_with_retry(
                        content,
                        files,
                        allowed_mentions
                    )
            else:
                # Fallback to regular send if no files downloaded successfully
                self.logger.warning(
                    "No chart files downloaded, sending message without attachments"
                )
                return await self.send(content, ephemeral)

        except discord.HTTPException as e:
            self.logger.error(
                "Discord HTTP error sending message with charts: %s",
                e,
                exc_info=True,
            )
            raise  # Re-raise to propagate error (no fallback)
        except (aiohttp.client_exceptions.ClientOSError, aiohttp.client_exceptions.ClientError) as e:
            self.logger.error(
                "Network/SSL error sending message with charts after retries: %s",
                e,
                exc_info=True
            )
            raise  # Re-raise to propagate error (no fallback)
        except Exception as e:
            self.logger.error("Error sending message with charts: %s", e, exc_info=True)
            raise  # Re-raise to propagate error (no fallback)

    async def _download_chart_files(self, chart_data: List[Dict]) -> List[discord.File]:
        """Create Discord File objects from chart file data."""
        files = []

        for idx, chart in enumerate(chart_data):
            try:
                chart_file = chart.get("file")
                chart_type = chart.get("type", "chart")

                if not chart_file:
                    self.logger.warning("Chart %s has no file data, skipping", idx + 1)
                    continue

                # Create a new BytesIO object to avoid seek issues
                image_file = io.BytesIO(chart_file.getvalue())
                filename = f"{chart_type}_{idx + 1}.png"

                # Create Discord file object
                discord_file = discord.File(image_file, filename=filename)
                files.append(discord_file)

                self.logger.info("Prepared chart %s: %s", idx + 1, chart_type)

            except Exception as e:
                self.logger.error(
                    f"Error preparing chart {idx + 1}: {e}", exc_info=True
                )
                continue

        return files


class InteractionResponseSender:
    """Response sender for Discord slash command interactions."""

    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.logger = logging.getLogger(__name__)

    async def send(
        self, content: str, ephemeral: bool = False
    ) -> Optional[discord.Message]:
        allowed_mentions = discord.AllowedMentions(
            everyone=False, roles=False, users=True
        )

        # Check content length and split if necessary
        if len(content) > 2000:
            from message_utils import split_long_message

            parts = await split_long_message(content, max_length=1900)

            # Send first part and return its message object
            first_message = await self.interaction.followup.send(
                parts[0],
                ephemeral=ephemeral,
                allowed_mentions=allowed_mentions,
                suppress_embeds=True,
                wait=True,
            )

            # Send remaining parts
            for part in parts[1:]:
                await self.interaction.followup.send(
                    part,
                    ephemeral=ephemeral,
                    allowed_mentions=allowed_mentions,
                    suppress_embeds=True,
                )

            return first_message if not ephemeral else None
        else:
            message = await self.interaction.followup.send(
                content,
                ephemeral=ephemeral,
                allowed_mentions=allowed_mentions,
                suppress_embeds=True,
                wait=True,
            )
            return (
                message if not ephemeral else None
            )  # Can't create threads from ephemeral messages

    async def send_in_parts(self, parts: list[str], ephemeral: bool = False) -> None:
        allowed_mentions = discord.AllowedMentions(
            everyone=False, roles=False, users=True
        )
        for part in parts:
            await self.interaction.followup.send(
                part,
                ephemeral=ephemeral,
                allowed_mentions=allowed_mentions,
                suppress_embeds=True,
            )

    async def _send_with_retry(self, content: str, files: List[discord.File], allowed_mentions, ephemeral: bool, max_retries: int = 3):
        """Send interaction followup with retry logic for SSL errors."""
        for attempt in range(max_retries):
            try:
                return await self.interaction.followup.send(
                    content,
                    files=files,
                    ephemeral=ephemeral,
                    allowed_mentions=allowed_mentions,
                    suppress_embeds=True,
                    wait=True,
                )
            except (aiohttp.client_exceptions.ClientOSError, aiohttp.client_exceptions.ClientError) as e:
                if "SSL" in str(e) or "ssl" in str(e).lower():
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        self.logger.warning(
                            "SSL error sending interaction with charts (attempt %d/%d): %s. Retrying in %ds...",
                            attempt + 1,
                            max_retries,
                            e,
                            wait_time
                        )
                        await asyncio.sleep(wait_time)
                        # Recreate file objects since they may have been consumed
                        files = [discord.File(io.BytesIO(f.fp.getvalue()), filename=f.filename) for f in files]
                    else:
                        self.logger.error(
                            "SSL error persists after %d attempts: %s",
                            max_retries,
                            e,
                            exc_info=True
                        )
                        raise
                else:
                    # Not an SSL error, re-raise immediately
                    raise

    async def send_with_charts(
        self, content: str, chart_data: List[Dict], ephemeral: bool = False
    ) -> Optional[discord.Message]:
        """Send a message with chart image attachments with SSL error retry logic."""
        allowed_mentions = discord.AllowedMentions(
            everyone=False, roles=False, users=True
        )

        try:
            # Download chart images and create Discord file objects
            files = await self._download_chart_files(chart_data)

            if files:
                # Check content length and split if necessary
                if len(content) > 1900:  # Leave room for chart placeholders
                    # Split content into parts and send charts with first part
                    from message_utils import split_long_message

                    parts = await split_long_message(content, max_length=1900)

                    # Send first part with charts (with retry logic)
                    first_message = await self._send_with_retry(
                        parts[0],
                        files,
                        allowed_mentions,
                        ephemeral
                    )

                    # Send remaining parts without charts
                    for part in parts[1:]:
                        await self.interaction.followup.send(
                            part,
                            ephemeral=ephemeral,
                            allowed_mentions=allowed_mentions,
                            suppress_embeds=True,
                        )

                    return first_message if not ephemeral else None
                else:
                    # Content is short enough, send with charts (with retry logic)
                    message = await self._send_with_retry(
                        content,
                        files,
                        allowed_mentions,
                        ephemeral
                    )
                    return message if not ephemeral else None
            else:
                # Fallback to regular send if no files downloaded successfully
                self.logger.warning(
                    "No chart files downloaded, sending message without attachments"
                )
                return await self.send(content, ephemeral)

        except discord.HTTPException as e:
            self.logger.error(
                "Discord HTTP error sending interaction with charts: %s",
                e,
                exc_info=True,
            )
            raise  # Re-raise to propagate error (no fallback)
        except (aiohttp.client_exceptions.ClientOSError, aiohttp.client_exceptions.ClientError) as e:
            self.logger.error(
                "Network/SSL error sending interaction with charts after retries: %s",
                e,
                exc_info=True
            )
            raise  # Re-raise to propagate error (no fallback)
        except Exception as e:
            self.logger.error(
                "Error sending interaction response with charts: %s", exc_info=True
            )
            raise  # Re-raise to propagate error (no fallback)

    async def _download_chart_files(self, chart_data: List[Dict]) -> List[discord.File]:
        """Create Discord File objects from chart file data."""
        files = []

        for idx, chart in enumerate(chart_data):
            try:
                chart_file = chart.get("file")
                chart_type = chart.get("type", "chart")

                if not chart_file:
                    self.logger.warning("Chart %s has no file data, skipping", idx + 1)
                    continue

                # Create a new BytesIO object to avoid seek issues
                image_file = io.BytesIO(chart_file.getvalue())
                filename = f"{chart_type}_{idx + 1}.png"

                # Create Discord file object
                discord_file = discord.File(image_file, filename=filename)
                files.append(discord_file)

                self.logger.info("Prepared chart %s: %s", idx + 1, chart_type)

            except Exception as e:
                self.logger.error(
                    f"Error preparing chart {idx + 1}: {e}", exc_info=True
                )
                continue

        return files


class ThreadManager:
    """Handles thread creation for both message and interaction contexts."""

    # Class-level lock and cache to prevent duplicate thread creation across all instances
    _thread_creation_lock = asyncio.Lock()
    _created_threads = {}  # message_id -> thread_id mapping
    _MAX_CACHE_SIZE = 500

    def __init__(self, channel, guild: Optional[discord.Guild] = None):
        self.channel = channel
        self.guild = guild

    def _can_create_threads(self) -> bool:
        """Check if threads can be created in this channel."""
        # Threads are only supported in guild text channels and news channels
        if not self.guild:
            return False

        # Check if channel supports threads
        if isinstance(self.channel, discord.TextChannel):
            return True

        # Try to check for NewsChannel if it exists in this discord.py version
        try:
            if hasattr(discord, "NewsChannel") and isinstance(
                self.channel, discord.NewsChannel
            ):
                return True
        except AttributeError:
            pass

        # DMs, voice channels, categories, etc. don't support threads
        return False

    def _get_channel_type_description(self) -> str:
        """Get a user-friendly description of the channel type."""
        if isinstance(self.channel, discord.DMChannel):
            return "DM"
        elif isinstance(self.channel, discord.GroupChannel):
            return "Group DM"
        elif isinstance(self.channel, discord.VoiceChannel):
            return "Voice Channel"
        elif isinstance(self.channel, discord.CategoryChannel):
            return "Category"
        elif isinstance(self.channel, discord.Thread):
            return "Thread"
        elif isinstance(self.channel, discord.TextChannel):
            return "TextChannel"
        else:
            return type(self.channel).__name__

    async def create_thread(self, name: str) -> Optional[discord.Thread]:
        """Create a thread in the channel."""
        if not self._can_create_threads():
            logger = logging.getLogger(__name__)
            channel_desc = self._get_channel_type_description()
            if isinstance(self.channel, discord.DMChannel):
                logger.debug("Thread creation not supported in %ss", channel_desc)
            else:
                logger.info(
                    f"Thread creation not supported in {channel_desc}, skipping thread creation"  # noqa: E501
                )
            return None

        try:
            return await self.channel.create_thread(
                name=name, type=discord.ChannelType.public_thread
            )
        except discord.Forbidden as e:
            logger = logging.getLogger(__name__)
            logger.warning("Insufficient permissions to create thread '%s': %s", name, e)
            return None
        except discord.HTTPException as e:
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to create thread '{name}': HTTP {e.status} - {e.text}"
            )
            return None
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(
                f"Unexpected error creating thread '{name}': {str(e)}", exc_info=True
            )
            return None

    async def _handle_missing_guild_info(
        self, message: discord.Message, name: str
    ) -> Optional[discord.Thread]:
        """Handle case where message lacks guild info."""
        logger = logging.getLogger(__name__)
        logger.info(
            f"Message lacks guild info, fetching message with guild info for thread creation: '{name}'"  # noqa: E501
        )
        try:
            fetched_message = await self.channel.fetch_message(message.id)
            return await fetched_message.create_thread(name=name)
        except (discord.HTTPException, discord.NotFound) as fetch_error:
            logger.warning(
                f"Failed to fetch message {
                    message.id} for thread creation: {fetch_error}"
            )
            return await self.create_thread(name)

    async def _handle_value_error(
        self, e: ValueError, message: discord.Message, name: str
    ) -> Optional[discord.Thread]:
        """Handle ValueError during thread creation."""
        logger = logging.getLogger(__name__)
        if "guild info" in str(e):
            logger.info(
                f"Message lacks guild info, attempting to fetch with proper guild info: {e}"  # noqa: E501
            )
            return await self._handle_missing_guild_info(message, name)
        else:
            logger.error("ValueError creating thread from message '%s': %s", name, e)
            return None

    async def _handle_http_exception(
        self, e: discord.HTTPException, name: str, message: Optional[discord.Message] = None
    ) -> Optional[discord.Thread]:
        """Handle HTTPException during thread creation."""
        logger = logging.getLogger(__name__)
        if e.status == 400 and "thread has already been created" in str(e.text).lower():
            logger.info(
                "Message already has a thread, attempting to fetch it "
                "instead of creating new one"
            )
            # If we have the message, try to fetch its existing thread
            if message:
                try:
                    existing_thread = await message.fetch_thread()
                    if existing_thread:
                        logger.info("Successfully fetched existing thread: '%s'", existing_thread.name)
                        return existing_thread
                except discord.NotFound:
                    logger.warning("Could not find existing thread despite error message")
                except Exception as fetch_error:
                    logger.warning("Error fetching existing thread: %s", fetch_error)

            # Fallback: return None to avoid creating duplicate standalone threads
            logger.warning("Cannot create or fetch thread, returning None")
            return None
        elif e.status == 400 and "Cannot execute action on this channel type" in str(
            e.text
        ):
            channel_desc = self._get_channel_type_description()
            logger.info(
                f"Thread creation not supported in {channel_desc}, this is expected behavior"  # noqa: E501
            )
            return None
        elif e.status == 400:
            logger.info(
                f"Cannot create thread from message '{name}': HTTP {e.status} - {e.text}"  # noqa: E501
            )
            return None
        else:
            logger.warning(
                f"Failed to create thread from message '{name}': HTTP {e.status} - {e.text}"  # noqa: E501
            )
            return None

    async def create_thread_from_message(
        self, message: discord.Message, name: str
    ) -> Optional[discord.Thread]:
        """Create a thread from an existing message with duplicate prevention."""
        logger = logging.getLogger(__name__)

        if not self._can_create_threads():
            channel_desc = self._get_channel_type_description()
            if isinstance(self.channel, discord.DMChannel):
                logger.debug("Thread creation not supported in %ss", channel_desc)
            else:
                logger.info(
                    f"Thread creation not supported in {channel_desc}, falling back to channel response"  # noqa: E501
                )
            return None

        # Use class-level lock to prevent duplicate thread creation across all instances
        async with ThreadManager._thread_creation_lock:
            message_id = str(message.id)

            # Check if we already created a thread for this message
            if message_id in ThreadManager._created_threads:
                thread_id = ThreadManager._created_threads[message_id]
                logger.warning(
                    "DUPLICATE THREAD CREATION PREVENTED: Message %s already has thread %s",
                    message_id,
                    thread_id
                )
                # Try to fetch the existing thread
                try:
                    thread = await message.guild.fetch_channel(int(thread_id))
                    if isinstance(thread, discord.Thread):
                        logger.info("Successfully retrieved existing thread %s for message %s", thread_id, message_id)
                        return thread
                except Exception as e:
                    logger.warning("Could not fetch cached thread %s: %s", thread_id, e)
                    # Remove stale entry
                    del ThreadManager._created_threads[message_id]

            try:
                # Check if the message has guild info (required for thread creation)
                if not hasattr(message, "guild") or message.guild is None:
                    return await self._handle_missing_guild_info(message, name)

                # Check if this message already has a thread (cache check)
                if hasattr(message, 'thread') and message.thread is not None:
                    logger.info("Message %s already has thread '%s' (from cache), reusing it", message.id, message.thread.name)
                    # Cache this thread
                    ThreadManager._created_threads[message_id] = str(message.thread.id)
                    return message.thread

                # Try to fetch thread from API (handles case where Discord auto-created one)
                try:
                    existing_thread = await message.fetch_thread()
                    if existing_thread:
                        logger.info("Message %s already has thread '%s' (from API), reusing it", message.id, existing_thread.name)
                        # Cache this thread
                        ThreadManager._created_threads[message_id] = str(existing_thread.id)
                        return existing_thread
                except discord.NotFound:
                    # No thread exists, we can create one
                    pass
                except Exception as fetch_error:
                    logger.debug("Could not fetch existing thread for message %s: %s", message.id, fetch_error)

                logger.debug("Creating new thread '%s' from message %s", name, message.id)
                try:
                    thread = await message.create_thread(name=name)
                    logger.info("Successfully created thread '%s' (ID: %s) from message %s", name, thread.id, message.id)

                    # Cache the newly created thread
                    ThreadManager._created_threads[message_id] = str(thread.id)

                    # Maintain cache size limit
                    if len(ThreadManager._created_threads) > ThreadManager._MAX_CACHE_SIZE:
                        # Remove oldest half of entries
                        items_to_remove = list(ThreadManager._created_threads.keys())[:ThreadManager._MAX_CACHE_SIZE // 2]
                        for key in items_to_remove:
                            del ThreadManager._created_threads[key]
                        logger.debug("Cleaned thread cache, removed %d old entries", len(items_to_remove))

                    return thread
                except discord.HTTPException as create_error:
                    # If thread creation fails, it might be because Discord just created one
                    if "already has a thread" in str(create_error).lower():
                        logger.info("Thread creation failed - message %s already has a thread, fetching it", message.id)
                        try:
                            existing_thread = await message.fetch_thread()
                            # Cache this thread
                            ThreadManager._created_threads[message_id] = str(existing_thread.id)
                            return existing_thread
                        except Exception:
                            pass
                    raise  # Re-raise if it's a different error
            except ValueError as e:
                return await self._handle_value_error(e, message, name)
            except discord.Forbidden as e:
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Insufficient permissions to create thread from message '{name}': {e}"
                )
                return None
            except discord.HTTPException as e:
                return await self._handle_http_exception(e, name, message)
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(
                    f"Unexpected error creating thread from message '{name}': {str(e)}",
                    exc_info=True,
                )
                return None


def create_context_from_message(message: discord.Message) -> CommandContext:
    """Create a CommandContext from a Discord message."""
    # Check if we're in a thread and add thread_id if so
    thread_id = None
    if hasattr(message.channel, "parent") and message.channel.parent is not None:
        thread_id = str(message.channel.id)

    context = CommandContext(
        user_id=message.author.id,
        user_name=str(message.author),
        channel_id=message.channel.id,
        channel_name=getattr(message.channel, "name", None),
        guild_id=message.guild.id if message.guild else None,
        guild_name=message.guild.name if message.guild else None,
        content=message.content,
        source_type="message",
    )

    # Add thread_id as a dynamic attribute if we're in a thread
    if thread_id:
        context.thread_id = thread_id

    return context


def create_context_from_interaction(
    interaction: discord.Interaction, content: str
) -> CommandContext:
    """Create a CommandContext from a Discord interaction."""
    # Check if we're in a thread and add thread_id if so
    thread_id = None
    if (
        interaction.channel
        and hasattr(interaction.channel, "parent")
        and interaction.channel.parent is not None
    ):
        thread_id = str(interaction.channel.id)

    context = CommandContext(
        user_id=interaction.user.id,
        user_name=str(interaction.user),
        channel_id=interaction.channel_id,
        channel_name=(
            getattr(interaction.channel, "name", None) if interaction.channel else None
        ),
        guild_id=interaction.guild_id,
        guild_name=interaction.guild.name if interaction.guild else None,
        content=content,
        source_type="interaction",
    )

    # Add thread_id as a dynamic attribute if we're in a thread
    if thread_id:
        context.thread_id = thread_id

    return context


def create_response_sender(
    source: Union[discord.Message, discord.Interaction],
) -> ResponseSender:
    """Create appropriate response sender based on command source."""
    if isinstance(source, discord.Message):
        return MessageResponseSender(source.channel)
    elif isinstance(source, discord.Interaction):
        return InteractionResponseSender(source)
    else:
        raise ValueError(f"Unsupported source type: {type(source)}")


def create_thread_manager(
    source: Union[discord.Message, discord.Interaction],
) -> ThreadManager:
    """Create thread manager based on command source."""
    if isinstance(source, (discord.Message, discord.Interaction)):
        return ThreadManager(source.channel, source.guild)
    else:
        raise ValueError(f"Unsupported source type: {type(source)}")


async def _store_dm_responses(
    summary_parts: list[str],
    context: CommandContext,
    bot_user: Optional[discord.ClientUser] = None,
) -> None:
    """Store bot responses in database for DM conversations."""
    try:
        import database
        from datetime import datetime

        # Get bot user ID from the provided bot_user - raise error if missing
        if bot_user is None:
            raise ValueError("bot_user parameter is required for storing DM responses")

        bot_user_id = str(bot_user.id)
        bot_user_name = str(bot_user)

        # Use transaction for multiple database operations
        messages_to_store = []
        base_timestamp = datetime.now()

        for i, part in enumerate(summary_parts):
            # Generate a unique message ID for each part
            message_id = (
                f"bot_dm_response_{context.user_id}_{base_timestamp.timestamp()}_{i}"
            )

            messages_to_store.append(
                {
                    "message_id": message_id,
                    "author_id": bot_user_id,
                    "author_name": bot_user_name,
                    "channel_id": str(context.channel_id),
                    "channel_name": context.channel_name or "DM",
                    "content": part,
                    "created_at": base_timestamp,
                    "guild_id": None,  # DMs don't have guilds
                    "guild_name": None,
                    "is_bot": True,
                    "is_command": False,
                    "command_type": None,
                }
            )

        # Store all messages in a single transaction
        await database.store_messages_batch(messages_to_store)
    except (ValueError, TypeError) as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error("Invalid parameters for storing DM response: %s", str(e))
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error("Database error storing DM response: %s", str(e), exc_info=True)


async def _validate_summary_inputs(
    context: CommandContext, response_sender: ResponseSender, hours: int
) -> bool:
    """Validate inputs for summary command."""
    import config
    import logging

    logger = logging.getLogger(__name__)

    if not isinstance(hours, int) or hours < 1:
        logger.warning("Invalid hours parameter: %s (must be positive integer)", hours)
        await response_sender.send(
            "Invalid hours parameter. Must be a positive number.", ephemeral=True
        )
        return False

    if hours > config.MAX_SUMMARY_HOURS:
        logger.warning(
            f"Hours parameter {hours} exceeds maximum {config.MAX_SUMMARY_HOURS}"
        )
        error_msg = config.ERROR_MESSAGES["invalid_hours_range"]
        await response_sender.send(error_msg, ephemeral=True)
        return False

    return True


async def _check_rate_limits(
    context: CommandContext, response_sender: ResponseSender
) -> bool:
    """Check rate limits for summary command."""
    from rate_limiter import check_rate_limit
    import config
    import logging

    logger = logging.getLogger(__name__)

    is_limited, wait_time, reason = check_rate_limit(str(context.user_id))
    if is_limited:
        if reason == "cooldown":
            error_msg = config.ERROR_MESSAGES["rate_limit_cooldown"].format(
                wait_time=wait_time
            )
        else:
            error_msg = config.ERROR_MESSAGES["rate_limit_exceeded"].format(
                wait_time=wait_time
            )
        await response_sender.send(error_msg, ephemeral=True)
        logger.info(
            f"Rate limited user {
                context.user_name} ({reason}): wait time {
                wait_time:.1f}s"
        )
        return False

    return True


async def _validate_database_connection(response_sender: ResponseSender) -> bool:
    """Validate database connection for summary command."""
    from database import check_database_connection
    import database
    import config
    import logging

    logger = logging.getLogger(__name__)

    if not database:
        logger.error("Database module not available in handle_summary_command")
        await response_sender.send(
            config.ERROR_MESSAGES["database_unavailable"], ephemeral=True
        )
        return False

    if not check_database_connection():
        logger.error("Database connection check failed in handle_summary_command")
        await response_sender.send(
            config.ERROR_MESSAGES["database_error"], ephemeral=True
        )
        return False

    return True


async def _store_summary_data(
    context: CommandContext,
    full_summary: str,
    messages_for_summary: list,
    hours: int,
    force_charts: bool,
    channel_id_str: str,
    channel_name_str: str,
    today,
):
    """Store summary data in thread memory and database."""
    import database
    import logging

    logger = logging.getLogger(__name__)

    # Store thread context memory if available
    thread_context = await _get_thread_context(context)
    if thread_context and hasattr(context, "thread_id") and context.thread_id:
        try:
            command_description = f"Requested {hours}h summary" + (
                " with charts" if force_charts else ""
            )
            store_thread_exchange(
                thread_id=context.thread_id,
                user_id=str(context.user_id),
                user_name=context.user_name,
                user_message=command_description,
                bot_response=(
                    full_summary[:500] + "..."
                    if len(full_summary) > 500
                    else full_summary
                ),
                guild_id=str(context.guild_id) if context.guild_id else None,
                channel_id=str(context.channel_id),
                is_chart_analysis=force_charts,
            )
            logger.debug(
                f"Stored summary thread exchange for thread {
                    context.thread_id}"
            )
        except Exception as e:
            logger.warning("Failed to store summary thread exchange: %s", e)

    # Store summary in database
    try:
        from sorting_utils import get_top_n_tuples

        # Count messages per user
        user_counts = {}
        for msg in messages_for_summary:
            if not msg.get("is_bot", False):
                user = msg.get("author_name", "Unknown")
                user_counts[user] = user_counts.get(user, 0) + 1

        # Get all users sorted by activity (most active first)
        sorted_user_tuples = get_top_n_tuples(
            list(user_counts.items()), n=len(user_counts), reverse=True
        )
        active_users = [user for user, count in sorted_user_tuples]
        database.store_channel_summary(
            channel_id=channel_id_str,
            channel_name=channel_name_str,
            date=today,
            summary_text=full_summary,
            message_count=len(messages_for_summary),
            active_users=active_users,
            guild_id=str(context.guild_id) if context.guild_id else None,
            guild_name=context.guild_name,
            metadata={
                "hours_summarized": hours,
                "requested_by": str(context.user_id),
            },
        )
    except Exception as e:
        logger.error("Failed to store summary in database: %s", str(e))


async def _get_thread_context(context: CommandContext) -> str:
    """Get thread context if available."""
    import logging

    logger = logging.getLogger(__name__)
    thread_context = ""

    if context.source_type == "message":
        if hasattr(context, "thread_id") and context.thread_id:
            thread_id = context.thread_id
            if has_thread_memory(thread_id):
                thread_context = get_thread_context(thread_id, max_exchanges=3)
                logger.debug(
                    f"Retrieved thread context for summary in thread {thread_id}"
                )

    return thread_context


async def _send_summary_with_charts(
    sender: ResponseSender, summary_parts: list, chart_data: list
):
    """Send summary with charts helper."""
    if chart_data and summary_parts:
        await sender.send_with_charts(summary_parts[0], chart_data)
        if len(summary_parts) > 1:
            await sender.send_in_parts(summary_parts[1:])
    else:
        await sender.send_in_parts(summary_parts)


async def _process_summary_generation(
    context: CommandContext,
    messages_for_summary: list,
    channel_name_str: str,
    hours: int,
    force_charts: bool,
):
    """Process summary generation and return summary parts and chart data."""
    from datetime import datetime, timezone
    from llm_handler import call_llm_for_summary
    from message_utils import split_long_message
    import logging

    logger = logging.getLogger(__name__)
    today = datetime.now(timezone.utc)

    # Check for thread context if we're in a thread
    thread_context = await _get_thread_context(context)
    if thread_context:
        logger.info(
            f"Generating summary with thread context awareness for {
                len(messages_for_summary)} messages"
        )

    # Generate summary
    summary, chart_data = await call_llm_for_summary(
        messages_for_summary, channel_name_str, today, hours, force_charts
    )
    summary_parts = await split_long_message(summary)

    return summary_parts, chart_data, today


async def _handle_guild_summary(
    context: CommandContext,
    response_sender: ResponseSender,
    thread_manager: ThreadManager,
    initial_message,
    summary_parts: list,
    chart_data: list,
    channel_name_str: str,
    hours: int,
    today,
):
    """Handle summary for guild channels with thread creation."""
    import logging
    import discord

    logger = logging.getLogger(__name__)
    thread_name = f"Summary - {channel_name_str} - {today.strftime('%Y-%m-%d')}"

    if initial_message:
        try:
            thread = await thread_manager.create_thread_from_message(
                initial_message, thread_name
            )

            if thread:
                thread_sender = MessageResponseSender(thread)
                await _send_summary_with_charts(
                    thread_sender, summary_parts, chart_data
                )

                await initial_message.edit(
                    content=f"**Summary of #{channel_name_str} for the past {hours} hour{'s' if hours != 1 else ''}**"  # noqa: E501
                )
            else:
                logger.warning(
                    "Thread creation failed, sending summary in main channel"
                )
                await initial_message.edit(
                    content=f"**Summary of #{channel_name_str} for the past {hours} hour{'s' if hours != 1 else ''}**"  # noqa: E501
                )
                await _send_summary_with_charts(
                    response_sender, summary_parts, chart_data
                )

        except discord.HTTPException as e:
            logger.warning("Failed to edit initial message: %s", e)
            thread = await thread_manager.create_thread(thread_name)
            if thread:
                thread_sender = MessageResponseSender(thread)
                await _send_summary_with_charts(
                    thread_sender, summary_parts, chart_data
                )
                await response_sender.send(
                    f"Summary posted in thread: {thread.mention}"
                )
            else:
                await _send_summary_with_charts(
                    response_sender, summary_parts, chart_data
                )
    else:
        thread = await thread_manager.create_thread(thread_name)
        if thread:
            thread_sender = MessageResponseSender(thread)
            await _send_summary_with_charts(thread_sender, summary_parts, chart_data)
            await response_sender.send(f"Summary posted in thread: {thread.mention}")
        else:
            await _send_summary_with_charts(response_sender, summary_parts, chart_data)


async def handle_summary_command(
    context: CommandContext,
    response_sender: ResponseSender,
    thread_manager: ThreadManager,
    hours: int = 24,
    bot_user: Optional[discord.ClientUser] = None,
    force_charts: bool = False,
) -> None:
    """
    Core logic for summary commands, abstracted from Discord-specific handling.

    Args:
        context: Command execution context
        response_sender: Interface for sending responses
        thread_manager: Interface for thread creation
        hours: Number of hours to summarize (default 24)
        bot_user: Bot user for database operations
        force_charts: If True, use chart-focused analysis system
    """
    from datetime import datetime, timezone
    import database
    import config
    import logging

    logger = logging.getLogger(__name__)

    # Input validation
    if not await _validate_summary_inputs(context, response_sender, hours):
        return

    # Rate limiting
    if not await _check_rate_limits(context, response_sender):
        return

    # Send initial response
    initial_message = await response_sender.send(
        "Generating channel summary, please wait... This may take a moment."
    )

    try:
        today = datetime.now(timezone.utc)
        channel_id_str = str(context.channel_id)
        channel_name_str = context.channel_name or "DM"

        # Database checks
        if not await _validate_database_connection(response_sender):
            return

        # Get messages for the specified time period
        messages_for_summary = database.get_channel_messages_for_hours(
            channel_id_str, today, hours
        )

        logger.info(
            f"Found {
                len(messages_for_summary)} messages for summary in channel {channel_name_str} (past {hours} hours)"  # noqa: E501
        )

        if not messages_for_summary:
            logger.info(
                f"No messages found for summary command in channel {channel_name_str} for the past {hours} hours"  # noqa: E501
            )
            error_msg = config.ERROR_MESSAGES["no_messages_found"].format(hours=hours)
            await response_sender.send(error_msg, ephemeral=True)
            return

        # Process summary generation
        summary_parts, chart_data, today = await _process_summary_generation(
            context, messages_for_summary, channel_name_str, hours, force_charts
        )

        # Combine summary parts for storage
        full_summary = " ".join(summary_parts)

        # Send summary
        if context.guild_id:
            await _handle_guild_summary(
                context,
                response_sender,
                thread_manager,
                initial_message,
                summary_parts,
                chart_data,
                channel_name_str,
                hours,
                today,
            )
        else:
            # For DMs: Send summary directly in the channel
            await _send_summary_with_charts(response_sender, summary_parts, chart_data)

        # Store bot responses in database for DMs
        if context.source_type == "message" and not context.guild_id:
            await _store_dm_responses(summary_parts, context, bot_user)

        # Store summary in thread memory and database
        await _store_summary_data(
            context,
            full_summary,
            messages_for_summary,
            hours,
            force_charts,
            channel_id_str,
            channel_name_str,
            today,
        )

    except Exception as e:
        logger.error("Error in handle_summary_command: %s", str(e), exc_info=True)
        await response_sender.send(
            config.ERROR_MESSAGES["summary_error"], ephemeral=True
        )
