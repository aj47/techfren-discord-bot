"""
Thread Memory System for Discord Bot

This module provides thread-based conversation memory, allowing the bot to remember
previous exchanges within a thread and maintain context across multiple interactions.
"""

import sqlite3
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class ThreadMessage:
    """Represents a message in a thread conversation."""

    sequence_id: int
    user_message: str
    bot_response: str
    user_id: str
    user_name: str
    timestamp: datetime
    message_type: str  # 'user', 'bot'


class ThreadMemoryManager:
    """Manages thread-based conversation memory for the Discord bot."""

    def __init__(self, db_path: str = "bot_database.db"):
        """Initialize the thread memory manager."""
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure the thread memory database schema exists."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Create thread_conversations table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS thread_conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        thread_id TEXT NOT NULL,
                        sequence_number INTEGER NOT NULL,
                        user_id TEXT NOT NULL,
                        user_name TEXT NOT NULL,
                        user_message TEXT NOT NULL,
                        bot_response TEXT,
                        timestamp DATETIME NOT NULL,
                        guild_id TEXT,
                        channel_id TEXT,
                        is_chart_analysis BOOLEAN DEFAULT 0,
                        context_data TEXT,  -- JSON for additional context
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(thread_id, sequence_number)
                    )
                """
                )

                # Create indexes for efficient retrieval
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_thread_conversations_thread_id
                    ON thread_conversations(thread_id)
                """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_thread_conversations_timestamp
                    ON thread_conversations(timestamp DESC)
                """
                )

                # Create thread_metadata table for thread-level information
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS thread_metadata (
                        thread_id TEXT PRIMARY KEY,
                        thread_name TEXT,
                        creator_id TEXT,
                        creator_name TEXT,
                        guild_id TEXT,
                        channel_id TEXT,
                        created_at DATETIME NOT NULL,
                        last_activity DATETIME NOT NULL,
                        message_count INTEGER DEFAULT 0,
                        is_active BOOLEAN DEFAULT 1,
                        thread_type TEXT DEFAULT 'conversation'  -- 'conversation', 'summary', 'analysis'  # noqa: E501
                    )
                """
                )

                conn.commit()
                logger.info("Thread memory database schema initialized successfully")

        except sqlite3.Error as e:
            logger.error("Error initializing thread memory schema: %s", e)
            raise

    def store_thread_exchange(
        self,
        thread_id: str,
        user_id: str,
        user_name: str,
        user_message: str,
        bot_response: str,
        guild_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        is_chart_analysis: bool = False,
        context_data: Optional[Dict] = None,
    ) -> bool:
        """
        Store a complete user-bot exchange in the thread memory.

        Args:
            thread_id: Discord thread ID
            user_id: User's Discord ID
            user_name: User's display name
            user_message: User's message content
            bot_response: Bot's response content
            guild_id: Guild ID where thread exists
            channel_id: Channel ID where thread exists
            is_chart_analysis: Whether this was a chart analysis request
            context_data: Additional context information

        Returns:
            bool: True if stored successfully
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get next sequence number for this thread
                cursor.execute(
                    """
                    SELECT COALESCE(MAX(sequence_number), 0) + 1
                    FROM thread_conversations
                    WHERE thread_id = ?
                """,
                    (thread_id,),
                )

                sequence_number = cursor.fetchone()[0]

                # Store the exchange
                context_json = json.dumps(context_data) if context_data else None
                timestamp = datetime.now(timezone.utc)

                cursor.execute(
                    """
                    INSERT INTO thread_conversations (
                        thread_id, sequence_number, user_id, user_name,
                        user_message, bot_response, timestamp, guild_id,
                        channel_id, is_chart_analysis, context_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        thread_id,
                        sequence_number,
                        user_id,
                        user_name,
                        user_message,
                        bot_response,
                        timestamp,
                        guild_id,
                        channel_id,
                        is_chart_analysis,
                        context_json,
                    ),
                )

                # Update or create thread metadata
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO thread_metadata (
                        thread_id, creator_id, creator_name, guild_id, channel_id,
                        created_at, last_activity, message_count, is_active
                    ) VALUES (
                        ?, ?, ?, ?, ?,
                        COALESCE((SELECT created_at FROM thread_metadata WHERE thread_id = ?), ?),  # noqa: E501
                        ?, ?, 1
                    )
                """,
                    (
                        thread_id,
                        user_id,
                        user_name,
                        guild_id,
                        channel_id,
                        thread_id,
                        timestamp,
                        timestamp,
                        sequence_number,
                    ),
                )

                conn.commit()
                logger.debug(
                    f"Stored thread exchange for thread {thread_id}, sequence {sequence_number}")  # noqa: E501
                return True

        except sqlite3.Error as e:
            logger.error("Error storing thread exchange: %s", e)
            return False

    def get_thread_memory(
        self,
        thread_id: str,
        max_exchanges: int = 10,
        include_chart_context: bool = True,
    ) -> List[ThreadMessage]:
        """
        Retrieve conversation memory for a thread.

        Args:
            thread_id: Discord thread ID
            max_exchanges: Maximum number of exchanges to retrieve
            include_chart_context: Whether to include chart analysis context

        Returns:
            List of ThreadMessage objects in chronological order
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                query = """
                    SELECT sequence_number, user_message, bot_response, user_id, user_name,  # noqa: E501
                           timestamp, is_chart_analysis, context_data
                    FROM thread_conversations
                    WHERE thread_id = ?
                """

                if not include_chart_context:
                    query += " AND is_chart_analysis = 0"

                query += " ORDER BY sequence_number DESC LIMIT ?"

                cursor.execute(query, (thread_id, max_exchanges))
                rows = cursor.fetchall()

                # Convert to ThreadMessage objects and reverse to chronological order
                messages = []
                for row in reversed(rows):
                    (
                        sequence_id,
                        user_msg,
                        bot_resp,
                        user_id,
                        user_name,
                        timestamp_str,
                        is_chart,
                        context_json,
                    ) = row

                    # Parse timestamp
                    timestamp = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )

                    messages.append(
                        ThreadMessage(
                            sequence_id=sequence_id,
                            user_message=user_msg,
                            bot_response=bot_resp,
                            user_id=user_id,
                            user_name=user_name,
                            timestamp=timestamp,
                            message_type="exchange",
                        )
                    )

                logger.debug(
                    f"Retrieved {len(messages)} thread messages for thread {thread_id}"
                )
                return messages

        except sqlite3.Error as e:
            logger.error("Error retrieving thread memory: %s", e)
            return []

    def format_thread_context(
        self, thread_messages: List[ThreadMessage], max_context_length: int = 2500
    ) -> str:
        """
        Format thread messages into context string for LLM.

        Args:
            thread_messages: List of ThreadMessage objects
            max_context_length: Maximum length of context string

        Returns:
            Formatted context string
        """
        if not thread_messages:
            return ""

        context_parts = ["**Previous conversation in this thread:**"]
        current_length = len(context_parts[0])

        for msg in thread_messages:
            # Format timestamp
            time_str = msg.timestamp.strftime("%H:%M")

            # Format exchange - truncate user message and bot response for brevity
            user_msg_truncated = (
                msg.user_message[:150] + "..."
                if len(msg.user_message) > 150
                else msg.user_message
            )
            bot_resp_truncated = (
                msg.bot_response[:100] + "..."
                if len(msg.bot_response) > 100
                else msg.bot_response
            )

            exchange = f"\n[{time_str}] {msg.user_name}: {user_msg_truncated}"
            exchange += f"\nBot: {bot_resp_truncated}"

            # Check if adding this exchange would exceed limit
            if current_length + len(exchange) > max_context_length:
                context_parts.append("\n[Earlier messages truncated...]")
                break

            context_parts.append(exchange)
            current_length += len(exchange)

        return "\n".join(context_parts)

    def get_thread_summary(self, thread_id: str) -> Optional[Dict]:
        """
        Get a summary of thread activity.

        Args:
            thread_id: Discord thread ID

        Returns:
            Dictionary with thread summary information
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get thread metadata
                cursor.execute(
                    """
                    SELECT thread_name, creator_name, created_at, last_activity,
                           message_count, thread_type
                    FROM thread_metadata
                    WHERE thread_id = ?
                """,
                    (thread_id,),
                )

                metadata = cursor.fetchone()
                if not metadata:
                    return None

                # Get conversation stats
                cursor.execute(
                    """
                    SELECT COUNT(*) as total_exchanges,
                           COUNT(CASE WHEN is_chart_analysis = 1 THEN 1 END) as chart_analyses,  # noqa: E501
                           MIN(timestamp) as first_exchange,
                           MAX(timestamp) as last_exchange
                    FROM thread_conversations
                    WHERE thread_id = ?
                """,
                    (thread_id,),
                )

                stats = cursor.fetchone()

                return {
                    "thread_name": metadata[0],
                    "creator_name": metadata[1],
                    "created_at": metadata[2],
                    "last_activity": metadata[3],
                    "message_count": metadata[4],
                    "thread_type": metadata[5],
                    "total_exchanges": stats[0] if stats else 0,
                    "chart_analyses": stats[1] if stats else 0,
                    "first_exchange": stats[2] if stats else None,
                    "last_exchange": stats[3] if stats else None,
                }

        except sqlite3.Error as e:
            logger.error("Error getting thread summary: %s", e)
            return None

    def cleanup_old_threads(self, days_old: int = 30) -> int:
        """
        Clean up thread memory older than specified days.

        Args:
            days_old: Number of days after which to clean up threads

        Returns:
            Number of threads cleaned up
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get threads to be cleaned up
                cursor.execute(
                    """
                    SELECT thread_id FROM thread_metadata
                    WHERE last_activity < ? AND is_active = 1
                """,
                    (cutoff_date,),
                )

                old_threads = [row[0] for row in cursor.fetchall()]

                if old_threads:
                    # Mark threads as inactive instead of deleting
                    cursor.execute(
                        """
                        UPDATE thread_metadata
                        SET is_active = 0
                        WHERE thread_id IN ({})
                    """.format(
                            ",".join("?" * len(old_threads))
                        ),
                        old_threads,
                    )

                    conn.commit()
                    logger.info("Marked %d old threads as inactive", len(old_threads))

                return len(old_threads)

        except sqlite3.Error as e:
            logger.error("Error cleaning up old threads: %s", e)
            return 0

    def search_thread_conversations(
        self, search_term: str, thread_id: Optional[str] = None, limit: int = 10
    ) -> List[Dict]:
        """
        Search through thread conversations.

        Args:
            search_term: Term to search for
            thread_id: Optional specific thread to search in
            limit: Maximum number of results

        Returns:
            List of matching conversation snippets
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                query = """
                    SELECT tc.thread_id, tc.user_name, tc.user_message, tc.bot_response,
                           tc.timestamp, tm.thread_name
                    FROM thread_conversations tc
                    LEFT JOIN thread_metadata tm ON tc.thread_id = tm.thread_id
                    WHERE (tc.user_message LIKE ? OR tc.bot_response LIKE ?)
                """

                params = [f"%{search_term}%", f"%{search_term}%"]

                if thread_id:
                    query += " AND tc.thread_id = ?"
                    params.append(thread_id)

                query += " ORDER BY tc.timestamp DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                results = []
                for row in rows:
                    results.append(
                        {
                            "thread_id": row[0],
                            "user_name": row[1],
                            "user_message": row[2],
                            "bot_response": row[3],
                            "timestamp": row[4],
                            "thread_name": row[5] or "Unknown Thread",
                        }
                    )

                return results

        except sqlite3.Error as e:
            logger.error("Error searching thread conversations: %s", e)
            return []


# Singleton instance for global use
_thread_memory_manager = None


def get_thread_memory_manager() -> ThreadMemoryManager:
    """Get the global thread memory manager instance."""
    global _thread_memory_manager
    if _thread_memory_manager is None:
        _thread_memory_manager = ThreadMemoryManager()
    return _thread_memory_manager


def store_thread_exchange(
    thread_id: str,
    user_id: str,
    user_name: str,
    user_message: str,
    bot_response: str,
    **kwargs,
) -> bool:
    """Convenience function to store a thread exchange."""
    manager = get_thread_memory_manager()
    return manager.store_thread_exchange(
        thread_id, user_id, user_name, user_message, bot_response, **kwargs
    )


def get_thread_context(thread_id: str, max_exchanges: int = 6) -> str:
    """Convenience function to get formatted thread context."""
    manager = get_thread_memory_manager()
    messages = manager.get_thread_memory(thread_id, max_exchanges)
    return manager.format_thread_context(messages)


def has_thread_memory(thread_id: str) -> bool:
    """Check if a thread has existing conversation memory."""
    manager = get_thread_memory_manager()
    messages = manager.get_thread_memory(thread_id, max_exchanges=1)
    return len(messages) > 0


def clear_thread_memory(thread_id: str) -> bool:
    """Clear conversation memory for a specific thread."""
    manager = get_thread_memory_manager()
    try:
        with sqlite3.connect(manager.db_path) as conn:
            cursor = conn.cursor()

            # Mark thread as inactive and clear conversations
            cursor.execute(
                """
                UPDATE thread_metadata
                SET is_active = 0
                WHERE thread_id = ?
            """,
                (thread_id,),
            )

            cursor.execute(
                """
                DELETE FROM thread_conversations
                WHERE thread_id = ?
            """,
                (thread_id,),
            )

            conn.commit()
            logger.info("Cleared thread memory for thread %s", thread_id)
            return True

    except sqlite3.Error as e:
        logger.error("Error clearing thread memory: %s", e)
        return False


def get_thread_stats(thread_id: str) -> Optional[Dict]:
    """Get statistics about a thread's conversation history."""
    manager = get_thread_memory_manager()
    summary = manager.get_thread_summary(thread_id)
    if not summary:
        return None

    messages = manager.get_thread_memory(thread_id, max_exchanges=50)

    return {
        "thread_name": summary.get("thread_name", "Unknown Thread"),
        "creator": summary.get("creator_name", "Unknown"),
        "created_at": summary.get("created_at"),
        "total_exchanges": len(messages),
        "chart_analyses": summary.get("chart_analyses", 0),
        "last_activity": summary.get("last_activity"),
        "is_active": bool(messages),  # Active if has recent messages
    }


