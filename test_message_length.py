"""
Test script to verify message length handling and splitting functionality.
"""

import asyncio
import logging
from message_utils import split_long_message

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_message_splitting():
    """Test message splitting functionality with various lengths."""

    print("Testing Message Length Handling")
    print("=" * 50)

    # Test cases with different message lengths
    test_cases = [
        {
            "name": "Short message (under 2000 chars)",
            "content": "This is a short message that should not be split.",
            "expected_parts": 1,
        },
        {
            "name": "Medium message (around 2500 chars)",
            "content": "A" * 2500,
            "expected_parts": 2,
        },
        {
            "name": "Long message (around 5000 chars)",
            "content": "B" * 5000,
            "expected_parts": 3,
        },
        {
            "name": "Very long message (around 10000 chars)",
            "content": "C" * 10000,
            "expected_parts": 6,
        },
    ]

    for test_case in test_cases:
        print(f"\nTesting: {test_case['name']}")
        print(f"Original length: {len(test_case['content'])} characters")

        try:
            # Test with default max_length (1900)
            parts = await split_long_message(test_case["content"])

            print(f"Split into {len(parts)} parts")

            # Verify each part is within limits
            all_valid = True
            for i, part in enumerate(parts):
                if len(part) > 2000:
                    print(f"  ERROR: Part {i+1} is {len(part)} chars (exceeds 2000)")
                    all_valid = False
                else:
                    print(f"  Part {i+1}: {len(part)} chars ✓")

            # Verify content integrity
            rejoined = "".join(parts)
            if rejoined == test_case["content"]:
                print("  Content integrity: ✓")
            else:
                print("  Content integrity: ✗ (content was modified during split)")
                all_valid = False

            if all_valid:
                print(f"  Result: PASS")
            else:
                print(f"  Result: FAIL")

        except Exception as e:
            print(f"  ERROR: {e}")
            print(f"  Result: FAIL")


async def test_chart_message_lengths():
    """Test realistic chart response lengths."""

    print("\n\nTesting Chart Response Lengths")
    print("=" * 50)

    # Simulate chart analysis responses of various lengths
    chart_responses = [
        {
            "name": "Simple chart response",
            "content": """Here's the user activity analysis:

| Username | Message Count |
| --- | --- |
| alice | 45 |
| bob | 32 |
| charlie | 28 |

Key insights:
- Alice leads with 42% of messages
- Activity peaked during evening hours
- Technical discussions dominated""",
        },
        {
            "name": "Detailed chart response",
            "content": """Based on the conversation analysis, here are the detailed activity patterns:

| Username | Message Count | Percentage |
| --- | --- | --- |
| alice | 145 | 35.2% |
| bob | 132 | 32.1% |
| charlie | 98 | 23.8% |
| david | 36 | 8.9% |

| Time Period | Messages | Peak Users |
| --- | --- | --- |
| 09:00-12:00 | 87 | alice, bob |
| 12:00-15:00 | 134 | charlie, david |
| 15:00-18:00 | 156 | alice, charlie |
| 18:00-21:00 | 201 | all active |

Key insights and patterns:
- Alice maintained consistent activity throughout the day with peak engagement during morning and evening hours
- Bob showed strong morning presence but reduced activity in afternoon
- Charlie demonstrated steady participation with emphasis on afternoon technical discussions
- David's participation was more focused on midday collaborative sessions
- Overall engagement showed healthy distribution across time zones
- Technical topics dominated during business hours while casual conversation increased in evening
- Link sharing peaked during afternoon hours with 23 technical resources shared
- Code collaboration was most active during 15:00-18:00 timeframe

Notable trends:
- Increased use of threads for technical discussions
- More collaborative problem-solving in recent period
- Growing focus on AI and machine learning topics
- Enhanced community interaction and knowledge sharing""",
        },
    ]

    for i, response in enumerate(chart_responses, 1):
        print(f"\nTesting: {response['name']}")
        content = response["content"]
        print(f"Length: {len(content)} characters")

        try:
            # Test splitting for regular messages
            parts = await split_long_message(content, max_length=1800)
            print(f"Split for regular send: {len(parts)} parts")

            for j, part in enumerate(parts):
                print(f"  Part {j+1}: {len(part)} chars")

            # Test splitting for chart messages (more conservative)
            chart_parts = await split_long_message(content, max_length=1900)
            print(f"Split for chart send: {len(chart_parts)} parts")

            for j, part in enumerate(chart_parts):
                print(f"  Chart part {j+1}: {len(part)} chars")

        except Exception as e:
            print(f"  ERROR: {e}")


def test_thread_context_length():
    """Test thread context formatting length."""

    print("\n\nTesting Thread Context Length")
    print("=" * 50)

    # Simulate thread context
    from thread_memory import ThreadMessage
    from datetime import datetime, timezone

    # Create mock thread messages
    messages = []
    for i in range(10):
        msg = ThreadMessage(
            sequence_id=i + 1,
            user_message=f"User message {i+1}: "
            + "This is a sample user message with some content. " * 3,
            bot_response=f"Bot response {i+1}: "
            + "This is a sample bot response with analysis and insights. " * 4,
            user_id=f"user_{i+1}",
            user_name=f"user{i+1}",
            timestamp=datetime.now(timezone.utc),
            message_type="exchange",
        )
        messages.append(msg)

    # Test context formatting
    from thread_memory import ThreadMemoryManager

    manager = ThreadMemoryManager()

    context = manager.format_thread_context(messages, max_context_length=2500)

    print(f"Thread context length: {len(context)} characters")
    print(f"Context preview (first 200 chars):")
    print(context[:200] + "..." if len(context) > 200 else context)

    if len(context) <= 2500:
        print("✓ Context within limits")
    else:
        print(f"✗ Context exceeds limit by {len(context) - 2500} characters")


async def main():
    """Run all tests."""
    try:
        await test_message_splitting()
        await test_chart_message_lengths()
        test_thread_context_length()

        print("\n" + "=" * 50)
        print("All tests completed!")

    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
