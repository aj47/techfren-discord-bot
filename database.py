"""
Database module for the Discord bot.
Handles SQLite database operations for storing messages and channel summaries.
"""

import sqlite3
import os
import logging
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

# Set up logging
logger = logging.getLogger('discord_bot.database')

# Database constants
DB_DIRECTORY = "data"
DB_FILE = os.path.join(DB_DIRECTORY, "discord_messages.db")

# SQL statements
CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    guild_id TEXT,
    guild_name TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    is_bot INTEGER NOT NULL,
    is_command INTEGER NOT NULL,
    command_type TEXT,
    scraped_url TEXT,
    scraped_content_summary TEXT,
    scraped_content_key_points TEXT,
    image_descriptions TEXT,
    reply_to_message_id TEXT
);
"""

CREATE_CHANNEL_SUMMARIES_TABLE = """
CREATE TABLE IF NOT EXISTS channel_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    guild_id TEXT,
    guild_name TEXT,
    date TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    active_users INTEGER NOT NULL,
    active_users_list TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    metadata TEXT
);
"""

CREATE_USER_POINTS_TABLE = """
CREATE TABLE IF NOT EXISTS user_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    total_points INTEGER DEFAULT 0,
    last_updated TIMESTAMP NOT NULL,
    UNIQUE(author_id, guild_id)
);
"""

CREATE_DAILY_POINT_AWARDS_TABLE = """
CREATE TABLE IF NOT EXISTS daily_point_awards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    date TEXT NOT NULL,
    points_awarded INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    UNIQUE(author_id, guild_id, date)
);
"""

CREATE_USER_ROLE_COLORS_TABLE = """
CREATE TABLE IF NOT EXISTS user_role_colors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    color_hex TEXT NOT NULL,
    color_name TEXT NOT NULL,
    points_per_day INTEGER NOT NULL,
    started_at TIMESTAMP NOT NULL,
    last_charged_date TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    UNIQUE(author_id, guild_id)
);
"""

CREATE_INDEX_AUTHOR = "CREATE INDEX IF NOT EXISTS idx_author_id ON messages (author_id);"
CREATE_INDEX_CHANNEL = "CREATE INDEX IF NOT EXISTS idx_channel_id ON messages (channel_id);"
CREATE_INDEX_GUILD = "CREATE INDEX IF NOT EXISTS idx_guild_id ON messages (guild_id);"
CREATE_INDEX_CREATED = "CREATE INDEX IF NOT EXISTS idx_created_at ON messages (created_at);"
CREATE_INDEX_COMMAND = "CREATE INDEX IF NOT EXISTS idx_is_command ON messages (is_command);"
CREATE_INDEX_SUMMARY_CHANNEL = "CREATE INDEX IF NOT EXISTS idx_summary_channel_id ON channel_summaries (channel_id);"
CREATE_INDEX_SUMMARY_DATE = "CREATE INDEX IF NOT EXISTS idx_summary_date ON channel_summaries (date);"
CREATE_INDEX_USER_POINTS_AUTHOR = "CREATE INDEX IF NOT EXISTS idx_user_points_author_id ON user_points (author_id);"
CREATE_INDEX_USER_POINTS_GUILD = "CREATE INDEX IF NOT EXISTS idx_user_points_guild_id ON user_points (guild_id);"
CREATE_INDEX_DAILY_AWARDS_DATE = "CREATE INDEX IF NOT EXISTS idx_daily_awards_date ON daily_point_awards (date);"
CREATE_INDEX_DAILY_AWARDS_AUTHOR = "CREATE INDEX IF NOT EXISTS idx_daily_awards_author_id ON daily_point_awards (author_id);"
CREATE_INDEX_ROLE_COLORS_AUTHOR = "CREATE INDEX IF NOT EXISTS idx_role_colors_author_id ON user_role_colors (author_id);"
CREATE_INDEX_ROLE_COLORS_GUILD = "CREATE INDEX IF NOT EXISTS idx_role_colors_guild_id ON user_role_colors (guild_id);"
CREATE_INDEX_REPLY_TO = "CREATE INDEX IF NOT EXISTS idx_reply_to_message_id ON messages (reply_to_message_id);"

INSERT_MESSAGE = """
INSERT INTO messages (
    id, author_id, author_name, channel_id, channel_name,
    guild_id, guild_name, content, created_at, is_bot, is_command, command_type,
    scraped_url, scraped_content_summary, scraped_content_key_points, image_descriptions,
    reply_to_message_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

INSERT_CHANNEL_SUMMARY = """
INSERT INTO channel_summaries (
    channel_id, channel_name, guild_id, guild_name, date,
    summary_text, message_count, active_users, active_users_list,
    created_at, metadata
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

def migrate_database() -> None:
    """
    Run database migrations to update schema for existing databases.
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            # Check if image_descriptions column exists
            cursor.execute("PRAGMA table_info(messages)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'image_descriptions' not in columns:
                logger.info("Adding image_descriptions column to messages table")
                cursor.execute("ALTER TABLE messages ADD COLUMN image_descriptions TEXT")
                conn.commit()
                logger.info("Successfully added image_descriptions column")

            # Check if reply_to_message_id column exists
            if 'reply_to_message_id' not in columns:
                logger.info("Adding reply_to_message_id column to messages table")
                cursor.execute("ALTER TABLE messages ADD COLUMN reply_to_message_id TEXT")
                cursor.execute(CREATE_INDEX_REPLY_TO)
                conn.commit()
                logger.info("Successfully added reply_to_message_id column and index")

    except Exception as e:
        logger.error(f"Error running database migrations: {str(e)}", exc_info=True)

def init_database() -> None:
    """
    Initialize the database by creating the necessary directory and tables.
    """
    try:
        # Create the data directory if it doesn't exist
        if not os.path.exists(DB_DIRECTORY):
            os.makedirs(DB_DIRECTORY)
            logger.info(f"Created database directory: {DB_DIRECTORY}")

        # Connect to the database and create tables using context manager
        with sqlite3.connect(DB_FILE) as conn:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")

            # Set a shorter timeout for better error reporting
            conn.execute("PRAGMA busy_timeout = 5000")  # 5 seconds

            cursor = conn.cursor()

            # Create tables and indexes
            cursor.execute(CREATE_MESSAGES_TABLE)
            cursor.execute(CREATE_CHANNEL_SUMMARIES_TABLE)
            cursor.execute(CREATE_USER_POINTS_TABLE)
            cursor.execute(CREATE_DAILY_POINT_AWARDS_TABLE)
            cursor.execute(CREATE_USER_ROLE_COLORS_TABLE)

            # Create indexes for messages table
            cursor.execute(CREATE_INDEX_AUTHOR)
            cursor.execute(CREATE_INDEX_CHANNEL)
            cursor.execute(CREATE_INDEX_GUILD)
            cursor.execute(CREATE_INDEX_CREATED)
            cursor.execute(CREATE_INDEX_COMMAND)

            # Create indexes for channel_summaries table
            cursor.execute(CREATE_INDEX_SUMMARY_CHANNEL)
            cursor.execute(CREATE_INDEX_SUMMARY_DATE)

            # Create indexes for user_points table
            cursor.execute(CREATE_INDEX_USER_POINTS_AUTHOR)
            cursor.execute(CREATE_INDEX_USER_POINTS_GUILD)

            # Create indexes for daily_point_awards table
            cursor.execute(CREATE_INDEX_DAILY_AWARDS_DATE)
            cursor.execute(CREATE_INDEX_DAILY_AWARDS_AUTHOR)

            # Create indexes for user_role_colors table
            cursor.execute(CREATE_INDEX_ROLE_COLORS_AUTHOR)
            cursor.execute(CREATE_INDEX_ROLE_COLORS_GUILD)

            # Create index for reply tracking
            cursor.execute(CREATE_INDEX_REPLY_TO)

            # Insert a test message to ensure the database is working
            try:
                test_message_id = f"test-init-{datetime.now().timestamp()}"
                cursor.execute(
                    INSERT_MESSAGE,
                    (
                        test_message_id,
                        "system",
                        "System",
                        "system",
                        "System",
                        None,
                        None,
                        "Database initialization test message",
                        datetime.now().isoformat(),
                        1,  # is_bot
                        0,  # is_command
                        None,
                        None,
                        None,
                        None,
                        None,  # image_descriptions
                        None   # reply_to_message_id
                    )
                )
                logger.info("Successfully inserted test message during database initialization")
            except sqlite3.IntegrityError:
                # This is fine, it means the test message already exists
                logger.info("Test message already exists in database")
            except Exception as e:
                logger.warning(f"Failed to insert test message during initialization: {str(e)}")

            conn.commit()

        # Run migrations for existing databases
        migrate_database()

        logger.info(f"Database initialized successfully at {DB_FILE}")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}", exc_info=True)
        raise

def get_connection() -> sqlite3.Connection:
    """
    Get a connection to the SQLite database.
    The connection supports context managers (with statements).

    Returns:
        sqlite3.Connection: A connection to the database.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row  # This enables column access by name

        # Set a shorter timeout for better error reporting
        conn.execute("PRAGMA busy_timeout = 5000")  # 5 seconds

        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")

        return conn
    except Exception as e:
        logger.error(f"Error connecting to database: {str(e)}", exc_info=True)
        raise

def check_database_connection() -> bool:
    """
    Check if the database connection is working properly.

    Returns:
        bool: True if the connection is working, False otherwise
    """
    try:
        # First check if the database file exists
        if not os.path.exists(DB_FILE):
            logger.error(f"Database file does not exist: {DB_FILE}")
            return False

        # Check if the file is readable and writable
        if not os.access(DB_FILE, os.R_OK | os.W_OK):
            logger.error(f"Database file is not readable or writable: {DB_FILE}")
            return False

        # Check the file size
        file_size = os.path.getsize(DB_FILE)
        logger.info(f"Database file size: {file_size} bytes")

        # Try to connect and execute a simple query
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

            # Check if the messages table exists and has the expected schema
            cursor.execute("PRAGMA table_info(messages)")
            columns = cursor.fetchall()
            if not columns:
                logger.error("Messages table does not exist in the database")
                return False

            # Log the schema
            column_names = [col['name'] for col in columns]
            logger.info(f"Messages table columns: {', '.join(column_names)}")

            return result is not None and result[0] == 1
    except Exception as e:
        logger.error(f"Database connection check failed: {str(e)}", exc_info=True)
        return False

def store_message(
    message_id: str,
    author_id: str,
    author_name: str,
    channel_id: str,
    channel_name: str,
    content: str,
    created_at: datetime,
    guild_id: Optional[str] = None,
    guild_name: Optional[str] = None,
    is_bot: bool = False,
    is_command: bool = False,
    command_type: Optional[str] = None,
    scraped_url: Optional[str] = None,
    scraped_content_summary: Optional[str] = None,
    scraped_content_key_points: Optional[str] = None,
    image_descriptions: Optional[str] = None,
    reply_to_message_id: Optional[str] = None
) -> bool:
    """
    Store a message in the database.

    Args:
        message_id (str): The Discord message ID
        author_id (str): The Discord user ID of the message author
        author_name (str): The username of the message author
        channel_id (str): The Discord channel ID where the message was sent
        channel_name (str): The name of the channel where the message was sent
        content (str): The content of the message
        created_at (datetime): The timestamp when the message was created
        guild_id (Optional[str]): The Discord guild ID (if applicable)
        guild_name (Optional[str]): The name of the guild (if applicable)
        is_bot (bool): Whether the message was sent by a bot
        is_command (bool): Whether the message is a command
        command_type (Optional[str]): The type of command (if applicable)
        scraped_url (Optional[str]): The URL that was scraped from the message (if any)
        scraped_content_summary (Optional[str]): Summary of the scraped content (if any)
        scraped_content_key_points (Optional[str]): JSON string of key points from scraped content (if any)
        image_descriptions (Optional[str]): JSON string of image analysis results (if any)
        reply_to_message_id (Optional[str]): The ID of the message this is replying to (if any)

    Returns:
        bool: True if the message was stored successfully, False otherwise
    """
    try:
        # Use context manager to ensure connection is properly closed
        with get_connection() as conn:
            cursor = conn.cursor()

# Ensure consistent datetime format for storage (always UTC, no timezone info for SQLite compatibility)
            created_at_str = created_at.replace(tzinfo=None).isoformat()

            cursor.execute(
                INSERT_MESSAGE,
                (
                    message_id,
                    author_id,
                    author_name,
                    channel_id,
                    channel_name,
                    guild_id,
                    guild_name,
                    content,
                    created_at_str,
                    1 if is_bot else 0,
                    1 if is_command else 0,
                    command_type,
                    scraped_url,
                    scraped_content_summary,
                    scraped_content_key_points,
                    image_descriptions,
                    reply_to_message_id
                )
            )

            conn.commit()

        logger.debug(f"Message {message_id} stored in database")
        return True
    except sqlite3.IntegrityError:
        # This could happen if we try to insert a message with the same ID twice
        # This is normal when the bot restarts and processes recent messages
        logger.debug(f"Message {message_id} already exists in database (skipping duplicate)")
        return False
    except Exception as e:
        logger.error(f"Error storing message {message_id}: {str(e)}", exc_info=True)
        return False

async def store_messages_batch(messages: List[Dict[str, Any]]) -> bool:
    """
    Store multiple messages in a single transaction for better performance and consistency.

    Args:
        messages (List[Dict[str, Any]]): List of message dictionaries with required fields

    Returns:
        bool: True if all messages were stored successfully, False otherwise
    """
    if not messages:
        return True
        
    try:
        def _store_batch():
            with get_connection() as conn:
                cursor = conn.cursor()
                
                for msg in messages:
                    # Ensure consistent datetime format for storage (always UTC, no timezone info for SQLite compatibility)
                    created_at = msg['created_at']
                    created_at_str = created_at.replace(tzinfo=None).isoformat()
                    
                    cursor.execute(
                        INSERT_MESSAGE,
                        (
                            msg['message_id'],
                            msg['author_id'],
                            msg['author_name'],
                            msg['channel_id'],
                            msg['channel_name'],
                            msg.get('guild_id'),
                            msg.get('guild_name'),
                            msg['content'],
                            created_at_str,
                            int(msg.get('is_bot', False)),
                            int(msg.get('is_command', False)),
                            msg.get('command_type'),
                            msg.get('scraped_url'),
                            msg.get('scraped_content_summary'),
                            msg.get('scraped_content_key_points'),
                            msg.get('image_descriptions'),
                            msg.get('reply_to_message_id')
                        )
                    )
                
                conn.commit()
                return True

        result = await asyncio.to_thread(_store_batch)
        logger.info(f"Stored {len(messages)} messages in batch transaction")
        return result
    except sqlite3.IntegrityError as e:
        logger.warning(f"Integrity error in batch message storage: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error storing message batch: {str(e)}", exc_info=True)
        return False

async def update_message_with_scraped_data(
    message_id: str,
    scraped_url: str,
    scraped_content_summary: str,
    scraped_content_key_points: str
) -> bool:
    """
    Update an existing message with scraped URL data.

    Args:
        message_id (str): The Discord message ID to update
        scraped_url (str): The URL that was scraped
        scraped_content_summary (str): Summary of the scraped content
        scraped_content_key_points (str): JSON string of key points from scraped content

    Returns:
        bool: True if the message was updated successfully, False otherwise
    """
    try:
        # Define a synchronous function to run in a thread pool
        def _update_message_sync():
            with get_connection() as conn:
                cursor = conn.cursor()

                # Update the message with scraped data
                cursor.execute(
                    """
                    UPDATE messages
                    SET scraped_url = ?,
                        scraped_content_summary = ?,
                        scraped_content_key_points = ?
                    WHERE id = ?
                    """,
                    (
                        scraped_url,
                        scraped_content_summary,
                        scraped_content_key_points,
                        message_id
                    )
                )

                # Check if any rows were affected
                rows_affected = cursor.rowcount == 0
                conn.commit()
                return rows_affected

        # Run the synchronous function in a thread pool to avoid blocking the event loop
        no_rows_affected = await asyncio.to_thread(_update_message_sync)

        if no_rows_affected:
            logger.warning(f"No message found with ID {message_id} to update with scraped data")
            return False

        logger.info(f"Message {message_id} updated with scraped data from URL: {scraped_url}")
        return True
    except Exception as e:
        logger.error(f"Error updating message {message_id} with scraped data: {str(e)}", exc_info=True)
        return False

def get_message_count() -> int:
    """
    Get the total number of messages in the database.

    Returns:
        int: The number of messages
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM messages")
            count = cursor.fetchone()[0]

        return count
    except Exception as e:
        logger.error(f"Error getting message count: {str(e)}", exc_info=True)
        # Return 0 instead of -1 for consistency with other error cases
        return 0

def get_user_message_count(user_id: str) -> int:
    """
    Get the number of messages from a specific user.

    Args:
        user_id (str): The Discord user ID

    Returns:
        int: The number of messages from the user
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM messages WHERE author_id = ?", (user_id,))
            count = cursor.fetchone()[0]

        return count
    except Exception as e:
        logger.error(f"Error getting message count for user {user_id}: {str(e)}", exc_info=True)
        # Return 0 instead of -1 for consistency with other error cases
        return 0

def get_all_channel_messages(channel_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get all messages from a specific channel, regardless of date.

    Args:
        channel_id (str): The Discord channel ID
        limit (int): Maximum number of messages to return

    Returns:
        List[Dict[str, Any]]: A list of messages as dictionaries
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Query all messages for the channel
            cursor.execute(
                """
                SELECT author_name, content, created_at, is_bot, is_command,
                       scraped_url, scraped_content_summary, scraped_content_key_points, image_descriptions
                FROM messages
                WHERE channel_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (channel_id, limit)
            )

            # Convert rows to dictionaries
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'author_name': row['author_name'],
                    'content': row['content'],
                    'created_at': datetime.fromisoformat(row['created_at']),
                    'is_bot': bool(row['is_bot']),
                    'is_command': bool(row['is_command']),
                    'scraped_url': row['scraped_url'],
                    'scraped_content_summary': row['scraped_content_summary'],
                    'scraped_content_key_points': row['scraped_content_key_points'],
                    'image_descriptions': row['image_descriptions']
                })

        logger.info(f"Retrieved {len(messages)} messages from channel {channel_id} (all time)")
        return messages
    except Exception as e:
        logger.error(f"Error getting all messages for channel {channel_id}: {str(e)}", exc_info=True)
        return []

