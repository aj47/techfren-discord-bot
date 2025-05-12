"""
Database module for the Discord bot.
Handles libSQL database operations for storing messages and channel summaries.
"""

import libsql_client as libsql
import os
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set

# Set up logging
logger = logging.getLogger('discord_bot.database')

# Database constants
DB_DIRECTORY = "data"
DB_FILE = os.path.join(DB_DIRECTORY, "discord_messages.turso")
DB_URL = None
DB_AUTH_TOKEN = None

# Load Turso DB credentials
try:
    with open('keys.json', 'r') as f:
        keys_data = json.load(f)
        if 'turso_db' in keys_data:
            DB_URL = keys_data['turso_db']['url']
            DB_AUTH_TOKEN = keys_data['turso_db']['auth_token']
            logger.info("Loaded Turso DB credentials")
except Exception as e:
    logger.warning(f"Could not load Turso DB credentials: {e}")

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
    command_type TEXT
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

CREATE_SCRAPED_LINKS_TABLE = """
CREATE TABLE IF NOT EXISTS scraped_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    content TEXT,
    metadata TEXT, -- JSON string for additional metadata from Firecrawl
    first_scraped_at TIMESTAMP NOT NULL,
    last_updated_at TIMESTAMP NOT NULL
);
"""

CREATE_FRONTEND_ENTRIES_TABLE = """
CREATE TABLE IF NOT EXISTS frontend_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK(status IN ('proprietary', 'opensource', 'freemium', 'unknown')),
    github_url TEXT,
    website_url TEXT,
    rating REAL CHECK(rating >= 0 AND rating <= 10),
    rating_source TEXT,
    discord_submitter TEXT,
    discord_submitter_id TEXT,
    category TEXT,
    tags TEXT, -- JSON array of tags
    logo_url TEXT,
    repository_stars INTEGER,
    pricing_info TEXT,
    notes TEXT,
    related_urls TEXT, -- JSON array of related URLs
    created_at TIMESTAMP NOT NULL,
    last_updated_at TIMESTAMP NOT NULL
);
"""

CREATE_INDEX_AUTHOR = "CREATE INDEX IF NOT EXISTS idx_author_id ON messages (author_id);"
CREATE_INDEX_CHANNEL = "CREATE INDEX IF NOT EXISTS idx_channel_id ON messages (channel_id);"
CREATE_INDEX_GUILD = "CREATE INDEX IF NOT EXISTS idx_guild_id ON messages (guild_id);"
CREATE_INDEX_CREATED = "CREATE INDEX IF NOT EXISTS idx_created_at ON messages (created_at);"
CREATE_INDEX_COMMAND = "CREATE INDEX IF NOT EXISTS idx_is_command ON messages (is_command);"
CREATE_INDEX_SUMMARY_CHANNEL = "CREATE INDEX IF NOT EXISTS idx_summary_channel_id ON channel_summaries (channel_id);"
CREATE_INDEX_SUMMARY_DATE = "CREATE INDEX IF NOT EXISTS idx_summary_date ON channel_summaries (date);"
CREATE_INDEX_SCRAPED_URL = "CREATE INDEX IF NOT EXISTS idx_scraped_url ON scraped_links (url);"
CREATE_INDEX_FRONTEND_NAME = "CREATE INDEX IF NOT EXISTS idx_frontend_entries_name ON frontend_entries (name);"
CREATE_INDEX_FRONTEND_STATUS = "CREATE INDEX IF NOT EXISTS idx_frontend_entries_status ON frontend_entries (status);"
CREATE_INDEX_FRONTEND_CATEGORY = "CREATE INDEX IF NOT EXISTS idx_frontend_entries_category ON frontend_entries (category);"
CREATE_INDEX_FRONTEND_SUBMITTER = "CREATE INDEX IF NOT EXISTS idx_frontend_entries_submitter_id ON frontend_entries (discord_submitter_id);"

