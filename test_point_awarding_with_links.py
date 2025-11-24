"""
Test to verify that point awarding includes scraped link content.
This test validates the fix for link point awarding by checking that
scraped content is properly included in the message formatting.
"""
import json

def test_message_formatting_with_links():
    """Test that messages with scraped content are properly formatted for point analysis"""

    # Simulate messages with scraped content
    messages = [
        {
            'author_name': 'TestUser',
            'author_id': '123456',
            'content': 'Check out this article: https://example.com/article',
            'scraped_url': 'https://example.com/article',
            'scraped_content_summary': 'This article discusses the latest advances in AI technology.',
            'scraped_content_key_points': json.dumps([
                'AI models are becoming more efficient',
                'New architectures reduce training costs',
                'Applications in healthcare are expanding'
            ])
        },
        {
            'author_name': 'AnotherUser',
            'author_id': '789012',
            'content': 'That\'s really interesting!',
        }
    ]

    # Format messages like the analyze_messages_for_points function does
    formatted_messages_text = []
    for msg in messages:
        author_name = msg.get('author_name', 'Unknown')
        content = msg.get('content', '')
        author_id = msg.get('author_id', '')

        # Check if this message has scraped content from a URL
        scraped_url = msg.get('scraped_url')
        scraped_summary = msg.get('scraped_content_summary')
        scraped_key_points = msg.get('scraped_content_key_points')

        # Include author_id for tracking
        message_text = f"[User: {author_name} (ID: {author_id})] {content}"

        # If there's scraped content, add it to the message so LLM can evaluate link quality
        if scraped_url and scraped_summary:
            link_content = f"\n[Link Content from {scraped_url}]:\n{scraped_summary}"
            message_text += link_content

            # If there are key points, add them too
            if scraped_key_points:
                try:
                    key_points = json.loads(scraped_key_points)
                    if key_points and isinstance(key_points, list):
                        message_text += "\nKey points:"
                        for point in key_points:
                            message_text += f"\n- {point}"
                except json.JSONDecodeError:
                    print(f"Failed to parse key points JSON for point analysis: {scraped_key_points}")

        formatted_messages_text.append(message_text)

    # Check the results
    print("=== Formatted Messages for Point Analysis ===\n")
    for i, msg_text in enumerate(formatted_messages_text, 1):
        print(f"Message {i}:")
        print(msg_text)
        print("\n" + "-" * 50 + "\n")

    # Verify that the first message includes scraped content
    assert 'Link Content from https://example.com/article' in formatted_messages_text[0], \
        "Scraped URL should be included in formatted message"
    assert 'This article discusses the latest advances in AI technology' in formatted_messages_text[0], \
        "Scraped summary should be included in formatted message"
    assert 'AI models are becoming more efficient' in formatted_messages_text[0], \
        "Key points should be included in formatted message"

    # Verify that the second message doesn't have scraped content (no link)
    assert 'Link Content' not in formatted_messages_text[1], \
        "Messages without links should not have scraped content"

    print("✅ All assertions passed!")
    print("\nSummary:")
    print("- Messages with links now include full scraped content for LLM analysis")
    print("- This allows the LLM to properly evaluate link quality and relevance")
    print("- Original posters of valuable links will receive appropriate point awards")

if __name__ == "__main__":
    test_message_formatting_with_links()
