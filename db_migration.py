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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('db_migration')

# Database constants
DB_DIRECTORY = "data"
DB_FILE = os.path.join(DB_DIRECTORY, "discord_messages.db")

def migrate_database():
    """
    Add missing columns to the messages table.
    """
    try:
        # Check if database file exists
        if not os.path.exists(DB_FILE):
            logger.error(f"Database file not found: {DB_FILE}")
            return False

        # Connect to the database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add missing columns
        columns_to_add = []
        if 'scraped_url' not in columns:
            columns_to_add.append(("scraped_url", "TEXT"))
        if 'scraped_content_summary' not in columns:
            columns_to_add.append(("scraped_content_summary", "TEXT"))
        if 'scraped_content_key_points' not in columns:
            columns_to_add.append(("scraped_content_key_points", "TEXT"))
        
        # Execute ALTER TABLE statements
        for column_name, column_type in columns_to_add:
            logger.info(f"Adding column {column_name} to messages table")
            cursor.execute(f"ALTER TABLE messages ADD COLUMN {column_name} {column_type}")
        
        # Commit changes and close connection
        conn.commit()
        conn.close()
        
        if columns_to_add:
            logger.info(f"Successfully added {len(columns_to_add)} columns to messages table")
        else:
            logger.info("No columns needed to be added")
        
        return True
    except Exception as e:
        logger.error(f"Error migrating database: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    success = migrate_database()
    sys.exit(0 if success else 1)
