#!/usr/bin/env python3
"""
Example script demonstrating direct API usage with an existing API key
"""

import requests
import json

# API base URL
BASE_URL = "http://localhost:5001/api/v1"

# Example API key (replace with your own)
API_KEY = "lexai_3c54235b7b7945e88cd9663a156aacb5"

def score_answer(api_key, student_answer, marking_guide, question_text=""):
    """Score a student answer against a marking guide"""
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

def create_question(api_key, question_text, marking_guide):
    """Create a new question"""
    url = f"{BASE_URL}/questions"
    payload = {
        "question_text": question_text,
        "marking_guide": marking_guide
    }
    
    try:
        response = requests.post(url, 
                               json=payload,
                               headers={"X-API-Key": api_key})
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def get_questions(api_key):
    """Get all questions"""
    url = f"{BASE_URL}/questions"
    
    try:
        response = requests.get(url, 
                              headers={"X-API-Key": api_key})
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def main():
    """Main function demonstrating direct API usage"""
    print("🚀 AI-CBT API Direct Usage Example")
    print("=" * 50)
    print(f"Using API key: {API_KEY}")
    print()
    
    # Score an answer
    print("1. Scoring a student answer...")
    result, status = score_answer(
        API_KEY,
        "The capital of France is Paris.",
        "The capital of France is Paris.",
        "What is the capital of France?"
    )
    
    if status == 200:
        print(f"   ✅ Answer scored successfully")
        print(f"   Score: {result['data']['score']}")
        print(f"   Confidence: {result['data']['confidence']}")
        print(f"   Feedback: {result['data']['feedback']}")
    else:
        print(f"   ❌ Scoring failed: {result}")
        return
    
    # Create a question
    print("\n2. Creating a new question...")
    result, status = create_question(
        API_KEY,
        "What is the largest planet in our solar system?",
        "Jupiter is the largest planet in our solar system."
    )
    
    if status == 201:
        print(f"   ✅ Question created successfully")
        print(f"   Question ID: {result['question_id']}")
    else:
        print(f"   ❌ Question creation failed: {result}")
        return
    
    # Get all questions
    print("\n3. Retrieving all questions...")
    result, status = get_questions(API_KEY)
    
    if status == 200:
        print(f"   ✅ Retrieved questions successfully")
        print(f"   Total questions: {result['total_count']}")
        for question in result['questions']:
            print(f"   - {question['question_text']}")
    else:
        print(f"   ❌ Failed to retrieve questions: {result}")
        return
    
    print("\n🎉 Direct API usage demonstrated successfully!")
    print("You can use this API key for all your requests by including it in the X-API-Key header.")

if __name__ == "__main__":
    main()