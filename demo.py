import requests
import json

class AICBTAPI:
    def __init__(self, base_url="http://localhost:5001/api/v1", api_key="dev_key_123"):
        self.base_url = base_url
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }
    
    def health_check(self):
        """Check API health status"""
        response = requests.get(f"{self.base_url}/health")
        return response.json()
    
    def create_question(self, question_text, marking_guide):
        """Create a new assessment question"""
        data = {
            "question_text": question_text,
            "marking_guide": marking_guide
        }
        response = requests.post(f"{self.base_url}/questions", headers=self.headers, json=data)
        return response.json()
    
    def get_questions(self):
        """Get all questions"""
        response = requests.get(f"{self.base_url}/questions", headers=self.headers)
        return response.json()
    
    def create_student(self, name, matric_number):
        """Create or get a student"""
        data = {
            "name": name,
            "matric_number": matric_number
        }
        response = requests.post(f"{self.base_url}/students", headers=self.headers, json=data)
        return response.json()
    
    def submit_response(self, student_id, question_id, answer):
        """Submit and score a student response"""
        data = {
            "student_id": student_id,
            "question_id": question_id,
            "answer": answer
        }
        response = requests.post(f"{self.base_url}/submit-response", headers=self.headers, json=data)
        return response.json()
    
    def get_student_responses(self, student_id):
        """Get all responses for a student"""
        response = requests.get(f"{self.base_url}/student/{student_id}/responses", headers=self.headers)
        return response.json()

def run_demo():
    """Run a complete API demonstration"""
    print("🤖 AI-CBT Assessment API Demo")
    print("=" * 50)
    
    # Initialize API client
    api = AICBTAPI()
    
    # 1. Health Check
    print("\n1. 🏥 Health Check")
    try:
        health = api.health_check()
        print(f"   Status: {health['status']}")
        print(f"   Version: {health['version']}")
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
        {"name": "Bob Smith", "matric_number": "B87654321"}
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
    if created_students and created_questions:
        sample_responses = [
            {
                "student_id": created_students[0],
                "question_id": created_questions[0],
                "answer": "Photosynthesis is how plants make food using sunlight, water, and carbon dioxide. They produce glucose and oxygen."
            },
            {
                "student_id": created_students[1],
                "question_id": created_questions[1],
                "answer": "The water cycle involves water evaporating from oceans, forming clouds, and then raining back down."
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
    
    # 5. Get Student Progress
    print("\n5. 📊 Checking Student Progress")
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
    run_demo()