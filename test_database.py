"""
Test script for the database module.
This script tests the database initialization and message storage functionality.
"""

import os
import sys
import logging
from datetime import datetime, timezone
import database

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('test_database')

def test_database_init():
    """Test database initialization"""
    logger.info("Testing database initialization...")
    try:
        database.init_database()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}", exc_info=True)
        return False

def test_message_storage():
    """Test message storage functionality"""
    logger.info("Testing message storage...")
    try:
        # Create a test message
        message_id = "test_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        author_id = "123456789"
        author_name = "Test User"
        channel_id = "987654321"
        channel_name = "test-channel"
        content = "This is a test message"
        created_at = datetime.now(timezone.utc)
        guild_id = "111222333"
        guild_name = "Test Guild"

        # Store the message
        success = database.store_message(
            message_id=message_id,
            author_id=author_id,
            author_name=author_name,
            channel_id=channel_id,
            channel_name=channel_name,
            content=content,
            created_at=created_at,
            guild_id=guild_id,
            guild_name=guild_name,
            is_bot=False,
            is_command=True,
            command_type="test"
        )

        if success:
            logger.info(f"Message {message_id} stored successfully")
        else:
            logger.error(f"Failed to store message {message_id}")
            return False

        # Get message count
        count = database.get_message_count()
        logger.info(f"Total message count: {count}")

        # Get user message count
        user_count = database.get_user_message_count(author_id)
        logger.info(f"User message count for {author_id}: {user_count}")

        return True
    except Exception as e:
        logger.error(f"Message storage test failed: {str(e)}", exc_info=True)
        return False

def main():
    """Run all tests"""
    logger.info("Starting database tests...")

    # Test database initialization
    if not test_database_init():
        logger.error("Database initialization test failed")
        return False

    # Test message storage
    if not test_message_storage():
        logger.error("Message storage test failed")
        return False

    logger.info("All tests completed successfully")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
