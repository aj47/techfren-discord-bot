#!/usr/bin/env python3
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Get API key
api_key = os.getenv("PERPLEXITY_API_KEY")

# Initialize client
client = OpenAI(
    base_url="https://api.perplexity.ai",
    api_key=api_key,
)

print("Testing if 'sonar' model has web search capabilities...")
print("-" * 50)

try:
    response = client.chat.completions.create(
        model="sonar",
        messages=[
            {
                "role": "user",
                "content": "What is the current weather in New York City today? Please provide sources.",
            }
        ],
        max_tokens=200,
        temperature=0,
    )

    result = response.choices[0].message.content
    print("Response from 'sonar' model:")
    print(result)
    print("-" * 50)

    # Check if response contains web-based information
    if any(
        word in result.lower()
        for word in ["today", "current", "now", "degrees", "temperature", "weather"]
    ):
        print("✓ Model appears to have web search capabilities!")
    else:
        print(
            "⚠ Model may not have web search capabilities or couldn't retrieve current data"
        )

except Exception as e:
    print(f"Error: {e}")