def get_channel_messages_for_day(channel_id: str, date: datetime) -> List[Dict[str, Any]]:
    """
    Get all messages from a specific channel for the past 24 hours from the given date.

    Args:
        channel_id (str): The Discord channel ID
        date (datetime): The reference date (will get messages for 24 hours before this date)

    Returns:
        List[Dict[str, Any]]: A list of messages as dictionaries
    """
    return get_channel_messages_for_hours(channel_id, date, 24)

def get_channel_messages_for_hours(channel_id: str, date: datetime, hours: int) -> List[Dict[str, Any]]:
    """
    Get all messages from a specific channel for the past specified hours from the given date.

    Args:
        channel_id (str): The Discord channel ID
        date (datetime): The reference date (will get messages for specified hours before this date)
        hours (int): Number of hours to look back

    Returns:
        List[Dict[str, Any]]: A list of messages as dictionaries
    """
    try:
        # Ensure we're working with UTC timezone
        if date.tzinfo is None:
            # If naive datetime, assume it's UTC
            date = date.replace(tzinfo=timezone.utc)
        elif date.tzinfo != timezone.utc:
            # Convert to UTC if it's in a different timezone
            date = date.astimezone(timezone.utc)

        # Calculate the time range for the past specified hours
        # Add a small buffer (1 minute) to ensure we capture very recent messages
        end_date = date + timedelta(minutes=1)
        start_date = date - timedelta(hours=hours)

        # Convert to ISO format for database query (remove timezone info for SQLite compatibility)
        # For SQLite, we need to handle timezone-aware datetime strings properly
        start_date_str = start_date.replace(tzinfo=None).isoformat()
        end_date_str = end_date.replace(tzinfo=None).isoformat()

        with get_connection() as conn:
            cursor = conn.cursor()

            # Query messages for the channel within the time range
            # Use datetime comparison that works with SQLite's text storage
            # Handle both timezone-aware and naive datetime strings in the database
            cursor.execute(
                """
                SELECT id, author_name, content, created_at, is_bot, is_command,
                       scraped_url, scraped_content_summary, scraped_content_key_points,
                       image_descriptions, guild_id
                FROM messages
                WHERE channel_id = ?
                AND (
                    datetime(created_at) BETWEEN datetime(?) AND datetime(?)
                    OR datetime(substr(created_at, 1, 19)) BETWEEN datetime(?) AND datetime(?)
                )
                ORDER BY created_at ASC
                """,
                (channel_id, start_date_str, end_date_str, start_date_str, end_date_str)
            )

            # Convert rows to dictionaries
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'id': row['id'],
                    'author_name': row['author_name'],
                    'content': row['content'],
                    'created_at': datetime.fromisoformat(row['created_at']),
                    'is_bot': bool(row['is_bot']),
                    'is_command': bool(row['is_command']),
                    'scraped_url': row['scraped_url'],
                    'scraped_content_summary': row['scraped_content_summary'],
                    'scraped_content_key_points': row['scraped_content_key_points'],
                    'image_descriptions': row['image_descriptions'],
                    'guild_id': row['guild_id'],
                    'channel_id': channel_id
                })

        logger.info(f"Retrieved {len(messages)} messages from channel {channel_id} for the past {hours} hours from {start_date.isoformat()} to {end_date.isoformat()}")
        return messages
    except Exception as e:
        logger.error(f"Error getting messages for channel {channel_id} for the past {hours} hours from {date.isoformat()}: {str(e)}", exc_info=True)
        return []

