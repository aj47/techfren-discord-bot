"""
Test script to verify database performance improvements.
"""

import time
import asyncio
from datetime import datetime, timezone
from database import (
    init_database,
    store_message,
    store_messages_batch,
    get_channel_messages_for_hours,
)


def test_single_inserts():
    """Test performance of single message inserts."""
    print("\n=== Testing Single Inserts ===")
    channel_id = "perf_test_channel"
    start_time = time.time()

    for i in range(50):
        store_message(
            message_id=f"single_msg_{i}_{time.time()}",
            author_id="test_user",
            author_name="Test User",
            channel_id=channel_id,
            channel_name="Performance Test",
            content=f"Test message {i}",
            created_at=datetime.now(timezone.utc),
            is_bot=False,
            is_command=False,
        )

    elapsed = time.time() - start_time
    print(
        f"Inserted 50 messages individually in {
            elapsed:.3f}s ({
            50 /
            elapsed:.1f} msg/s)")
    return elapsed


async def test_batch_inserts(single_time):
    """Test performance of batch message inserts."""
    print("\n=== Testing Batch Inserts ===")
    channel_id = "perf_test_channel"

    messages = []
    for i in range(50):
        messages.append(
            {
                "message_id": f"batch_msg_{i}_{time.time()}",
                "author_id": "test_user",
                "author_name": "Test User",
                "channel_id": channel_id,
                "channel_name": "Performance Test",
                "content": f"Test batch message {i}",
                "created_at": datetime.now(timezone.utc),
                "is_bot": False,
                "is_command": False,
            }
        )

    start_time = time.time()
    await store_messages_batch(messages)
    elapsed = time.time() - start_time

    print(f"Inserted 50 messages in batch in {elapsed:.3f}s ({50 / elapsed:.1f} msg/s)")
    print(f"Batch is {single_time / elapsed:.1f}x faster than individual inserts")
    return elapsed


def test_query_performance():
    """Test performance of querying messages."""
    print("\n=== Testing Query Performance ===")
    channel_id = "perf_test_channel"

    # Query last 24 hours
    start_time = time.time()
    messages = get_channel_messages_for_hours(
        channel_id=channel_id, date=datetime.now(timezone.utc), hours=24
    )
    elapsed = time.time() - start_time

    print(f"Queried {len(messages)} messages in {elapsed:.3f}s")
    return elapsed


async def main():
    """Run all performance tests."""
    print("Initializing database...")
    init_database()

    # Test single inserts
    single_time = test_single_inserts()

    # Test batch inserts
    await test_batch_inserts(single_time)

    # Test queries
    test_query_performance()

    print("\n=== Performance Test Complete ===")
    print("\nKey Improvements:")
    print("1. Composite index (channel_id, created_at) eliminates temp B-tree sorting")
    print(
        "2. Direct string comparison instead of datetime() functions enables index usage"  # noqa: E501
    )
    print("3. Explicit BEGIN/COMMIT for batch operations reduces transaction overhead")
    print("4. WAL journal mode improves write concurrency")
    print("5. Optimized cache and memory settings speed up operations")


if __name__ == "__main__":
    asyncio.run(main())
