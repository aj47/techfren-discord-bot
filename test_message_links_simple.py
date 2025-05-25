#!/usr/bin/env python3
"""
Simple test script to verify that message link generation works.
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import store_message, get_channel_messages_for_day, init_database
from message_utils import generate_discord_message_link
from logging_config import logger

def test_message_links():
    """Test that message link generation works correctly."""
    logger.info("Starting test for message link generation...")
    
    # Initialize database
    init_database()
    
    # Test data
    guild_id = "123456789012345678"
    channel_id = "987654321098765432"
    channel_name = "test-channel"
    today = datetime.now(timezone.utc)
    
    # Test message link generation
    test_message_id = "msg123"
    test_link = generate_discord_message_link(guild_id, channel_id, test_message_id)
    expected_link = f"https://discord.com/channels/{guild_id}/{channel_id}/{test_message_id}"
    
    logger.info(f"Generated link: {test_link}")
    logger.info(f"Expected link: {expected_link}")
    
    if test_link == expected_link:
        logger.info("✓ Message link generation works correctly!")
    else:
        logger.error("✗ Message link generation failed!")
        return False
    
    # Test DM link generation (no guild_id)
    dm_link = generate_discord_message_link(None, channel_id, test_message_id)
    expected_dm_link = f"https://discord.com/channels/@me/{channel_id}/{test_message_id}"
    
    logger.info(f"Generated DM link: {dm_link}")
    logger.info(f"Expected DM link: {expected_dm_link}")
    
    if dm_link == expected_dm_link:
        logger.info("✓ DM message link generation works correctly!")
    else:
        logger.error("✗ DM message link generation failed!")
        return False
    
    # Create and store a test message
    test_message = {
        "id": "msg456",
        "author_id": "user1",
        "author_name": "TestUser1",
        "content": "This is a test message for link generation.",
        "created_at": today - timedelta(hours=1)
    }
    
    success = store_message(
        message_id=test_message["id"],
        author_id=test_message["author_id"],
        author_name=test_message["author_name"],
        channel_id=channel_id,
        channel_name=channel_name,
        content=test_message["content"],
        created_at=test_message["created_at"],
        guild_id=guild_id,
        guild_name="Test Guild"
    )
    
    if success:
        logger.info(f"✓ Stored test message {test_message['id']}")
    else:
        logger.error(f"✗ Failed to store test message {test_message['id']}")
        return False
    
    # Retrieve messages and check they have the required fields
    messages = get_channel_messages_for_day(channel_id, today)
    logger.info(f"Retrieved {len(messages)} messages for the day")
    
    if not messages:
        logger.warning("No messages found")
        return False
    
    # Check that messages include the required fields for link generation
    for msg in messages:
        logger.info(f"Message {msg.get('id', 'NO_ID')} fields: {list(msg.keys())}")
        
        required_fields = ['id', 'guild_id', 'channel_id']
        missing_fields = [field for field in required_fields if field not in msg]
        
        if not missing_fields:
            logger.info(f"✓ Message {msg['id']} has all required fields for link generation")
            
            # Generate a link for this message
            msg_link = generate_discord_message_link(msg['guild_id'], msg['channel_id'], msg['id'])
            logger.info(f"  Generated link: {msg_link}")
        else:
            logger.error(f"✗ Message missing required fields: {missing_fields}")
            return False
    
    logger.info("✓ All tests passed!")
    return True

if __name__ == "__main__":
    success = test_message_links()
    if not success:
        sys.exit(1)