def get_messages_for_time_range(start_time: datetime, end_time: datetime) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get all messages from all channels within a specific time range, grouped by channel.

    Args:
        start_time (datetime): The start time for the range
        end_time (datetime): The end time for the range

    Returns:
        Dict[str, List[Dict[str, Any]]]: A dictionary mapping channel_id to a list of messages
    """
    try:
        start_date_str = start_time.isoformat()
        end_date_str = end_time.isoformat()

        with get_connection() as conn:
            cursor = conn.cursor()

            # Query messages within the time range
            cursor.execute(
                """
                SELECT
                    id, author_id, author_name, channel_id, channel_name,
                    guild_id, guild_name, content, created_at, is_bot, is_command,
                    scraped_url, scraped_content_summary, scraped_content_key_points, image_descriptions
                FROM messages
                WHERE created_at BETWEEN ? AND ?
                ORDER BY channel_id, created_at ASC
                """,
                (start_date_str, end_date_str)
            )

            # Group messages by channel
            messages_by_channel = {}
            for row in cursor.fetchall():
                channel_id = row['channel_id']

                if channel_id not in messages_by_channel:
                    messages_by_channel[channel_id] = {
                        'channel_id': channel_id,
                        'channel_name': row['channel_name'],
                        'guild_id': row['guild_id'],
                        'guild_name': row['guild_name'],
                        'messages': []
                    }

                messages_by_channel[channel_id]['messages'].append({
                    'id': row['id'],
                    'author_id': row['author_id'],
                    'author_name': row['author_name'],
                    'content': row['content'],
                    'created_at': datetime.fromisoformat(row['created_at']),
                    'is_bot': bool(row['is_bot']),
                    'is_command': bool(row['is_command']),
                    'scraped_url': row['scraped_url'],
                    'scraped_content_summary': row['scraped_content_summary'],
                    'scraped_content_key_points': row['scraped_content_key_points'],
                    'image_descriptions': row['image_descriptions']
                })

        total_messages = sum(len(channel_data['messages']) for channel_data in messages_by_channel.values())
        logger.info(f"Retrieved {total_messages} messages from {len(messages_by_channel)} channels between {start_time} and {end_time}")
        return messages_by_channel
    except Exception as e:
        logger.error(f"Error getting messages between {start_time} and {end_time}: {str(e)}", exc_info=True)
        return {}

def store_channel_summary(
    channel_id: str,
    channel_name: str,
    date: datetime,
    summary_text: str,
    message_count: int,
    active_users: List[str],
    guild_id: Optional[str] = None,
    guild_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Store a channel summary in the database.

    Args:
        channel_id (str): The Discord channel ID
        channel_name (str): The name of the channel
        date (datetime): The date of the summary
        summary_text (str): The summary text
        message_count (int): The number of messages summarized
        active_users (List[str]): List of active user names
        guild_id (Optional[str]): The Discord guild ID (if applicable)
        guild_name (Optional[str]): The name of the guild (if applicable)
        metadata (Optional[Dict[str, Any]]): Additional metadata for the summary

    Returns:
        bool: True if the summary was stored successfully, False otherwise
    """
    try:
        # Convert active_users list to JSON string
        active_users_json = json.dumps(active_users)

        # Convert metadata to JSON string if provided
        metadata_json = json.dumps(metadata) if metadata else None

        # Format date as YYYY-MM-DD
        date_str = date.strftime('%Y-%m-%d')

        # Current timestamp
        created_at = datetime.now().isoformat()

        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                INSERT_CHANNEL_SUMMARY,
                (
                    channel_id,
                    channel_name,
                    guild_id,
                    guild_name,
                    date_str,
                    summary_text,
                    message_count,
                    len(active_users),
                    active_users_json,
                    created_at,
                    metadata_json
                )
            )

            conn.commit()

        logger.info(f"Stored summary for channel {channel_name} ({channel_id}) for {date_str}")
        return True
    except Exception as e:
        logger.error(f"Error storing summary for channel {channel_id} on {date.strftime('%Y-%m-%d')}: {str(e)}", exc_info=True)
        return False