INSERT_MESSAGE = """
INSERT INTO messages (
    id, author_id, author_name, channel_id, channel_name,
    guild_id, guild_name, content, created_at, is_bot, is_command, command_type
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

INSERT_CHANNEL_SUMMARY = """
INSERT INTO channel_summaries (
    channel_id, channel_name, guild_id, guild_name, date,
    summary_text, message_count, active_users, active_users_list,
    created_at, metadata
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

INSERT_SCRAPED_LINK = """
INSERT INTO scraped_links (url, content, metadata, first_scraped_at, last_updated_at)
VALUES (?, ?, ?, ?, ?);
"""

INSERT_FRONTEND_ENTRY = """
INSERT INTO frontend_entries (
    name, description, status, github_url, website_url, rating, rating_source,
    discord_submitter, discord_submitter_id, category, tags, logo_url,
    repository_stars, pricing_info, notes, related_urls, created_at, last_updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

UPDATE_SCRAPED_LINK = """
UPDATE scraped_links
SET content = ?, metadata = ?, last_updated_at = ?
WHERE url = ?;
"""

UPDATE_FRONTEND_ENTRY = """
UPDATE frontend_entries
SET description = ?, status = ?, github_url = ?, website_url = ?, rating = ?,
    rating_source = ?, category = ?, tags = ?, logo_url = ?, repository_stars = ?,
    pricing_info = ?, notes = ?, related_urls = ?, last_updated_at = ?
WHERE id = ?;
"""

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
        with get_connection() as conn:
            cursor = conn.cursor()

            # Create tables and indexes
            cursor.execute(CREATE_MESSAGES_TABLE)
            cursor.execute(CREATE_CHANNEL_SUMMARIES_TABLE)
            cursor.execute(CREATE_SCRAPED_LINKS_TABLE)
            cursor.execute(CREATE_FRONTEND_ENTRIES_TABLE)

            # Create indexes for messages table
            cursor.execute(CREATE_INDEX_AUTHOR)
            cursor.execute(CREATE_INDEX_CHANNEL)
            cursor.execute(CREATE_INDEX_GUILD)
            cursor.execute(CREATE_INDEX_CREATED)
            cursor.execute(CREATE_INDEX_COMMAND)

            # Create indexes for channel_summaries table
            cursor.execute(CREATE_INDEX_SUMMARY_CHANNEL)
            cursor.execute(CREATE_INDEX_SUMMARY_DATE)

            # Create index for scraped_links table
            cursor.execute(CREATE_INDEX_SCRAPED_URL)

            # Create indexes for frontend_entries table
            cursor.execute(CREATE_INDEX_FRONTEND_NAME)
            cursor.execute(CREATE_INDEX_FRONTEND_STATUS)
            cursor.execute(CREATE_INDEX_FRONTEND_CATEGORY)
            cursor.execute(CREATE_INDEX_FRONTEND_SUBMITTER)

            conn.commit()

        logger.info(f"Database initialized successfully at {DB_FILE}")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}", exc_info=True)
        raise

def get_connection() -> libsql.Connection:
    """Get a connection to the libSQL database, using Turso if configured."""
    # If Turso credentials are available, use them
    if DB_URL and DB_AUTH_TOKEN:
        logger.debug("Connecting to Turso database using URL")
        try:
            conn = libsql.connect(
                url=DB_URL,
                auth_token=DB_AUTH_TOKEN
            )
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to Turso database: {e}")
            # Fall back to local file if remote connection fails
            logger.warning("Falling back to local database file")
    
    # Otherwise, use local file
    if not os.path.exists(DB_FILE):
        logger.warning(f"Database file not found at {DB_FILE}, creating directory")
        os.makedirs(DB_DIRECTORY, exist_ok=True)
    
    logger.debug("Connecting to local libSQL database")
    conn = libsql.connect(DB_FILE)
    return conn

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
    command_type: Optional[str] = None
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

    Returns:
        bool: True if the message was stored successfully, False otherwise
    """
    try:
        # Use context manager to ensure connection is properly closed
        with get_connection() as conn:
            cursor = conn.cursor()

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
                    created_at.isoformat(),
                    1 if is_bot else 0,
                    1 if is_command else 0,
                    command_type
                )
            )

            conn.commit()

        logger.debug(f"Message {message_id} stored in database")
        return True
    except libsql.IntegrityError:
        # This could happen if we try to insert a message with the same ID twice
        logger.warning(f"Message {message_id} already exists in database")
        return False
    except Exception as e:
        logger.error(f"Error storing message {message_id}: {str(e)}", exc_info=True)
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

