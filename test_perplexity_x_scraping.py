#!/usr/bin/env python3
"""
Test script to verify Perplexity can scrape and summarize X/Twitter posts directly.
"""
import asyncio
import os
from dotenv import load_dotenv
from llm_handler import summarize_url_with_perplexity

# Load environment variables
load_dotenv(override=True)

async def test_x_scraping():
    """Test Perplexity's ability to scrape and summarize an X post."""

    # Test with multiple X post URLs
    test_urls = [
        "https://x.com/elonmusk/status/1854251718319792453",  # Recent Elon tweet
        "https://x.com/OpenAI/status/1854251718319792453",  # OpenAI tweet
        "https://x.com/kcosr/status/1985550648113528924"  # Original test URL
    ]

    for test_url in test_urls:
        print(f"\nTesting Perplexity scraping for X post: {test_url}")
        print("-" * 60)

        try:
            result = await summarize_url_with_perplexity(test_url)

            if result:
                print("✓ Successfully scraped and summarized X post!")
                print("\nSummary:")
                print(result.get('summary', 'No summary'))
                print("\nKey Points:")
                for i, point in enumerate(result.get('key_points', []), 1):
                    print(f"{i}. {point}")
            else:
                print("✗ Failed to scrape and summarize X post")

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()

        print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(test_x_scraping())

