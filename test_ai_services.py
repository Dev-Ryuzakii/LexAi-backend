#!/usr/bin/env python3
"""
Test script for AI services integration
"""
import sys
import os

# Add src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from ai_service_manager import ai_service_manager

def test_ai_services():
    """Test all AI services with a sample question"""
    
    # Sample test data
    student_answer = "Photosynthesis is the process where plants use sunlight to make food."
    marking_guide = "Photosynthesis is the process by which plants convert light energy into chemical energy using chlorophyll."
    question = "Explain the process of photosynthesis."
    
    print("AI-CBT Assessment Platform - AI Services Test")
    print("=" * 50)
    print(f"Question: {question}")
    print(f"Student Answer: {student_answer}")
    print(f"Marking Guide: {marking_guide}")
    print("=" * 50)
    
    # Test each service
    services = ['ollama', 'palm', 'cohere', 'huggingface']
    
    for service_name in services:
        print(f"\nTesting {service_name.upper()} service:")
        print("-" * 30)
        
        # Set as active service
        if ai_service_manager.set_active_service(service_name):
            # Score the answer
            result = ai_service_manager.score_answer(student_answer, marking_guide, question)
            
            print(f"Score: {result.get('score', 'N/A')}/5")
            print(f"Confidence: {result.get('confidence', 'N/A')}")
            print(f"Feedback: {result.get('feedback', 'N/A')}")
            print(f"Strengths: {result.get('strengths', 'N/A')}")
            print(f"Weaknesses: {result.get('weaknesses', 'N/A')}")
        else:
            print(f"Service {service_name} not available or not configured")
    
    # Show service status
    print("\n\nService Status:")
    print("=" * 30)
    status = ai_service_manager.get_service_status()
    for service, info in status.items():
        print(f"{service}: {'Connected' if info['connected'] else 'Disconnected'}")
        if 'error' in info:
            print(f"  Error: {info['error']}")

if __name__ == "__main__":
    test_ai_services()