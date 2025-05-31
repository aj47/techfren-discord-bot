#!/usr/bin/env python3
"""
Quick test to verify the new model works
"""

import os
import requests
import json

# Read the API key from .env file manually
def read_env_file():
    env_vars = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip('"\'')
                    env_vars[key] = value
    except FileNotFoundError:
        print("Error: .env file not found")
        return None
    return env_vars

def test_openrouter_model():
    """Test the OpenRouter API with the new model"""
    env_vars = read_env_file()
    if not env_vars:
        return False
    
    api_key = env_vars.get('OPENROUTER_API_KEY')
    model = env_vars.get('LLM_MODEL', 'openai/gpt-4o-mini')
    
    if not api_key:
        print("Error: OPENROUTER_API_KEY not found in .env")
        return False
    
    print(f"Testing model: {model}")
    print(f"API key: {api_key[:20]}...")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://techfren.net",
        "X-Title": "TechFren Discord Bot"
    }
    
    data = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Hello! Please respond with 'Model is working' to confirm you're available."
            }
        ],
        "max_tokens": 50,
        "temperature": 0.1
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            message = result['choices'][0]['message']['content']
            print(f"✅ Success! Response: {message}")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error details: {json.dumps(error_data, indent=2)}")
            except:
                print(f"Error text: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return False

if __name__ == "__main__":
    print("Testing OpenRouter API with new model...")
    success = test_openrouter_model()
    
    if success:
        print("\n🎉 The model is working! The 404 error should be resolved.")
    else:
        print("\n💥 The model is still not working. You may need to try a different model.")
        print("\nSuggested alternatives to try in .env:")
        print("- LLM_MODEL=anthropic/claude-3-haiku")
        print("- LLM_MODEL=openai/gpt-3.5-turbo")
        print("- LLM_MODEL=google/gemini-pro")
