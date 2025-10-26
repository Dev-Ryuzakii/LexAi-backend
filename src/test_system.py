#!/usr/bin/env python3
"""
Test script to add sample questions and demonstrate the AI-CBT system
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, Question, Student, Response
from ollama_service import ollama_service

def add_sample_questions():
    """Add sample questions for testing"""
    session_db = SessionLocal()
    
    sample_questions = [
        {
            "question_text": "What is the capital of France and what is its significance?",
            "marking_guide": "The capital of France is Paris. It is significant as the political, economic, and cultural center of France, home to major landmarks like the Eiffel Tower, Louvre Museum, and government institutions."
        },
        {
            "question_text": "Explain the concept of photosynthesis.",
            "marking_guide": "Photosynthesis is the process by which green plants and some other organisms use sunlight, carbon dioxide, and water to produce glucose and oxygen. The process occurs in chloroplasts and involves light-dependent and light-independent reactions."
        },
        {
            "question_text": "What are the main principles of object-oriented programming?",
            "marking_guide": "The main principles of object-oriented programming are: 1) Encapsulation - bundling data and methods together, 2) Inheritance - creating new classes based on existing ones, 3) Polymorphism - same interface for different types, and 4) Abstraction - hiding complex implementation details."
        },
        {
            "question_text": "Describe the water cycle.",
            "marking_guide": "The water cycle is the continuous process of water movement on Earth. It includes evaporation from water bodies, transpiration from plants, condensation forming clouds, precipitation as rain or snow, and collection back into water bodies. Solar energy drives this cycle."
        },
        {
            "question_text": "What is artificial intelligence and give two examples of its applications?",
            "marking_guide": "Artificial Intelligence (AI) is the simulation of human intelligence in machines that are programmed to think and learn. Examples include: 1) Natural Language Processing (like chatbots and translation services), 2) Computer Vision (like facial recognition and autonomous vehicles), 3) Machine Learning (like recommendation systems and fraud detection)."
        }
    ]
    
    # Check if questions already exist
    existing_count = session_db.query(Question).count()
    if existing_count > 0:
        print(f"Found {existing_count} existing questions. Skipping question creation.")
        session_db.close()
        return
    
    print("Adding sample questions...")
    for i, q in enumerate(sample_questions, 1):
        question = Question(
            question_text=q["question_text"],
            marking_guide=q["marking_guide"]
        )
        session_db.add(question)
        print(f"  {i}. {q['question_text'][:50]}...")
    
    session_db.commit()
    session_db.close()
    print("✅ Sample questions added successfully!")

def simulate_student_answers():
    """Simulate various student answers for testing"""
    session_db = SessionLocal()
    
    # Get all questions
    questions = session_db.query(Question).all()
    if not questions:
        print("❌ No questions found. Please add questions first.")
        session_db.close()
        return
    
    # Sample student answers with varying quality
    test_students = [
        {
            "name": "Alice Johnson",
            "matric_number": "TEST001",
            "answers": [
                "Paris is the capital of France. It's a beautiful city with the Eiffel Tower and many museums.",
                "Photosynthesis is when plants make food using sunlight, water and carbon dioxide.",
                "OOP has encapsulation, inheritance, polymorphism and abstraction.",
                "Water evaporates, forms clouds, rains, and goes back to rivers and oceans.",
                "AI is computer intelligence. Examples are Siri and self-driving cars."
            ]
        },
        {
            "name": "Bob Smith",
            "matric_number": "TEST002", 
            "answers": [
                "Paris",
                "Plants use sun to make sugar",
                "I don't know much about programming",
                "Water goes up and comes down as rain",
                "AI is robots and stuff"
            ]
        },
        {
            "name": "Carol Davis",
            "matric_number": "TEST003",
            "answers": [
                "The capital of France is Paris, which serves as the political, economic, and cultural hub of the nation. It houses important government institutions, world-renowned museums like the Louvre, and iconic landmarks such as the Eiffel Tower.",
                "Photosynthesis is a complex biological process where chlorophyll-containing organisms convert light energy, carbon dioxide, and water into glucose and oxygen through light-dependent and light-independent reactions occurring in chloroplasts.",
                "Object-oriented programming is built on four main principles: encapsulation (data hiding), inheritance (code reuse through class hierarchies), polymorphism (one interface, multiple implementations), and abstraction (simplifying complex systems).",
                "The water cycle is a continuous process driven by solar energy involving evaporation from water bodies, transpiration from vegetation, condensation into clouds, precipitation, and collection back into water reservoirs.",
                "Artificial Intelligence refers to machine systems that simulate human cognitive functions. Applications include natural language processing in chatbots, computer vision in autonomous vehicles, and machine learning in recommendation algorithms."
            ]
        }
    ]
    
    print("\n🧪 Simulating student test sessions...")
    
    for student_data in test_students:
        print(f"\n📝 Testing with student: {student_data['name']}")
        
        # Create or get student
        existing_student = session_db.query(Student).filter_by(matric_number=student_data['matric_number']).first()
        if existing_student:
            print(f"   Student already exists, skipping...")
            continue
            
        student = Student(
            name=student_data['name'],
            matric_number=student_data['matric_number'],
            score=0
        )
        session_db.add(student)
        session_db.commit()
        
        # Answer questions
        total_score = 0
        for i, (question, answer) in enumerate(zip(questions[:len(student_data['answers'])], student_data['answers'])):
            print(f"   Question {i+1}: {question.question_text[:40]}...")
            print(f"   Answer: {answer[:40]}...")
            
            # Score with Ollama
            if ollama_service.check_connection():
                scoring_result = ollama_service.score_answer(answer, question.marking_guide, question.question_text)
                score = scoring_result["score"]
                ai_feedback = scoring_result["feedback"]
                ai_confidence = scoring_result["confidence"] 
                ai_strengths = str(scoring_result["strengths"])
                ai_weaknesses = str(scoring_result["weaknesses"])
                print(f"   🤖 Ollama Score: {score:.2f} (Confidence: {ai_confidence:.2f})")
            else:
                print("   ⚠️ Ollama not available, using fallback scoring")
                score = 0.5  # Fallback score
                ai_feedback = "Ollama not available during test"
                ai_confidence = 0.0
                ai_strengths = "[]"
                ai_weaknesses = "[]"
            
            # Save response
            response = Response(
                student_id=student.id,
                question_id=question.id,
                answer=answer,
                score=score,
                ai_score=score,
                ai_feedback=ai_feedback,
                ai_confidence=ai_confidence,
                ai_strengths=ai_strengths,
                ai_weaknesses=ai_weaknesses
            )
            session_db.add(response)
            total_score += score
        
        student.score = total_score
        session_db.commit()
        print(f"   ✅ Total Score: {total_score:.2f}")
    
    session_db.close()
    print("\n✅ Test simulation completed!")

def main():
    print("🧪 AI-CBT System Test Setup")
    print("=" * 40)
    
    # Step 1: Add sample questions
    add_sample_questions()
    
    # Step 2: Simulate student answers
    simulate_student_answers()
    
    print("\n🎉 Test setup complete!")
    print("\n📋 Next steps to test the system:")
    print("1. Visit the lecturer dashboard: http://127.0.0.1:5000/lecturer")
    print("2. Try logging in as a new student: http://127.0.0.1:5000/login")
    print("3. Check Ollama status: http://127.0.0.1:5000/ollama-status")
    print("4. Manage questions: http://127.0.0.1:5000/questions")
    
    print("\n🧑‍🎓 Manual testing suggestions:")
    print("• Log in with different student names and matric numbers")
    print("• Try answering questions with varying quality:")
    print("  - Excellent answers (detailed and accurate)")
    print("  - Good answers (correct but brief)")
    print("  - Poor answers (incorrect or incomplete)")
    print("  - Very poor answers ('I don't know')")
    print("• Check how Ollama scores different answer qualities")
    print("• Test the lecturer override functionality")

if __name__ == "__main__":
    main()