async def process_thread_memory_command(message, command_parts):
    """Process thread memory management commands."""
    if not command_parts or len(command_parts) < 2:
        return "Thread memory commands: `/thread-memory status`, `/thread-memory clear`, `/thread-memory stats`"  # noqa: E501

    action = command_parts[1].lower()
    thread_id = str(message.channel.id) if hasattr(message.channel, "parent") else None

    if not thread_id:
        return "Thread memory commands can only be used in threads."

    if action == "status":
        if has_thread_memory(thread_id):
            messages = get_thread_memory_manager().get_thread_memory(
                thread_id, max_exchanges=1
            )
            last_msg = messages[0] if messages else None
            if last_msg:
                return f"✅ This thread has conversation memory.\nLast exchange: {
                    last_msg.timestamp.strftime('%Y-%m-%d %H:%M')} UTC"
            else:
                return "This thread has no conversation memory."
        else:
            return "This thread has no conversation memory."

    elif action == "clear":
        if clear_thread_memory(thread_id):
            return "Thread conversation memory cleared successfully."
        else:
            return "Failed to clear thread memory."

    elif action == "stats":
        stats = get_thread_stats(thread_id)
        if stats:
            return f"""**Thread Statistics**
**Creator:** {stats['creator']}
**Total Exchanges:** {stats['total_exchanges']}
**Chart Analyses:** {stats['chart_analyses']}
**Created:** {stats['created_at'][:16] if stats['created_at'] else 'Unknown'}
**Last Activity:** {stats['last_activity'][:16] if stats['last_activity'] else 'Unknown'}  # noqa: E501
**Status:** {'Active' if stats['is_active'] else 'Inactive'}"""
        else:
            return "No statistics available for this thread."

    else:
        return f"Unknown action: {action}. Available: status, clear, stats"