def delete_messages_older_than(cutoff_time: datetime) -> int:
    """
    Delete messages older than the specified cutoff time.

    Args:
        cutoff_time (datetime): Messages older than this time will be deleted

    Returns:
        int: The number of messages deleted
    """
    try:
        cutoff_time_str = cutoff_time.isoformat()

        with get_connection() as conn:
            cursor = conn.cursor()

            # First, count how many messages will be deleted
            cursor.execute(
                "SELECT COUNT(*) FROM messages WHERE created_at < ?",
                (cutoff_time_str,)
            )
            count = cursor.fetchone()[0]

            # Then delete them
            cursor.execute(
                "DELETE FROM messages WHERE created_at < ?",
                (cutoff_time_str,)
            )

            conn.commit()

        logger.info(f"Deleted {count} messages older than {cutoff_time}")
        return count
    except Exception as e:
        logger.error(f"Error deleting messages older than {cutoff_time}: {str(e)}", exc_info=True)
        return 0

def get_active_channels(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get a list of channels that have had activity in the last specified hours.

    Args:
        hours (int): Number of hours to look back for activity

    Returns:
        List[Dict[str, Any]]: A list of active channels with their details
    """
    try:
        # Calculate the cutoff time
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

        with get_connection() as conn:
            cursor = conn.cursor()

            # Query for active channels
            cursor.execute(
                """
                SELECT
                    channel_id,
                    channel_name,
                    guild_id,
                    guild_name,
                    COUNT(*) as message_count
                FROM messages
                WHERE created_at >= ?
                GROUP BY channel_id
                ORDER BY message_count DESC
                """,
                (cutoff_time,)
            )

            # Convert rows to dictionaries
            channels = []
            for row in cursor.fetchall():
                channels.append({
                    'channel_id': row['channel_id'],
                    'channel_name': row['channel_name'],
                    'guild_id': row['guild_id'],
                    'guild_name': row['guild_name'],
                    'message_count': row['message_count']
                })

        logger.info(f"Found {len(channels)} active channels in the last {hours} hours")
        return channels
    except Exception as e:
        logger.error(f"Error getting active channels for the last {hours} hours: {str(e)}", exc_info=True)
        return []

def get_scraped_content_by_url(url: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve scraped content for a specific URL from the database.

    Args:
        url (str): The URL to search for

    Returns:
        Optional[Dict[str, Any]]: Dictionary containing scraped content if found, None otherwise
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Query for messages with scraped content for this URL
            cursor.execute(
                """
                SELECT
                    scraped_url,
                    scraped_content_summary,
                    scraped_content_key_points,
                    created_at
                FROM messages
                WHERE scraped_url = ? AND scraped_content_summary IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (url,)
            )

            row = cursor.fetchone()
            if not row:
                logger.debug(f"No scraped content found for URL: {url}")
                return None

            # Parse key points JSON
            key_points = []
            if row['scraped_content_key_points']:
                try:
                    key_points = json.loads(row['scraped_content_key_points'])
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in scraped_content_key_points for URL {url}")

            result = {
                'url': row['scraped_url'],
                'summary': row['scraped_content_summary'],
                'key_points': key_points,
                'created_at': row['created_at']
            }

            logger.debug(f"Retrieved scraped content for URL: {url}")
            return result

    except Exception as e:
        logger.error(f"Error retrieving scraped content for URL {url}: {str(e)}", exc_info=True)
        return None

