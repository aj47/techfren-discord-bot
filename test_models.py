#!/usr/bin/env python3
"""
Test script to check which models are available on OpenRouter
"""

import os
import sys

# Add the current directory to Python path to import config
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from openai import OpenAI
    from dotenv import load_dotenv
    import config
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running this from the correct environment")
    exit(1)

# Load environment variables
load_dotenv()

# Get API key from config
try:
    openrouter_key = config.openrouter
    if not openrouter_key:
        print("Error: OPENROUTER_API_KEY not found in config")
        exit(1)
except AttributeError:
    print("Error: openrouter not found in config")
    exit(1)

# Initialize client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=openrouter_key
)

# List of models to test
test_models = [
    "x-ai/grok-3-mini-beta",  # Current problematic model
    "anthropic/claude-3-haiku",
    "anthropic/claude-3-sonnet",
    "openai/gpt-3.5-turbo",
    "openai/gpt-4o-mini",
    "google/gemini-pro",
    "mistralai/mistral-7b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
]

def test_model(model_name):
    """Test if a model is available and working"""
    try:
        print(f"Testing {model_name}...")
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": "Hello, just testing if you're available. Please respond with 'OK'."}
            ],
            max_tokens=10,
            temperature=0.1
        )
        response = completion.choices[0].message.content
        print(f"✅ {model_name}: {response}")
        return True
    except Exception as e:
        print(f"❌ {model_name}: {str(e)}")
        return False

if __name__ == "__main__":
    print("Testing OpenRouter model availability...\n")
    
    working_models = []
    for model in test_models:
        if test_model(model):
            working_models.append(model)
        print()  # Empty line for readability
    
    print("=" * 50)
    print("SUMMARY:")
    print(f"Working models ({len(working_models)}):")
    for model in working_models:
        print(f"  - {model}")
    
    if working_models:
        print(f"\nRecommended replacement: {working_models[0]}")
    else:
        print("\nNo models are working! Check your API key and internet connection.")
