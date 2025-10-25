"""
Test to verify channel context is properly added to LLM prompts.
"""

from llm_handler import _prepare_user_content_with_context


def test_channel_context_in_prompt():
    """Test that channel name is included in the context."""
    print("=== Testing Channel Context Addition ===\n")

    # Test 1: With channel context
    print("Test 1: Message with channel context")
    query = "how many messages today?"
    message_context = {"channel_name": "general", "channel_id": "123456789"}

    user_content = _prepare_user_content_with_context(query, message_context)
    print(f"Query: {query}")
    print(f"Context: {message_context}")
    print(f"Prepared content:\n{user_content}\n")

    assert (
        "**Current Channel:** #general" in user_content
    ), "Channel context should be in user content"
    print("✅ PASS: Channel context is included\n")

    # Test 2: Without channel context
    print("Test 2: Message without channel context")
    query2 = "what is AI?"
    message_context2 = {}

    user_content2 = _prepare_user_content_with_context(query2, message_context2)
    print(f"Query: {query2}")
    print(f"Context: {message_context2}")
    print(f"Prepared content:\n{user_content2}\n")

    assert (
        "**Current Channel:**" not in user_content2
    ), "Channel context should not be present"
    print("✅ PASS: No channel context when not provided\n")

    # Test 3: With channel and thread context
    print("Test 3: Message with both channel and thread context")
    query3 = "continue the discussion"
    message_context3 = {
        "channel_name": "tech-talk",
        "channel_id": "987654321",
        "thread_context": "Previous message: User asked about Python vs JavaScript",
    }

    user_content3 = _prepare_user_content_with_context(query3, message_context3)
    print(f"Query: {query3}")
    print(f"Context keys: {list(message_context3.keys())}")
    print(f"Prepared content:\n{user_content3}\n")

    assert (
        "**Current Channel:** #tech-talk" in user_content3
    ), "Channel should be present"
    assert (
        "**Thread Conversation History:**" in user_content3
    ), "Thread context should be present"
    print("✅ PASS: Both channel and thread context are included\n")

    print("=== All Tests Passed ===")


if __name__ == "__main__":
    test_channel_context_in_prompt()
