#!/usr/bin/env python3
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Get API key
api_key = os.getenv("PERPLEXITY_API_KEY")

if not api_key:
    print("Error: PERPLEXITY_API_KEY not found in .env file")
    exit(1)

# Initialize client
client = OpenAI(
    base_url="https://api.perplexity.ai",
    api_key=api_key,
)

# Test different model names
test_models = [
    "sonar",
    "sonar-small-chat",
    "sonar-small-online",
    "sonar-medium-chat",
    "sonar-medium-online",
    "codellama-70b-instruct",
    "mistral-7b-instruct",
    "llama-2-70b-chat",
    "pplx-7b-chat",
    "pplx-70b-chat",
    "pplx-7b-online",
    "pplx-70b-online",
]

print("Testing Perplexity models...")
print("-" * 50)

for model in test_models:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'test' in one word"}],
            max_tokens=5,
            temperature=0,
        )
        print(f"✓ {model} - WORKS")
    except Exception as e:
        error_msg = str(e)
        if "Invalid model" in error_msg:
            print(f"✗ {model} - INVALID MODEL")
        else:
            print(f"✗ {model} - ERROR: {error_msg[:100]}")

print("-" * 50)
print("\nNote: Models marked with ✓ are available for use.")
