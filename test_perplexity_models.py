#!/usr/bin/env python3
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Get API key
api_key = os.getenv('WAFER_API_KEY')

if not api_key:
    import pytest
    pytest.skip("WAFER_API_KEY not configured", allow_module_level=True)

# Initialize client
client = OpenAI(
    base_url="https://pass.wafer.ai/v1",
    api_key=api_key,
)

# Test different model names
test_models = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
]

print("Testing Wafer models...")
print("-" * 50)

for model in test_models:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Say 'test' in one word"}
            ],
            max_tokens=5,
            temperature=0
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
