#!/usr/bin/env python3
"""
AI-CBT API Testing Script
Demonstrates how to use the AI-CBT Assessment API
"""

import requests
import json
import time
from typing import Dict, Any

class AIAssessmentAPI:
    def __init__(self, base_url: str = "http://localhost:5001/api/v1", api_key: str = "dev_key_123"):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Check API health status"""
        response = requests.get(f"{self.base_url}/health")
        return response.json()
    
    def score_answer(self, student_answer: str, marking_guide: str, question_text: str = "") -> Dict[str, Any]:
        """Score a student answer"""
        data = {
            "student_answer": student_answer,
            "marking_guide": marking_guide,
            "question_text": question_text
        }
        response = requests.post(f"{self.base_url}/score", headers=self.headers, json=data)
        return response.json()
    
    def create_question(self, question_text: str, marking_guide: str) -> Dict[str, Any]:
        """Create a new question"""
        data = {
            "question_text": question_text,
            "marking_guide": marking_guide
        }
        response = requests.post(f"{self.base_url}/questions", headers=self.headers, json=data)
        return response.json()
    
    def get_questions(self) -> Dict[str, Any]:
        """Get all questions"""
        response = requests.get(f"{self.base_url}/questions", headers=self.headers)
        return response.json()
    
    def create_student(self, name: str, matric_number: str) -> Dict[str, Any]:
        """Create or get a student"""
        data = {
            "name": name,
            "matric_number": matric_number
        }
        response = requests.post(f"{self.base_url}/students", headers=self.headers, json=data)
        return response.json()
    
    def submit_response(self, student_id: int, question_id: int, answer: str) -> Dict[str, Any]:
        """Submit and score a student response"""
        data = {
            "student_id": student_id,
            "question_id": question_id,
            "answer": answer
        }
        response = requests.post(f"{self.base_url}/submit-response", headers=self.headers, json=data)
        return response.json()
    
    def get_student_responses(self, student_id: int) -> Dict[str, Any]:
        """Get all responses for a student"""
        response = requests.get(f"{self.base_url}/student/{student_id}/responses", headers=self.headers)
        return response.json()

def run_demo():
    """Run a complete API demonstration"""
    print("🤖 AI-CBT Assessment API Demo")
    print("=" * 50)
    
    # Initialize API client
    api = AIAssessmentAPI()
    
    # 1. Health Check
    print("\n1. 🏥 Health Check")
    try:
        health = api.health_check()
        print(f"   Status: {health['status']}")
        print(f"   Ollama: {'✅' if health['services']['ollama'] else '❌'}")
        print(f"   Database: {'✅' if health['services']['database'] else '❌'}")
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return
    
    # 2. Create Questions
    print("\n2. 📚 Creating Sample Questions")
    questions_data = [
        {
            "question_text": "What is photosynthesis?",
            "marking_guide": "Photosynthesis is the process by which plants convert light energy, usually from the sun, into chemical energy stored in glucose. This process involves chlorophyll, carbon dioxide, and water, producing glucose and oxygen as byproducts."
        },
        {
            "question_text": "Explain the water cycle.",
            "marking_guide": "The water cycle is the continuous movement of water through evaporation from bodies of water, condensation into clouds, precipitation as rain or snow, and collection back into water bodies. It includes processes like transpiration from plants and infiltration into groundwater."
        },
        {
            "question_text": "What is machine learning?",
            "marking_guide": "Machine learning is a subset of artificial intelligence that enables computers to learn and improve from experience without being explicitly programmed. It uses algorithms to identify patterns in data and make predictions or decisions based on those patterns."
        }
    ]
    
    created_questions = []
    for q_data in questions_data:
        try:
            result = api.create_question(q_data["question_text"], q_data["marking_guide"])
            if result.get('success'):
                created_questions.append(result['question_id'])
                print(f"   ✅ Created question ID: {result['question_id']}")
            else:
                print(f"   ❌ Failed to create question: {result}")
        except Exception as e:
            print(f"   ❌ Error creating question: {e}")
    
    # 3. Create Students
    print("\n3. 👥 Creating Sample Students")
    students_data = [
        {"name": "Alice Johnson", "matric_number": "A12345678"},
        {"name": "Bob Smith", "matric_number": "B87654321"},
        {"name": "Charlie Brown", "matric_number": "C11223344"}
    ]
    
    created_students = []
    for s_data in students_data:
        try:
            result = api.create_student(s_data["name"], s_data["matric_number"])
            if result.get('success'):
                created_students.append(result['student_id'])
                print(f"   ✅ Created student: {s_data['name']} (ID: {result['student_id']})")
            else:
                print(f"   ❌ Failed to create student: {result}")
        except Exception as e:
            print(f"   ❌ Error creating student: {e}")
    
    # 4. Submit Sample Responses
    print("\n4. 📝 Submitting Sample Responses")
    sample_responses = [
        {
            "student_id": created_students[0] if created_students else 1,
            "question_id": created_questions[0] if created_questions else 1,
            "answer": "Photosynthesis is how plants make food using sunlight, water, and carbon dioxide. They produce glucose and oxygen."
        },
        {
            "student_id": created_students[1] if len(created_students) > 1 else 1,
            "question_id": created_questions[1] if len(created_questions) > 1 else 1,
            "answer": "The water cycle involves water evaporating from oceans, forming clouds, and then raining back down."
        },
        {
            "student_id": created_students[2] if len(created_students) > 2 else 1,
            "question_id": created_questions[2] if len(created_questions) > 2 else 1,
            "answer": "Machine learning is when computers learn from data without being programmed for specific tasks."
        }
    ]
    
    for i, response_data in enumerate(sample_responses):
        try:
            result = api.submit_response(
                response_data["student_id"],
                response_data["question_id"],
                response_data["answer"]
            )
            if result.get('success'):
                scoring = result['scoring']
                print(f"   ✅ Response {i+1} scored: {scoring['score']}/5")
                print(f"      Confidence: {scoring['confidence']:.2f}")
                print(f"      Feedback: {scoring['feedback'][:100]}...")
            else:
                print(f"   ❌ Failed to score response: {result}")
        except Exception as e:
            print(f"   ❌ Error submitting response: {e}")
    
    # 5. Test Direct Scoring
    print("\n5. 🎯 Testing Direct Answer Scoring")
    test_cases = [
        {
            "student_answer": "Gravity is a force that pulls things down to Earth.",
            "marking_guide": "Gravity is the force of attraction between masses, most commonly experienced as objects being pulled toward Earth due to its large mass.",
            "question_text": "What is gravity?"
        },
        {
            "student_answer": "DNA contains genetic information.",
            "marking_guide": "DNA (Deoxyribonucleic acid) is the hereditary material that contains genetic instructions for the development and function of living organisms. It is composed of nucleotides arranged in a double helix structure.",
            "question_text": "What is DNA and what is its function?"
        }
    ]
    
    for i, test_case in enumerate(test_cases):
        try:
            result = api.score_answer(
                test_case["student_answer"],
                test_case["marking_guide"],
                test_case["question_text"]
            )
            if result.get('success'):
                data = result['data']
                print(f"   ✅ Test {i+1} Score: {data['score']}/5 (Confidence: {data['confidence']:.2f})")
                print(f"      Method: {result['scoring_method']}")
                print(f"      Feedback: {data['feedback'][:100]}...")
            else:
                print(f"   ❌ Scoring failed: {result}")
        except Exception as e:
            print(f"   ❌ Error scoring: {e}")
    
    # 6. Get Student Progress
    print("\n6. 📊 Checking Student Progress")
    if created_students:
        try:
            student_id = created_students[0]
            result = api.get_student_responses(student_id)
            student = result['student']
            print(f"   Student: {student['name']} ({student['matric_number']})")
            print(f"   Total Score: {student['total_score']}")
            print(f"   Total Responses: {result['total_responses']}")
            
            for response in result['responses'][:2]:  # Show first 2 responses
                print(f"   📝 Response: Score {response['score']}/5")
                print(f"      Answer: {response['answer'][:80]}...")
        except Exception as e:
            print(f"   ❌ Error getting student progress: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Demo completed! Check the API documentation for more details.")
    print("📖 Documentation available at: http://localhost:5001/api/v1/docs")

if __name__ == "__main__":
    try:
        run_demo()
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted by user.")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        print("Make sure the API server is running on http://localhost:5001")
