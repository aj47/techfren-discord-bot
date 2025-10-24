"""
Database migration script to add missing columns to the messages table.
"""

import sqlite3
import os
import logging
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("db_migration")

# Database constants
DB_DIRECTORY = "data"
DB_FILE = os.path.join(DB_DIRECTORY, "discord_messages.db")


def migrate_database():
    """
    Add missing columns to the messages table and create thread memory tables.
    """
    try:
        # Check if database file exists
        if not os.path.exists(DB_FILE):
            logger.error(f"Database file not found: {DB_FILE}")
            return False

        # Connect to the database
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            # Check if columns already exist
            cursor.execute("PRAGMA table_info(messages)")
            columns = [column[1] for column in cursor.fetchall()]

            # Add missing columns
            columns_to_add = []
            if "scraped_url" not in columns:
                columns_to_add.append(("scraped_url", "TEXT"))
            if "scraped_content_summary" not in columns:
                columns_to_add.append(("scraped_content_summary", "TEXT"))
            if "scraped_content_key_points" not in columns:
                columns_to_add.append(("scraped_content_key_points", "TEXT"))

            # Execute ALTER TABLE statements
            for column_name, column_type in columns_to_add:
                logger.info(f"Adding column {column_name} to messages table")
                cursor.execute(
                    f"ALTER TABLE messages ADD COLUMN {column_name} {column_type}"
                )

            # explicit commit is optional; context-manager also commits on success
            conn.commit()
        if columns_to_add:
            logger.info(
                f"Successfully added {len(columns_to_add)} columns to messages table"
            )
        else:
            logger.info("No columns needed to be added")

        # Create thread memory tables
        migrate_thread_memory_tables()

        return True
    except Exception as e:
        logger.error(f"Error migrating database: {str(e)}", exc_info=True)
        return False


def migrate_thread_memory_tables():
    """
    Create thread memory tables if they don't exist.
    """
    try:
        with sqlite3.connect(DB_FILE) as conn:
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
                    context_data TEXT,
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

            # Create thread_metadata table
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
                    thread_type TEXT DEFAULT 'conversation'
                )
            """
            )

            conn.commit()
            logger.info("Thread memory tables created/verified successfully")

    except Exception as e:
        logger.error(f"Error creating thread memory tables: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    success = migrate_database()
    sys.exit(0 if success else 1)
