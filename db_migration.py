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
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            # Check if columns already exist
            cursor.execute("PRAGMA table_info(messages)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Define allowlisted columns and their types for security
            ALLOWED_COLUMNS = {
                'scraped_url': 'TEXT',
                'scraped_content_summary': 'TEXT',
                'scraped_content_key_points': 'TEXT'
            }
            
            # Add missing columns using allowlisted values only
            columns_to_add = []
            for column_name, column_type in ALLOWED_COLUMNS.items():
                if column_name not in columns:
                    columns_to_add.append((column_name, column_type))
            
            # Execute ALTER TABLE statements with allowlisted values
            for column_name, column_type in columns_to_add:
                # Validate that column_name and column_type are in our allowlist
                if column_name in ALLOWED_COLUMNS and ALLOWED_COLUMNS[column_name] == column_type:
                    logger.info(f"Adding column {column_name} to messages table")
                    # Use parameterized query construction with allowlisted values
                    sql = f"ALTER TABLE messages ADD COLUMN {column_name} {column_type}"
                    cursor.execute(sql)
                else:
                    logger.error(f"Attempted to add non-allowlisted column: {column_name} {column_type}")
                    return False
            
            # explicit commit is optional; context-manager also commits on success
            conn.commit()
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