def get_channel_messages_for_day(channel_id: str, date: datetime) -> List[Dict[str, Any]]:
    """
    Get all messages from a specific channel for a specific day.

    Args:
        channel_id (str): The Discord channel ID
        date (datetime): The date to get messages for

    Returns:
        List[Dict[str, Any]]: A list of messages as dictionaries
    """
    try:
        # Calculate start and end of the day
        start_date = datetime(date.year, date.month, date.day, 0, 0, 0).isoformat()
        end_date = datetime(date.year, date.month, date.day, 23, 59, 59, 999999).isoformat()

        with get_connection() as conn:
            cursor = conn.cursor()

            # Query messages for the channel within the date range
            cursor.execute(
                """
                SELECT author_name, content, created_at, is_bot, is_command
                FROM messages
                WHERE channel_id = ? AND created_at BETWEEN ? AND ?
                ORDER BY created_at ASC
                """,
                (channel_id, start_date, end_date)
            )

            # Convert rows to dictionaries
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'author_name': row['author_name'],
                    'content': row['content'],
                    'created_at': datetime.fromisoformat(row['created_at']),
                    'is_bot': bool(row['is_bot']),
                    'is_command': bool(row['is_command'])
                })

        logger.info(f"Retrieved {len(messages)} messages from channel {channel_id} for {date.strftime('%Y-%m-%d')}")
        return messages
    except Exception as e:
        logger.error(f"Error getting messages for channel {channel_id} on {date.strftime('%Y-%m-%d')}: {str(e)}", exc_info=True)
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
                    guild_id, guild_name, content, created_at, is_bot, is_command
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
                    'is_command': bool(row['is_command'])
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

def store_scraped_link(url: str, content: str, metadata: Optional[str] = None) -> bool:
    """Store a new scraped link in the database."""
    now = datetime.now().isoformat()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(INSERT_SCRAPED_LINK, (url, content, metadata, now, now))
            conn.commit()
        logger.info(f"Stored new scraped link: {url}")
        return True
    except libsql.IntegrityError:
        logger.warning(f"Scraped link {url} already exists. Use update_scraped_link to modify.")
        return False
    except Exception as e:
        logger.error(f"Error storing scraped link {url}: {e}", exc_info=True)
        return False

def get_scraped_link(url: str) -> Optional[Dict[str, Any]]:
    """Retrieve a scraped link from the database by URL."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, url, content, metadata, first_scraped_at, last_updated_at FROM scraped_links WHERE url = ?", (url,))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0], 'url': row[1], 'content': row[2], 
                    'metadata': row[3], 'first_scraped_at': row[4], 
                    'last_updated_at': row[5]
                }
    except Exception as e:
        logger.error(f"Error retrieving scraped link {url}: {e}", exc_info=True)
    return None

def update_scraped_link(url: str, content: str, metadata: Optional[str] = None) -> bool:
    """Update an existing scraped link's content and metadata."""
    now = datetime.now().isoformat()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(UPDATE_SCRAPED_LINK, (content, metadata, now, url))
            conn.commit()
        logger.info(f"Updated scraped link: {url}")
        return True
    except Exception as e:
        logger.error(f"Error updating scraped link {url}: {e}", exc_info=True)
        return False

def store_frontend_entry(
    name: str,
    description: str = None,
    status: str = "unknown",
    github_url: str = None,
    website_url: str = None,
    rating: float = None,
    rating_source: str = None,
    discord_submitter: str = None,
    discord_submitter_id: str = None,
    category: str = None,
    tags: List[str] = None,
    logo_url: str = None,
    repository_stars: int = None,
    pricing_info: str = None,
    notes: str = None,
    related_urls: List[str] = None
) -> bool:
    """Store a new frontend entry in the database."""
    now = datetime.now().isoformat()
    
    # Convert lists to JSON strings
    tags_json = json.dumps(tags) if tags else None
    related_urls_json = json.dumps(related_urls) if related_urls else None
    
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                INSERT_FRONTEND_ENTRY,
                (
                    name, description, status, github_url, website_url, rating, rating_source,
                    discord_submitter, discord_submitter_id, category, tags_json, logo_url,
                    repository_stars, pricing_info, notes, related_urls_json, now, now
                )
            )
            conn.commit()
        logger.info(f"Stored new frontend entry: {name}")
        return True
    except Exception as e:
        logger.error(f"Error storing frontend entry {name}: {e}", exc_info=True)
        return False

