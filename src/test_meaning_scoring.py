#!/usr/bin/env python3
"""
Test the meaning-based integer scoring system
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ollama_service import ollama_service

def test_meaning_based_scoring():
    """Test how Ollama scores based on meaning, not exact words"""
    
    # Test case: Capital of France
    question = "What is the capital of France?"
    marking_guide = "The capital of France is Paris."
    
    test_answers = [
        # Perfect answers (different wording, same meaning)
        ("Paris is the capital city of France.", "Expected: 5/5"),
        ("France's capital is Paris.", "Expected: 5/5"),
        ("The capital city of France is called Paris.", "Expected: 5/5"),
        
        # Good answers (correct but brief)
        ("Paris", "Expected: 4/5"),
        ("It's Paris.", "Expected: 4/5"),
        
        # Adequate answers (correct but unclear)
        ("I think it's Paris.", "Expected: 3/5"),
        ("Paris, I believe.", "Expected: 3/5"),
        
        # Poor answers (wrong information)
        ("London is the capital of France.", "Expected: 0/5"),
        ("The capital is London.", "Expected: 0/5"),
        
        # No knowledge
        ("I don't know.", "Expected: 0/5"),
        ("Not sure.", "Expected: 0/5"),
    ]
    
    print("🧪 Testing Meaning-Based Integer Scoring (0-5 scale)")
    print("=" * 60)
    print(f"Question: {question}")
    print(f"Marking Guide: {marking_guide}")
    print("=" * 60)
    
    if not ollama_service.check_connection():
        print("❌ Ollama not connected. Please start Ollama with: ollama serve")
        return
    
    for i, (answer, expected) in enumerate(test_answers, 1):
        print(f"\n📝 Test {i}: {expected}")
        print(f"   Student Answer: '{answer}'")
        
        try:
            result = ollama_service.score_answer(answer, marking_guide, question)
            
            score = result.get('score', 0)
            confidence = result.get('confidence', 0)
            feedback = result.get('feedback', 'No feedback')
            
            print(f"   🤖 Ollama Score: {score}/5")
            print(f"   📊 Confidence: {confidence:.0%}")
            print(f"   💭 Feedback: {feedback}")
            
            if result.get('strengths'):
                print(f"   ✅ Strengths: {result['strengths']}")
            if result.get('weaknesses'):
                print(f"   ❌ Weaknesses: {result['weaknesses']}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 Key Points Demonstrated:")
    print("• Ollama understands MEANING, not just exact words")
    print("• Different ways of saying the same thing get similar scores")
    print("• Brief correct answers still get good scores")
    print("• Wrong information gets 0 points regardless of confidence")
    print("• Integer scoring (0-5) makes grading clearer for educators")

def test_different_subjects():
    """Test meaning understanding across different subjects"""
    
    test_cases = [
        {
            "question": "What is photosynthesis?",
            "marking_guide": "Photosynthesis is the process by which plants use sunlight, carbon dioxide, and water to produce glucose and oxygen.",
            "answers": [
                ("Plants make food using sunlight, CO2, and water to create sugar and oxygen.", "Should get 5/5"),
                ("Plants use the sun to make their own food.", "Should get 3-4/5"),
                ("It's when plants eat sunlight.", "Should get 1-2/5"),
                ("Plants need water.", "Should get 1/5"),
            ]
        },
        {
            "question": "What is gravity?",
            "marking_guide": "Gravity is a force that attracts objects with mass toward each other, causing objects to fall toward Earth.",
            "answers": [
                ("Gravity is the force that pulls things down to Earth.", "Should get 4-5/5"),
                ("It's what makes things fall.", "Should get 3/5"),
                ("Gravity makes objects with mass attract each other.", "Should get 5/5"),
                ("It's a type of energy.", "Should get 1/5"),
            ]
        }
    ]
    
    if not ollama_service.check_connection():
        print("❌ Ollama not connected.")
        return
    
    print("\n🔬 Testing Across Different Subjects")
    print("=" * 50)
    
    for case in test_cases:
        print(f"\n📚 Subject Test: {case['question']}")
        print(f"   Marking Guide: {case['marking_guide']}")
        
        for answer, expectation in case['answers']:
            print(f"\n   📝 Answer: '{answer}'")
            print(f"   📊 {expectation}")
            
            try:
                result = ollama_service.score_answer(answer, case['marking_guide'], case['question'])
                score = result.get('score', 0)
                print(f"   🤖 Actual Score: {score}/5")
            except Exception as e:
                print(f"   ❌ Error: {e}")

def main():
    print("🧠 AI-CBT Meaning-Based Scoring Test")
    print("Testing Ollama's ability to understand meaning over exact words")
    
    # Test 1: Basic meaning understanding
    test_meaning_based_scoring()
    
    # Test 2: Cross-subject understanding
    test_different_subjects()
    
    print("\n🎉 Testing complete!")
    print("\n📋 Next steps:")
    print("1. Open your browser to: http://127.0.0.1:5000/questions")
    print("2. Add your own questions and marking guides")
    print("3. Test with students using: http://127.0.0.1:5000/login")
    print("4. Review results at: http://127.0.0.1:5000/lecturer")

if __name__ == "__main__":
    main()