def award_points_to_user(
    author_id: str,
    author_name: str,
    guild_id: str,
    points: int
) -> bool:
    """
    Award points to a user, updating their total points.

    Args:
        author_id (str): The Discord user ID
        author_name (str): The username
        guild_id (str): The Discord guild ID
        points (int): Number of points to award (must be 1-20)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Validate author_id is present
        if not author_id or not author_id.strip():
            logger.error("Cannot award points: author_id is empty or None")
            return False

        # Validate points are positive (reject zero or negative)
        if points <= 0:
            logger.warning(f"Skipping point award for {author_name}: points={points} (must be > 0)")
            return False

        # Clamp points to maximum of 20 per award
        if points > 20:
            logger.warning(f"Clamping points for {author_name} from {points} to 20 (max per user per day)")
            points = 20

        with get_connection() as conn:
            cursor = conn.cursor()

            # Insert or update user points
            cursor.execute(
                """
                INSERT INTO user_points (author_id, author_name, guild_id, total_points, last_updated)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(author_id, guild_id) DO UPDATE SET
                    total_points = total_points + ?,
                    author_name = ?,
                    last_updated = ?
                """,
                (
                    author_id,
                    author_name,
                    guild_id,
                    points,
                    datetime.now().isoformat(),
                    points,
                    author_name,
                    datetime.now().isoformat()
                )
            )

            conn.commit()

        logger.info(f"Awarded {points} points to user {author_name} ({author_id}) in guild {guild_id}")
        return True
    except Exception as e:
        logger.error(f"Error awarding points to user {author_id}: {str(e)}", exc_info=True)
        return False

def get_user_points(author_id: str, guild_id: str) -> int:
    """
    Get the total points for a specific user in a guild.

    Args:
        author_id (str): The Discord user ID
        guild_id (str): The Discord guild ID

    Returns:
        int: Total points for the user
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT total_points FROM user_points WHERE author_id = ? AND guild_id = ?",
                (author_id, guild_id)
            )

            row = cursor.fetchone()
            if row:
                return row['total_points']
            return 0
    except Exception as e:
        logger.error(f"Error getting points for user {author_id}: {str(e)}", exc_info=True)
        return 0

