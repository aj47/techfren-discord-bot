import asyncio
import logging
import pytest
from datetime import datetime, timezone
from logging_config import logger
from database import init_database, store_message, update_message_with_scraped_data, get_channel_messages_for_day
from llm_handler import call_llm_for_summary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

@pytest.mark.asyncio
async def test_sum_day_with_links():
    """
    Test the sum-day command with messages containing links.
    This test simulates:
    1. Storing messages in the database, including one with a URL
    2. Updating the message with scraped content
    3. Retrieving messages for the day
    4. Generating a summary that includes the link content
    """
    logger.info("Starting sum-day with links test...")

    # Initialize the database
    init_database()

    # Current date for testing (use UTC)
    today = datetime.now(timezone.utc)

    # Test channel info
    channel_id = "test_channel_123"
    channel_name = "test-channel"

    # Store some test messages
    messages = [
        {
            "id": "msg1",
            "author_id": "user1",
            "author_name": "User One",
            "content": "Hello everyone!",
            "created_at": today.replace(hour=10, minute=0, second=0)
        },
        {
            "id": "msg2",
            "author_id": "user2",
            "author_name": "User Two",
            "content": "Check out this Twitter post: https://x.com/cline/status/1925002086405832987",
            "created_at": today.replace(hour=10, minute=15, second=0)
        },
        {
            "id": "msg3",
            "author_id": "user1",
            "author_name": "User One",
            "content": "That's really interesting!",
            "created_at": today.replace(hour=10, minute=30, second=0)
        }
    ]

    # Store the messages
    for msg in messages:
        success = store_message(
            message_id=msg["id"],
            author_id=msg["author_id"],
            author_name=msg["author_name"],
            channel_id=channel_id,
            channel_name=channel_name,
            content=msg["content"],
            created_at=msg["created_at"]
        )
        if success:
            logger.info(f"Stored message {msg['id']}")
        else:
            logger.warning(f"Failed to store message {msg['id']}")

    # Update the message with the URL to include scraped content
    url = "https://x.com/cline/status/1925002086405832987"
    summary = "Cline announced new Workflows feature in v3.16. Workflows are automation scripts that define a sequence of actions using natural language, Cline's tools, CLI commands, or MCPs within a Markdown file."
    key_points = [
        "Cline v3.16 introduces Workflows feature",
        "Workflows are automation scripts defined in Markdown files",
        "They can use Cline's tools, CLI commands, or MCPs",
        "Several users expressed excitement about the new feature"
    ]

    # Convert key points to JSON string
    import json
    key_points_json = json.dumps(key_points)

    # Update the message with scraped data
    success = await update_message_with_scraped_data(
        message_id="msg2",
        scraped_url=url,
        scraped_content_summary=summary,
        scraped_content_key_points=key_points_json
    )

    if success:
        logger.info(f"Updated message msg2 with scraped data")
    else:
        logger.warning(f"Failed to update message msg2 with scraped data")

    # Retrieve messages for the day
    messages = get_channel_messages_for_day(channel_id, today)
    logger.info(f"Retrieved {len(messages)} messages for the day")

    # Check if the scraped content is included in the retrieved messages
    for msg in messages:
        if msg.get('scraped_url'):
            logger.info(f"Found message with scraped URL: {msg.get('scraped_url')}")
            logger.info(f"Scraped summary: {msg.get('scraped_content_summary')}")
            logger.info(f"Scraped key points: {msg.get('scraped_content_key_points')}")

    # Generate a summary
    summary = await call_llm_for_summary(messages, channel_name, today)
    logger.info("Generated summary:")
    logger.info(summary)

    logger.info("Test completed!")

if __name__ == "__main__":
    asyncio.run(test_sum_day_with_links())
