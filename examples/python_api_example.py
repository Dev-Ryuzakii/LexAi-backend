#!/usr/bin/env python3
"""
Example script demonstrating how to use the AI-CBT API
"""

import requests
import json
import sys
import os

# Add the src directory to the path so we can import our models
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import SessionLocal, User, APIKey

# API base URL
BASE_URL = "http://localhost:5001/api/v1"

def register_user(email, password):
    """Register a new user"""
    url = f"{BASE_URL}/register"
    payload = {
        "email": email,
        "password": password
    }
    
    try:
        response = requests.post(url, json=payload)
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def login_user(email, password):
    """Login and get authentication token"""
    url = f"{BASE_URL}/login"
    payload = {
        "email": email,
        "password": password
    }
    
    try:
        response = requests.post(url, json=payload)
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def create_api_key(auth_token, email, key_name, plan_type="free", rate_limit=1000, monthly_quota=10000):
    """Create an API key using the auth token"""
    url = f"{BASE_URL}/api-keys"
    payload = {
        "email": email,
        "key_name": key_name,
        "plan_type": plan_type,
        "rate_limit": rate_limit,
        "monthly_quota": monthly_quota
    }
    
    try:
        response = requests.post(url, 
                               json=payload,
                               headers={"Authorization": f"Bearer {auth_token}"})
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def use_api_with_key(api_key, student_answer, marking_guide, question_text=""):
    """Use the API with an API key"""
    url = f"{BASE_URL}/score"
    payload = {
        "student_answer": student_answer,
        "marking_guide": marking_guide,
        "question_text": question_text
    }
    
    try:
        response = requests.post(url, 
                               json=payload,
                               headers={"X-API-Key": api_key})
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def main():
    """Main function demonstrating the complete flow"""
    print("🚀 AI-CBT API Usage Example")
    print("=" * 50)
    
    # User credentials
    email = "example_user@test.com"
    password = "secure_password_123"
    
    # Step 1: Register user
    print("1. Registering user...")
    result, status = register_user(email, password)
    if status != 201:
        print(f"   Registration failed: {result}")
        return
    print(f"   ✅ User registered successfully")
    
    # Step 2: Login user
    print("2. Logging in...")
    result, status = login_user(email, password)
    if status != 200:
        print(f"   Login failed: {result}")
        return
    
    auth_token = result.get("token")
    print(f"   ✅ Login successful")
    print(f"   Auth token: {auth_token[:20]}...")
    
    # Step 3: Create API key
    print("3. Creating API key...")
    result, status = create_api_key(auth_token, email, "My Application Key", "development", 1000, 10000)
    if status != 201:
        print(f"   API key creation failed: {result}")
        return
    
    api_key = result.get("api_key", {}).get("api_key")
    print(f"   ✅ API key created successfully")
    print(f"   API key: {api_key}")
    
    # Step 4: Use API with the key
    print("4. Using API with the key...")
    result, status = use_api_with_key(
        api_key,
        "Photosynthesis is the process by which plants convert sunlight into energy.",
        "Photosynthesis is the process used by plants and other organisms to convert light energy into chemical energy that can later be released to fuel the organisms' activities.",
        "What is photosynthesis?"
    )
    
    if status != 200:
        print(f"   API usage failed: {result}")
        return
    
    print(f"   ✅ API request successful")
    print(f"   Score: {result.get('data', {}).get('score', 'N/A')}")
    print(f"   Confidence: {result.get('data', {}).get('confidence', 'N/A')}")
    
    print("\n🎉 Complete flow demonstrated successfully!")
    print(f"Your API key is: {api_key}")
    print("Use this key in the X-API-Key header for all API requests.")

if __name__ == "__main__":
    main()