def get_leaderboard(guild_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get the top users by points in a guild.

    Args:
        guild_id (str): The Discord guild ID
        limit (int): Maximum number of users to return

    Returns:
        List[Dict[str, Any]]: List of users with their points
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT author_id, author_name, total_points, last_updated
                FROM user_points
                WHERE guild_id = ?
                ORDER BY total_points DESC
                LIMIT ?
                """,
                (guild_id, limit)
            )

            leaderboard = []
            for row in cursor.fetchall():
                leaderboard.append({
                    'author_id': row['author_id'],
                    'author_name': row['author_name'],
                    'total_points': row['total_points'],
                    'last_updated': row['last_updated']
                })

        logger.info(f"Retrieved leaderboard for guild {guild_id} with {len(leaderboard)} users")
        return leaderboard
    except Exception as e:
        logger.error(f"Error getting leaderboard for guild {guild_id}: {str(e)}", exc_info=True)
        return []


def get_user_engagement_metrics(
    guild_id: str,
    start_time: datetime,
    end_time: datetime
) -> Dict[str, Dict[str, Any]]:
    """
    Calculate engagement metrics for users based on replies to their messages.

    This helps identify users whose messages sparked discussions, even if they
    didn't post many messages themselves.

    Args:
        guild_id (str): The Discord guild ID
        start_time (datetime): Start of the time range
        end_time (datetime): End of the time range

    Returns:
        Dict[str, Dict[str, Any]]: Dictionary mapping author_id to engagement metrics:
            - author_name: The username
            - message_count: Number of messages they posted
            - replies_received: Number of replies their messages received
            - unique_repliers: Number of unique users who replied to them
            - replies_given: Number of replies they gave to other users' messages
            - mentions_received: Number of @mentions they received from others
            - mentions_given: Number of @mentions they gave to others
            - engagement_score: Calculated engagement score (replies weighted more than messages)
    """
    try:
        start_time_str = start_time.replace(tzinfo=None).isoformat()
        end_time_str = end_time.replace(tzinfo=None).isoformat()

        with get_connection() as conn:
            cursor = conn.cursor()

            # Get all messages in the time range for this guild
            cursor.execute(
                """
                SELECT id, author_id, author_name, reply_to_message_id, content
                FROM messages
                WHERE guild_id = ?
                AND is_bot = 0
                AND is_command = 0
                AND (
                    datetime(created_at) BETWEEN datetime(?) AND datetime(?)
                    OR datetime(substr(created_at, 1, 19)) BETWEEN datetime(?) AND datetime(?)
                )
                """,
                (guild_id, start_time_str, end_time_str, start_time_str, end_time_str)
            )

            messages = cursor.fetchall()

            # Build a map of message_id -> author_id for messages in this time range
            # Also build author_id -> author_id map for mention detection
            message_authors = {}
            user_message_counts = {}
            user_names = {}
            author_id_set = set()  # All author IDs in this time range

            for row in messages:
                msg_id = row['id']
                author_id = row['author_id']
                author_name = row['author_name']

                message_authors[msg_id] = author_id
                user_message_counts[author_id] = user_message_counts.get(author_id, 0) + 1
                user_names[author_id] = author_name
                author_id_set.add(author_id)

            # Count replies to each user's messages
            # Also count @mentions as a form of engagement (when someone mentions another user)
            user_replies_received = {}  # author_id -> count of replies
            user_unique_repliers = {}   # author_id -> set of replier author_ids
            user_replies_given = {}     # author_id -> count of replies they gave to others
            user_mentions_received = {} # author_id -> count of @mentions they received
            user_mentions_given = {}    # author_id -> count of @mentions they gave

            # Regex to find Discord user mentions: <@user_id> or <@!user_id>
            import re
            mention_pattern = re.compile(r'<@!?(\d+)>')

            for row in messages:
                reply_to_id = row['reply_to_message_id']
                replier_id = row['author_id']
                content = row['content'] or ''

                # Track explicit replies
                if reply_to_id and reply_to_id in message_authors:
                    original_author_id = message_authors[reply_to_id]

                    # Don't count self-replies
                    if original_author_id != replier_id:
                        user_replies_received[original_author_id] = \
                            user_replies_received.get(original_author_id, 0) + 1

                        if original_author_id not in user_unique_repliers:
                            user_unique_repliers[original_author_id] = set()
                        user_unique_repliers[original_author_id].add(replier_id)

                        # Track that this user gave a reply to someone else
                        user_replies_given[replier_id] = \
                            user_replies_given.get(replier_id, 0) + 1

                # Track @mentions as an additional engagement signal
                # This catches responses written without using the reply button
                mentioned_ids = mention_pattern.findall(content)
                for mentioned_id in mentioned_ids:
                    # Only count mentions of users who are active in this time period
                    # and don't count self-mentions
                    if mentioned_id in author_id_set and mentioned_id != replier_id:
                        user_mentions_received[mentioned_id] = \
                            user_mentions_received.get(mentioned_id, 0) + 1
                        user_mentions_given[replier_id] = \
                            user_mentions_given.get(replier_id, 0) + 1

            # Build the result with engagement scores
            result = {}
            all_author_ids = set(user_message_counts.keys())

            for author_id in all_author_ids:
                message_count = user_message_counts.get(author_id, 0)
                replies_received = user_replies_received.get(author_id, 0)
                unique_repliers = len(user_unique_repliers.get(author_id, set()))
                replies_given = user_replies_given.get(author_id, 0)
                mentions_received = user_mentions_received.get(author_id, 0)
                mentions_given = user_mentions_given.get(author_id, 0)

                # Engagement score formula:
                # - Each reply received is worth 3 points (shows their content sparked discussion)
                # - Each unique replier adds 2 bonus points (shows broad engagement)
                # - Each reply given to others is worth 2 points (shows they're helping others)
                # - Each @mention received is worth 2 points (someone addressed them directly)
                # - Each @mention given is worth 1 point (they're engaging with others)
                # - Each message sent is worth 1 point (baseline activity)
                # This rewards quality engagement over quantity
                engagement_score = (
                    (replies_received * 3) +
                    (unique_repliers * 2) +
                    (replies_given * 2) +
                    (mentions_received * 2) +
                    (mentions_given * 1) +
                    message_count
                )

                result[author_id] = {
                    'author_name': user_names.get(author_id, 'Unknown'),
                    'message_count': message_count,
                    'replies_received': replies_received,
                    'unique_repliers': unique_repliers,
                    'replies_given': replies_given,
                    'mentions_received': mentions_received,
                    'mentions_given': mentions_given,
                    'engagement_score': engagement_score
                }

            logger.info(f"Calculated engagement metrics for {len(result)} users in guild {guild_id}")
            return result

    except Exception as e:
        logger.error(f"Error calculating engagement metrics for guild {guild_id}: {str(e)}", exc_info=True)
        return {}


def store_daily_point_award(
    author_id: str,
    author_name: str,
    guild_id: str,
    date: datetime,
    points: int,
    reason: str
) -> bool:
    """
    Store a record of points awarded to a user on a specific date.

    Args:
        author_id (str): The Discord user ID
        author_name (str): The username
        guild_id (str): The Discord guild ID
        date (datetime): The date of the award
        points (int): Number of points awarded (must be 1-20)
        reason (str): Reason for the award

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Validate author_id is present
        if not author_id or not author_id.strip():
            logger.error("Cannot store daily point award: author_id is empty or None")
            return False

        # Validate points are within acceptable range (1-20)
        if points <= 0:
            logger.warning(f"Skipping award for {author_name}: points={points} (must be > 0)")
            return False

        if points > 20:
            logger.warning(f"Clamping points for {author_name} from {points} to 20 (max per user)")
            points = 20

        date_str = date.strftime('%Y-%m-%d')

        with get_connection() as conn:
            cursor = conn.cursor()

            # Check if award already exists for this user/guild/date
            cursor.execute(
                """
                SELECT points_awarded FROM daily_point_awards
                WHERE author_id = ? AND guild_id = ? AND date = ?
                """,
                (author_id, guild_id, date_str)
            )

            existing = cursor.fetchone()
            if existing:
                logger.warning(f"Points already awarded to {author_name} ({author_id}) on {date_str}. Skipping duplicate.")
                return False

            cursor.execute(
                """
                INSERT INTO daily_point_awards (
                    author_id, author_name, guild_id, date, points_awarded, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    author_id,
                    author_name,
                    guild_id,
                    date_str,
                    points,
                    reason,
                    datetime.now().isoformat()
                )
            )

            conn.commit()

        logger.info(f"Stored daily point award for {author_name} ({author_id}): {points} points for {reason}")
        return True
    except sqlite3.IntegrityError as e:
        # This handles the UNIQUE constraint violation as a backup
        logger.warning(f"Duplicate daily point award prevented for {author_name} ({author_id}) on {date.strftime('%Y-%m-%d')}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error storing daily point award: {str(e)}", exc_info=True)
        return False

def get_daily_point_awards(guild_id: str, date: datetime) -> List[Dict[str, Any]]:
    """
    Get all point awards for a specific date in a guild.

    Args:
        guild_id (str): The Discord guild ID
        date (datetime): The date to retrieve awards for

    Returns:
        List[Dict[str, Any]]: List of point awards for that date
    """
    try:
        date_str = date.strftime('%Y-%m-%d')

        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT author_id, author_name, points_awarded, reason, created_at
                FROM daily_point_awards
                WHERE guild_id = ? AND date = ?
                ORDER BY points_awarded DESC
                """,
                (guild_id, date_str)
            )

            awards = []
            for row in cursor.fetchall():
                awards.append({
                    'author_id': row['author_id'],
                    'author_name': row['author_name'],
                    'points_awarded': row['points_awarded'],
                    'reason': row['reason'],
                    'created_at': row['created_at']
                })

        logger.info(f"Retrieved {len(awards)} point awards for guild {guild_id} on {date_str}")
        return awards
    except Exception as e:
        logger.error(f"Error getting daily point awards: {str(e)}", exc_info=True)
        return []


def search_messages_by_keywords(
    keywords: List[str],
    guild_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    hours: Optional[int] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Search messages by keywords, optionally within a time range.

    Args:
        keywords: List of keywords to search for (uses OR matching)
        guild_id: Optional guild ID to filter by
        channel_id: Optional channel ID to filter by
        hours: Optional number of hours to look back (if None, no time filter applied)
        limit: Maximum number of messages to return (default: 50)

    Returns:
        List of messages matching the search criteria
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            # Build the query with keyword matching
            # Use LIKE for each keyword with OR logic
            keyword_conditions = []
            keyword_params = []

            for keyword in keywords:
                keyword_conditions.append("LOWER(content) LIKE ?")
                keyword_params.append(f"%{keyword.lower()}%")

            keyword_clause = " OR ".join(keyword_conditions)

            # Build the full query
            query = """
                SELECT
                    id, author_id, author_name, channel_id, channel_name,
                    guild_id, guild_name, content, created_at, is_bot, is_command,
                    scraped_url, scraped_content_summary, scraped_content_key_points,
                    image_descriptions
                FROM messages
                WHERE is_command = 0
                AND is_bot = 0
            """
            params = []

            # Add time filter only if hours is specified
            if hours is not None:
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(hours=hours)
                start_time_str = start_time.replace(tzinfo=None).isoformat()
                end_time_str = end_time.replace(tzinfo=None).isoformat()
                query += """
                AND (
                    datetime(created_at) BETWEEN datetime(?) AND datetime(?)
                    OR datetime(substr(created_at, 1, 19)) BETWEEN datetime(?) AND datetime(?)
                )
                """
                params.extend([start_time_str, end_time_str, start_time_str, end_time_str])

            # Add keyword filter
            query += f" AND ({keyword_clause})"
            params.extend(keyword_params)

            # Add optional filters
            if guild_id:
                query += " AND guild_id = ?"
                params.append(guild_id)

            if channel_id:
                query += " AND channel_id = ?"
                params.append(channel_id)

            # Order by relevance (more recent first) and limit
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)

            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'id': row['id'],
                    'author_id': row['author_id'],
                    'author_name': row['author_name'],
                    'channel_id': row['channel_id'],
                    'channel_name': row['channel_name'],
                    'guild_id': row['guild_id'],
                    'guild_name': row['guild_name'],
                    'content': row['content'],
                    'created_at': datetime.fromisoformat(row['created_at']),
                    'is_bot': bool(row['is_bot']),
                    'is_command': bool(row['is_command']),
                    'scraped_url': row['scraped_url'],
                    'scraped_content_summary': row['scraped_content_summary'],
                    'scraped_content_key_points': row['scraped_content_key_points'],
                    'image_descriptions': row['image_descriptions']
                })

        logger.info(f"Found {len(messages)} messages matching keywords: {keywords}")
        return messages

    except Exception as e:
        logger.error(f"Error searching messages by keywords: {str(e)}", exc_info=True)
        return []


