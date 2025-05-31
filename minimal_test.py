#!/usr/bin/env python3
"""
Minimal test to debug OpenRouter API issues.
"""

import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def minimal_test():
    """Minimal test with the simplest possible request"""
    
    api_key = os.getenv('OPENROUTER_API_KEY')
    print(f"🔑 Using API key: {api_key[:20]}...")
    
    # Try the absolute minimal request
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Try with the most basic model and minimal payload
    payload = {
        "model": "google/gemma-2b-it",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5
    }
    
    print(f"🚀 Making minimal request to: {url}")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"📊 Status: {response.status_code}")
        print(f"📄 Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Success!")
            return True
        else:
            print("❌ Failed")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def test_generation_endpoint():
    """Test the generation endpoint instead of chat completions"""
    
    api_key = os.getenv('OPENROUTER_API_KEY')
    
    # Try the generation endpoint
    url = "https://openrouter.ai/api/v1/generation"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "google/gemma-2b-it",
        "prompt": "Hello",
        "max_tokens": 5
    }
    
    print(f"\n🔄 Trying generation endpoint: {url}")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"📊 Status: {response.status_code}")
        print(f"📄 Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Generation endpoint works!")
            return True
        else:
            print("❌ Generation endpoint failed")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Minimal OpenRouter Test")
    print("=" * 40)
    
    minimal_test()
    test_generation_endpoint()