def get_frontend_entry(entry_id: int) -> Optional[Dict[str, Any]]:
    """Get a frontend entry by ID."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM frontend_entries WHERE id = ?", (entry_id,))
            row = cursor.fetchone()
            if not row:
                return None
                
            # Convert JSON strings back to lists
            entry = dict(zip([column[0] for column in cursor.description], row))
            if entry['tags']:
                entry['tags'] = json.loads(entry['tags'])
            if entry['related_urls']:
                entry['related_urls'] = json.loads(entry['related_urls'])
                
            return entry
    except Exception as e:
        logger.error(f"Error getting frontend entry {entry_id}: {e}", exc_info=True)
        return None

def get_frontend_entries_by_name(name: str) -> List[Dict[str, Any]]:
    """Get frontend entries that match or partially match the given name."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM frontend_entries WHERE name LIKE ?", (f"%{name}%",))
            rows = cursor.fetchall()
            
            entries = []
            column_names = [column[0] for column in cursor.description]
            
            for row in rows:
                entry = dict(zip(column_names, row))
                if entry['tags']:
                    entry['tags'] = json.loads(entry['tags'])
                if entry['related_urls']:
                    entry['related_urls'] = json.loads(entry['related_urls'])
                entries.append(entry)
                
            return entries
    except Exception as e:
        logger.error(f"Error getting frontend entries for name {name}: {e}", exc_info=True)
        return []

def update_frontend_entry(
    entry_id: int,
    description: str = None,
    status: str = None,
    github_url: str = None,
    website_url: str = None,
    rating: float = None,
    rating_source: str = None,
    category: str = None,
    tags: List[str] = None,
    logo_url: str = None,
    repository_stars: int = None,
    pricing_info: str = None,
    notes: str = None,
    related_urls: List[str] = None
) -> bool:
    """Update an existing frontend entry."""
    try:
        # First, get the current entry to preserve any values not being updated
        current_entry = get_frontend_entry(entry_id)
        if not current_entry:
            logger.error(f"Cannot update frontend entry {entry_id}: entry not found")
            return False
            
        # Use current values for any parameters that weren't specified
        description = description if description is not None else current_entry.get('description')
        status = status if status is not None else current_entry.get('status')
        github_url = github_url if github_url is not None else current_entry.get('github_url')
        website_url = website_url if website_url is not None else current_entry.get('website_url')
        rating = rating if rating is not None else current_entry.get('rating')
        rating_source = rating_source if rating_source is not None else current_entry.get('rating_source')
        category = category if category is not None else current_entry.get('category')
        tags = tags if tags is not None else current_entry.get('tags')
        logo_url = logo_url if logo_url is not None else current_entry.get('logo_url')
        repository_stars = repository_stars if repository_stars is not None else current_entry.get('repository_stars')
        pricing_info = pricing_info if pricing_info is not None else current_entry.get('pricing_info')
        notes = notes if notes is not None else current_entry.get('notes')
        related_urls = related_urls if related_urls is not None else current_entry.get('related_urls')
        
        # Convert lists to JSON strings
        tags_json = json.dumps(tags) if tags else None
        related_urls_json = json.dumps(related_urls) if related_urls else None
        
        now = datetime.now().isoformat()
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                UPDATE_FRONTEND_ENTRY,
                (
                    description, status, github_url, website_url, rating, rating_source,
                    category, tags_json, logo_url, repository_stars, pricing_info,
                    notes, related_urls_json, now, entry_id
                )
            )
            conn.commit()
            
        logger.info(f"Updated frontend entry {entry_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating frontend entry {entry_id}: {e}", exc_info=True)
        return False