def get_recent_messages_for_context(
    guild_id: str,
    channel_id: Optional[str] = None,
    hours: Optional[int] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get recent messages for providing context to the LLM.

    Args:
        guild_id: The guild ID to get messages from
        channel_id: Optional channel ID to filter by (if None, gets from all channels)
        hours: Optional number of hours to look back (if None, no time filter applied)
        limit: Maximum number of messages to return (default: 100)

    Returns:
        List of recent messages sorted by time (oldest first for conversation flow)
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT
                    id, author_id, author_name, channel_id, channel_name,
                    guild_id, guild_name, content, created_at, is_bot, is_command,
                    scraped_url, scraped_content_summary, scraped_content_key_points,
                    image_descriptions
                FROM messages
                WHERE guild_id = ?
                AND is_command = 0
            """
            params = [guild_id]

            # Add time filter only if hours is specified
            if hours is not None:
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(hours=hours)
                start_time_str = start_time.replace(tzinfo=None).isoformat()
                end_time_str = end_time.replace(tzinfo=None).isoformat()
                query += """
                AND (
                    datetime(created_at) BETWEEN datetime(?) AND datetime(?)
                    OR datetime(substr(created_at, 1, 19)) BETWEEN datetime(?) AND datetime(?)
                )
                """
                params.extend([start_time_str, end_time_str, start_time_str, end_time_str])

            if channel_id:
                query += " AND channel_id = ?"
                params.append(channel_id)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)

            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'id': row['id'],
                    'author_id': row['author_id'],
                    'author_name': row['author_name'],
                    'channel_id': row['channel_id'],
                    'channel_name': row['channel_name'],
                    'guild_id': row['guild_id'],
                    'guild_name': row['guild_name'],
                    'content': row['content'],
                    'created_at': datetime.fromisoformat(row['created_at']),
                    'is_bot': bool(row['is_bot']),
                    'is_command': bool(row['is_command']),
                    'scraped_url': row['scraped_url'],
                    'scraped_content_summary': row['scraped_content_summary'],
                    'scraped_content_key_points': row['scraped_content_key_points'],
                    'image_descriptions': row['image_descriptions']
                })

        # Reverse to get chronological order (oldest first)
        messages.reverse()
        logger.info(f"Retrieved {len(messages)} recent messages for context in guild {guild_id}")
        return messages

    except Exception as e:
        logger.error(f"Error getting recent messages for context: {str(e)}", exc_info=True)
        return []


# ==================== User Role Colors Functions ====================

def set_user_role_color(
    author_id: str,
    author_name: str,
    guild_id: str,
    role_id: str,
    color_hex: str,
    color_name: str,
    points_per_day: int
) -> bool:
    """
    Set or update a user's active role color.

    Args:
        author_id: The Discord user ID
        author_name: The username
        guild_id: The Discord guild ID
        role_id: The Discord role ID assigned to the user
        color_hex: The hex color code (e.g., "#FF5733")
        color_name: Human-readable color name
        points_per_day: Points to deduct per day

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        now = datetime.now(timezone.utc)
        today_str = now.strftime('%Y-%m-%d')

        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO user_role_colors (
                    author_id, author_name, guild_id, role_id, color_hex,
                    color_name, points_per_day, started_at, last_charged_date, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(author_id, guild_id) DO UPDATE SET
                    author_name = ?,
                    role_id = ?,
                    color_hex = ?,
                    color_name = ?,
                    points_per_day = ?,
                    started_at = ?,
                    last_charged_date = ?
                """,
                (
                    author_id, author_name, guild_id, role_id, color_hex,
                    color_name, points_per_day, now.isoformat(), today_str, now.isoformat(),
                    author_name, role_id, color_hex, color_name, points_per_day,
                    now.isoformat(), today_str
                )
            )

            conn.commit()

        logger.info(f"Set role color {color_name} ({color_hex}) for user {author_name} ({author_id})")
        return True
    except Exception as e:
        logger.error(f"Error setting role color for user {author_id}: {str(e)}", exc_info=True)
        return False


def get_user_role_color(author_id: str, guild_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a user's active role color.

    Args:
        author_id: The Discord user ID
        guild_id: The Discord guild ID

    Returns:
        Dict with role color info or None if not found
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT author_id, author_name, guild_id, role_id, color_hex,
                       color_name, points_per_day, started_at, last_charged_date, created_at
                FROM user_role_colors
                WHERE author_id = ? AND guild_id = ?
                """,
                (author_id, guild_id)
            )

            row = cursor.fetchone()
            if row:
                return {
                    'author_id': row['author_id'],
                    'author_name': row['author_name'],
                    'guild_id': row['guild_id'],
                    'role_id': row['role_id'],
                    'color_hex': row['color_hex'],
                    'color_name': row['color_name'],
                    'points_per_day': row['points_per_day'],
                    'started_at': row['started_at'],
                    'last_charged_date': row['last_charged_date'],
                    'created_at': row['created_at']
                }
            return None
    except Exception as e:
        logger.error(f"Error getting role color for user {author_id}: {str(e)}", exc_info=True)
        return None


def remove_user_role_color(author_id: str, guild_id: str) -> bool:
    """
    Remove a user's active role color.

    Args:
        author_id: The Discord user ID
        guild_id: The Discord guild ID

    Returns:
        bool: True if removed, False otherwise
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM user_role_colors WHERE author_id = ? AND guild_id = ?",
                (author_id, guild_id)
            )

            rows_affected = cursor.rowcount
            conn.commit()

        if rows_affected > 0:
            logger.info(f"Removed role color for user {author_id} in guild {guild_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error removing role color for user {author_id}: {str(e)}", exc_info=True)
        return False


def get_all_active_role_colors(guild_id: str) -> List[Dict[str, Any]]:
    """
    Get all active role colors for a guild.

    Args:
        guild_id: The Discord guild ID

    Returns:
        List of role color records
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT author_id, author_name, guild_id, role_id, color_hex,
                       color_name, points_per_day, started_at, last_charged_date, created_at
                FROM user_role_colors
                WHERE guild_id = ?
                """,
                (guild_id,)
            )

            results = []
            for row in cursor.fetchall():
                results.append({
                    'author_id': row['author_id'],
                    'author_name': row['author_name'],
                    'guild_id': row['guild_id'],
                    'role_id': row['role_id'],
                    'color_hex': row['color_hex'],
                    'color_name': row['color_name'],
                    'points_per_day': row['points_per_day'],
                    'started_at': row['started_at'],
                    'last_charged_date': row['last_charged_date'],
                    'created_at': row['created_at']
                })

        logger.info(f"Retrieved {len(results)} active role colors for guild {guild_id}")
        return results
    except Exception as e:
        logger.error(f"Error getting active role colors for guild {guild_id}: {str(e)}", exc_info=True)
        return []


def update_role_color_last_charged(author_id: str, guild_id: str, date_str: str) -> bool:
    """
    Update the last charged date for a user's role color.

    Args:
        author_id: The Discord user ID
        guild_id: The Discord guild ID
        date_str: The date string (YYYY-MM-DD format)

    Returns:
        bool: True if updated, False otherwise
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE user_role_colors
                SET last_charged_date = ?
                WHERE author_id = ? AND guild_id = ?
                """,
                (date_str, author_id, guild_id)
            )

            rows_affected = cursor.rowcount
            conn.commit()

        return rows_affected > 0
    except Exception as e:
        logger.error(f"Error updating last charged date for user {author_id}: {str(e)}", exc_info=True)
        return False


def deduct_user_points(author_id: str, guild_id: str, points: int) -> bool:
    """
    Deduct points from a user's total using atomic operation to prevent race conditions.

    Args:
        author_id: The Discord user ID
        guild_id: The Discord guild ID
        points: Number of points to deduct

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Validate points is positive
        if points <= 0:
            logger.warning(f"Cannot deduct non-positive points ({points}) from user {author_id}")
            return False

        with get_connection() as conn:
            cursor = conn.cursor()

            # Atomic update: only deduct if user has enough points
            # This prevents race conditions where multiple concurrent requests
            # could overdraft the user's points
            cursor.execute(
                """
                UPDATE user_points
                SET total_points = total_points - ?,
                    last_updated = ?
                WHERE author_id = ? AND guild_id = ? AND total_points >= ?
                """,
                (points, datetime.now().isoformat(), author_id, guild_id, points)
            )

            rows_affected = cursor.rowcount
            conn.commit()

        if rows_affected == 0:
            # Either user doesn't exist or has insufficient points
            logger.warning(f"Could not deduct {points} points from user {author_id} in guild {guild_id} (insufficient points or user not found)")
            return False

        logger.info(f"Deducted {points} points from user {author_id} in guild {guild_id}")
        return True
    except Exception as e:
        logger.error(f"Error deducting points from user {author_id}: {str(e)}", exc_info=True)
        return False


def get_all_guilds_with_role_colors() -> List[str]:
    """
    Get all guild IDs that have active role colors.

    Returns:
        List of guild IDs
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT DISTINCT guild_id FROM user_role_colors"
            )

            return [row['guild_id'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting guilds with role colors: {str(e)}", exc_info=True)
        return []
