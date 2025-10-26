#!/usr/bin/env python3
"""
Test script for Ollama integration in AI-CBT-Theory
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ollama_service import ollama_service, fallback_similarity_score

def test_ollama_connection():
    """Test if Ollama is connected and working"""
    print("🔍 Testing Ollama Connection...")
    
    if ollama_service.check_connection():
        print("✅ Ollama is connected!")
        
        # Get available models
        models = ollama_service.get_available_models()
        print(f"📋 Available models: {models}")
        
        if models:
            return True
        else:
            print("⚠️ No models available. You may need to pull a model first.")
            print("💡 Try: ollama pull llama2")
            return False
    else:
        print("❌ Ollama is not connected.")
        print("💡 Make sure Ollama is running: ollama serve")
        return False

def test_scoring():
    """Test the scoring functionality"""
    print("\n🧪 Testing AI Scoring...")
    
    # Test data
    question = "What is the capital of France?"
    correct_answer = "The capital of France is Paris."
    student_answers = [
        "Paris is the capital of France.",  # Good answer
        "The capital is Paris.",           # Okay answer
        "I think it's London.",            # Wrong answer
        "I don't know."                    # No knowledge
    ]
    
    for i, student_answer in enumerate(student_answers, 1):
        print(f"\n📝 Test Case {i}:")
        print(f"   Question: {question}")
        print(f"   Student Answer: {student_answer}")
        print(f"   Correct Answer: {correct_answer}")
        
        # Test Ollama scoring
        if ollama_service.check_connection():
            result = ollama_service.score_answer(student_answer, correct_answer, question)
            print(f"   🤖 Ollama Score: {result.get('score', 0):.2f}")
            print(f"   📊 Confidence: {result.get('confidence', 0):.2f}")
            print(f"   💭 Feedback: {result.get('feedback', 'No feedback')}")
            if result.get('strengths'):
                print(f"   ✅ Strengths: {result['strengths']}")
            if result.get('weaknesses'):
                print(f"   ❌ Weaknesses: {result['weaknesses']}")
            if result.get('error'):
                print(f"   ⚠️ Error: {result['error']}")
        else:
            # Test fallback scoring
            score = fallback_similarity_score(student_answer, correct_answer)
            print(f"   🔄 Fallback Score: {score:.2f}")

def test_model_switching():
    """Test switching between different models"""
    print("\n🔄 Testing Model Switching...")
    
    available_models = ollama_service.get_available_models()
    if len(available_models) > 1:
        original_model = ollama_service.model
        
        for model in available_models[:2]:  # Test first 2 models
            print(f"\n   Testing with model: {model}")
            ollama_service.model = model
            
            result = ollama_service.score_answer(
                "Paris", 
                "The capital of France is Paris.", 
                "What is the capital of France?"
            )
            print(f"   Score: {result['score']:.2f}, Confidence: {result['confidence']:.2f}")
        
        # Restore original model
        ollama_service.model = original_model
    else:
        print("   ⚠️ Only one model available, skipping model switching test")

def main():
    """Run all tests"""
    print("🧠 AI-CBT-Theory Ollama Integration Test")
    print("=" * 50)
    
    # Test 1: Connection
    if test_ollama_connection():
        # Test 2: Scoring
        test_scoring()
        
        # Test 3: Model switching
        test_model_switching()
        
        print("\n✅ All tests completed!")
        print("\n💡 Next steps:")
        print("   1. Start the Flask app: python app.py")
        print("   2. Visit: http://localhost:5000")
        print("   3. Check Ollama status: http://localhost:5000/ollama-status")
        
    else:
        print("\n❌ Ollama connection failed.")
        print("\n🛠️ Setup instructions:")
        print("   1. Install Ollama: curl -fsSL https://ollama.ai/install.sh | sh")
        print("   2. Start Ollama: ollama serve")
        print("   3. Pull a model: ollama pull llama2")
        print("   4. Run this test again")
    
    print("\n🚀 To start the full application:")
    print("   cd /Users/macbook/Ai-CBT-Theory/src")
    print("   python app.py")

if __name__ == "__main__":
    main()
