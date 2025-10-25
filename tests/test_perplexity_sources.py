#!/usr/bin/env python3
import os
import json
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

print("Testing Perplexity 'sonar' model with sources...")
print("-" * 50)

try:
    response = client.chat.completions.create(
        model="sonar",
        messages=[
            {
                "role": "user",
                "content": "What are the latest AI developments in 2024? Please provide sources.",  # noqa: E501
            }
        ],
        max_tokens=500,
        temperature=0,
    )

    print("Full Response Object:")
    print(json.dumps(response.model_dump(), indent=2, default=str))
    print("\n" + "-" * 50)

    print("\nMessage Content:")
    print(response.choices[0].message.content)

    # Check if there are citations in the response
    if hasattr(response, "citations") or hasattr(response.choices[0], "citations"):
        print("\nCitations found in response!")
    else:
        print("\nNo citations field found in response structure")

except Exception as e:
    print(f"Error: {e}")
