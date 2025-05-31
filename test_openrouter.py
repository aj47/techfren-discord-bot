#!/usr/bin/env python3
"""
Test script to debug OpenRouter API issues.
This script will test the API key and check available models.
"""

import os
import requests
import json
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

def test_openrouter_api():
    """Test OpenRouter API key and check available models"""
    
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        print("❌ OPENROUTER_API_KEY not found in environment variables")
        return False
    
    print(f"🔑 API Key: {api_key[:20]}...")
    
    # Test 1: Check available models
    print("\n📋 Testing available models...")
    try:
        models_response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        print(f"Models endpoint status: {models_response.status_code}")
        
        if models_response.status_code == 200:
            models_data = models_response.json()
            models = models_data.get('data', [])
            print(f"✅ Found {len(models)} available models")
            
            # Look for common models
            common_models = [
                'openai/gpt-4o-mini',
                'openai/gpt-3.5-turbo',
                'anthropic/claude-3-haiku',
                'meta-llama/llama-3.1-8b-instruct',
                'deepseek/deepseek-r1'
            ]
            
            print("\n🔍 Checking for common models:")
            available_models = [model['id'] for model in models]
            
            for model in common_models:
                if model in available_models:
                    print(f"  ✅ {model} - Available")
                else:
                    print(f"  ❌ {model} - Not available")
            
            # Show first 10 available models with more details
            print(f"\n📝 First 10 available models:")
            for i, model in enumerate(models[:10]):
                context_length = model.get('context_length', 'Unknown')
                pricing = model.get('pricing', {})
                prompt_price = pricing.get('prompt', 'Unknown')
                print(f"  {i+1}. {model['id']} (context: {context_length}, prompt: {prompt_price})")
                
        else:
            print(f"❌ Failed to get models: {models_response.status_code}")
            print(f"Response: {models_response.text}")
            
    except Exception as e:
        print(f"❌ Error checking models: {e}")
    
    # Test 2: Try a simple chat completion with a basic model
    print("\n💬 Testing chat completion...")
    
    # Try with models that appeared in the available list
    # Let's try both with and without :free suffix
    test_models = [
        'google/gemma-2b-it',
        'deepseek/deepseek-r1-distill-qwen-7b',
        'deepseek/deepseek-r1-0528-qwen3-8b:free',
        'deepseek/deepseek-r1-0528-qwen3-8b'
    ]
    
    for model in test_models:
        print(f"\n🧪 Testing model: {model}")
        try:
            chat_response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://techfren.net",
                    "X-Title": "TechFren Discord Bot Test"
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Say 'Hello, this is a test!' and nothing else."
                        }
                    ],
                    "max_tokens": 50,
                    "temperature": 0.1
                },
                timeout=30
            )
            
            print(f"  Status: {chat_response.status_code}")
            
            if chat_response.status_code == 200:
                response_data = chat_response.json()
                message = response_data['choices'][0]['message']['content']
                print(f"  ✅ Success! Response: {message}")
                return True
            else:
                print(f"  ❌ Failed: {chat_response.text}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    return False

def test_with_openai_client():
    """Test using OpenAI client like the bot does"""
    api_key = os.getenv('OPENROUTER_API_KEY')

    print("\n🔧 Testing with OpenAI client (like the bot)...")

    try:
        # Initialize the OpenAI client with OpenRouter base URL
        openai_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )

        # Try a simple model that should work
        test_models = ['google/gemma-2b-it', 'deepseek/deepseek-r1-distill-qwen-7b']

        for model in test_models:
            print(f"\n🧪 Testing {model} with OpenAI client...")
            try:
                completion = openai_client.chat.completions.create(
                    extra_headers={
                        "HTTP-Referer": "https://techfren.net",
                        "X-Title": "TechFren Discord Bot Test",
                    },
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": "Say 'Hello test' and nothing else."
                        }
                    ],
                    max_tokens=10,
                    temperature=0.1
                )

                message = completion.choices[0].message.content
                print(f"  ✅ Success! Response: {message}")
                return True

            except Exception as e:
                print(f"  ❌ Error with {model}: {e}")

    except Exception as e:
        print(f"❌ Error initializing OpenAI client: {e}")

    return False

def test_api_key_validity():
    """Test if the API key is valid by checking account info"""
    api_key = os.getenv('OPENROUTER_API_KEY')

    print("\n🔐 Testing API key validity...")
    try:
        # Try to get account information
        response = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            timeout=10
        )

        print(f"Auth endpoint status: {response.status_code}")

        if response.status_code == 200:
            auth_data = response.json()
            print("✅ API key is valid!")
            print(f"Key info: {json.dumps(auth_data, indent=2)}")

            # Check if this is a free tier account
            data = auth_data.get('data', {})
            is_free_tier = data.get('is_free_tier', False)
            usage = data.get('usage', 0)
            limit = data.get('limit')

            print(f"\n📊 Account Details:")
            print(f"  Free tier: {is_free_tier}")
            print(f"  Usage: ${usage}")
            print(f"  Limit: {limit}")

            return True
        else:
            print(f"❌ API key validation failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error validating API key: {e}")
        return False

if __name__ == "__main__":
    print("🚀 OpenRouter API Test")
    print("=" * 50)
    
    # Test API key validity first
    if test_api_key_validity():
        # If key is valid, test the API
        if not test_openrouter_api():
            # If regular API test fails, try with OpenAI client
            test_with_openai_client()
    else:
        print("\n❌ API key is invalid. Please check your OPENROUTER_API_KEY.")
