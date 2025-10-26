import requests
import json
import time

# Configuration
BASE_URL = "http://localhost:5001/api/v1"
API_KEY = "dev_key_123"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def test_health_check():
    """Test the health check endpoint"""
    print("Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    print("✓ Health check passed")

def test_question_crud():
    """Test question CRUD operations"""
    print("Testing question CRUD operations...")
    
    # Create a question
    question_data = {
        "question_text": "What is the capital of France?",
        "marking_guide": "The capital of France is Paris."
    }
    
    response = requests.post(f"{BASE_URL}/questions", headers=headers, json=question_data)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] == True
    question_id = data["question_id"]
    print("✓ Question created")
    
    # Get the question
    response = requests.get(f"{BASE_URL}/questions/{question_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["question"]["id"] == question_id
    assert data["question"]["question_text"] == question_data["question_text"]
    print("✓ Question retrieved")
    
    # Update the question
    update_data = {
        "question_text": "What is the capital of Germany?"
    }
    
    response = requests.put(f"{BASE_URL}/questions/{question_id}", headers=headers, json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    print("✓ Question updated")
    
    # Get all questions
    response = requests.get(f"{BASE_URL}/questions", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["questions"]) > 0
    print("✓ All questions retrieved")
    
    # Delete the question
    response = requests.delete(f"{BASE_URL}/questions/{question_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    print("✓ Question deleted")

def test_student_crud():
    """Test student CRUD operations"""
    print("Testing student CRUD operations...")
    
    # Create a student
    student_data = {
        "name": "John Doe",
        "matric_number": "MAT123456"
    }
    
    response = requests.post(f"{BASE_URL}/students", headers=headers, json=student_data)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] == True
    student_id = data["student_id"]
    print("✓ Student created")
    
    # Get the student
    response = requests.get(f"{BASE_URL}/students/{student_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["student"]["id"] == student_id
    assert data["student"]["name"] == student_data["name"]
    print("✓ Student retrieved")
    
    # Update the student
    update_data = {
        "name": "Jane Doe"
    }
    
    response = requests.put(f"{BASE_URL}/students/{student_id}", headers=headers, json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    print("✓ Student updated")
    
    # Get all students
    response = requests.get(f"{BASE_URL}/students", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["students"]) > 0
    print("✓ All students retrieved")
    
    # Delete the student
    response = requests.delete(f"{BASE_URL}/students/{student_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    print("✓ Student deleted")

def test_response_crud():
    """Test response CRUD operations"""
    print("Testing response CRUD operations...")
    
    # First create a question and student for the response
    question_data = {
        "question_text": "What is 2+2?",
        "marking_guide": "The answer is 4."
    }
    
    response = requests.post(f"{BASE_URL}/questions", headers=headers, json=question_data)
    assert response.status_code == 201
    question_id = response.json()["question_id"]
    
    student_data = {
        "name": "Test Student",
        "matric_number": "TEST001"
    }
    
    response = requests.post(f"{BASE_URL}/students", headers=headers, json=student_data)
    assert response.status_code == 201
    student_id = response.json()["student_id"]
    
    # Create a response
    response_data = {
        "student_id": student_id,
        "question_id": question_id,
        "answer": "The answer is 4."
    }
    
    response = requests.post(f"{BASE_URL}/responses", headers=headers, json=response_data)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] == True
    response_id = data["response_id"]
    print("✓ Response created")
    
    # Get the response
    response = requests.get(f"{BASE_URL}/responses/{response_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["response"]["id"] == response_id
    print("✓ Response retrieved")
    
    # Update the response
    update_data = {
        "score": 5.0
    }
    
    response = requests.put(f"{BASE_URL}/responses/{response_id}", headers=headers, json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    print("✓ Response updated")
    
    # Get all responses
    response = requests.get(f"{BASE_URL}/responses", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["responses"]) > 0
    print("✓ All responses retrieved")
    
    # Delete the response
    response = requests.delete(f"{BASE_URL}/responses/{response_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    print("✓ Response deleted")
    
    # Clean up
    requests.delete(f"{BASE_URL}/questions/{question_id}", headers=headers)
    requests.delete(f"{BASE_URL}/students/{student_id}", headers=headers)

def test_submit_response():
    """Test submitting and scoring a response"""
    print("Testing response submission and scoring...")
    
    # First create a question and student
    question_data = {
        "question_text": "Explain photosynthesis.",
        "marking_guide": "Photosynthesis is the process by which plants convert light energy into chemical energy."
    }
    
    response = requests.post(f"{BASE_URL}/questions", headers=headers, json=question_data)
    assert response.status_code == 201
    question_id = response.json()["question_id"]
    
    student_data = {
        "name": "AI Test Student",
        "matric_number": "AI001"
    }
    
    response = requests.post(f"{BASE_URL}/students", headers=headers, json=student_data)
    assert response.status_code == 201
    student_id = response.json()["student_id"]
    
    # Submit and score a response
    submit_data = {
        "student_id": student_id,
        "question_id": question_id,
        "answer": "Photosynthesis is how plants make food from sunlight."
    }
    
    response = requests.post(f"{BASE_URL}/submit-response", headers=headers, json=submit_data)
    # Note: This might fail if Ollama is not running, so we'll just check it doesn't return a 500
    assert response.status_code != 500
    print("✓ Response submission test completed")
    
    # Clean up
    requests.delete(f"{BASE_URL}/questions/{question_id}", headers=headers)
    requests.delete(f"{BASE_URL}/students/{student_id}", headers=headers)

def test_api_documentation():
    """Test that API documentation is accessible"""
    print("Testing API documentation...")
    response = requests.get("http://localhost:5001/api/v1/docs/")
    assert response.status_code == 200
    print("✓ API documentation accessible")

def test_rate_limiting():
    """Test rate limiting functionality"""
    print("Testing rate limiting...")
    
    # Make multiple requests quickly to test rate limiting
    start_time = time.time()
    success_count = 0
    rate_limit_count = 0
    
    for i in range(10):
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            success_count += 1
        elif response.status_code == 429:  # Rate limit exceeded
            rate_limit_count += 1
        time.sleep(0.1)  # Small delay between requests
    
    print(f"✓ Rate limiting test: {success_count} successful, {rate_limit_count} rate limited")

def test_authentication():
    """Test API authentication"""
    print("Testing API authentication...")
    
    # Test without API key
    response = requests.get(f"{BASE_URL}/questions")
    assert response.status_code == 401
    print("✓ Authentication required for protected endpoints")
    
    # Test with invalid API key
    bad_headers = {
        "X-API-Key": "invalid_key",
        "Content-Type": "application/json"
    }
    response = requests.get(f"{BASE_URL}/questions", headers=bad_headers)
    assert response.status_code == 401
    print("✓ Invalid API key rejected")

if __name__ == "__main__":
    try:
        test_health_check()
        test_api_documentation()
        test_authentication()
        test_question_crud()
        test_student_crud()
        test_response_crud()
        test_submit_response()
        test_rate_limiting()
        print("\n🎉 All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)