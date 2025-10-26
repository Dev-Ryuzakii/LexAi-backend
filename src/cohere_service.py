"""
Cohere AI Service for the AI-CBT Platform
"""
import cohere
import os
import logging
from typing import Dict, Any
from ollama_service import ResponseCache, fallback_similarity_score

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CohereService:
    def __init__(self):
        self.api_key = None
        self.model = "command"
        self.client = None
        self.cache = ResponseCache()
        self.health_status = type('obj', (object,), {'healthy': False})()
        
    def check_connection(self) -> bool:
        """Check if Cohere service is available"""
        try:
            if not self.api_key:
                logger.warning("Cohere API key not set")
                self.health_status.healthy = False
                return False
                
            self.client = cohere.Client(self.api_key)
            # Simple test request
            self.client.tokenize(text="test")
            self.health_status.healthy = True
            logger.info("Cohere service connection successful")
            return True
        except Exception as e:
            logger.error(f"Cohere service connection failed: {e}")
            self.health_status.healthy = False
            return False
    
    def score_answer(self, student_answer: str, marking_guide: str, question: str = "") -> Dict[str, Any]:
        """Score student answer using Cohere"""
        # Check cache first
        cache_key = f"{student_answer}|{marking_guide}|{question}"
        cached_result = self.cache.get(cache_key)
        if cached_result:
            logger.info("Using cached result for Cohere scoring")
            return cached_result
            
        if not self.client:
            if not self.check_connection():
                raise Exception("Cohere service not available")
        
        try:
            # Create a comprehensive prompt for scoring
            prompt = f"""
Question: {question}

Marking Guide: {marking_guide}

Student Answer: {student_answer}

Task: Analyze the student's answer and provide:
1. A numerical score from 0-10
2. Confidence level (0-100%)
3. Detailed feedback explaining the score
4. Specific strengths in the answer
5. Specific weaknesses in the answer

Format your response as JSON:
{{
    "score": [numerical score 0-10],
    "confidence": [confidence level 0-100],
    "feedback": "[detailed feedback]",
    "strengths": ["strength1", "strength2"],
    "weaknesses": ["weakness1", "weakness2"]
}}
"""
            
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                max_tokens=500,
                temperature=0.3
            )
            
            # Parse the response
            import json
            try:
                result = json.loads(response.generations[0].text)
            except json.JSONDecodeError:
                # Fallback parsing if JSON is not properly formatted
                text = response.generations[0].text
                result = {
                    "score": 5,
                    "confidence": 70,
                    "feedback": text,
                    "strengths": [],
                    "weaknesses": []
                }
            
            # Ensure score is within bounds
            result["score"] = max(0, min(10, result.get("score", 0)))
            result["confidence"] = max(0, min(100, result.get("confidence", 0)))
            result["model_used"] = self.model
            
            # Cache the result
            self.cache.set(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error scoring with Cohere: {e}")
            # Fallback to simple similarity scoring
            score = fallback_similarity_score(student_answer, marking_guide)
            return {
                "score": score,
                "confidence": 50,
                "feedback": f"Fallback scoring due to Cohere error: {str(e)}",
                "strengths": [],
                "weaknesses": [],
                "model_used": "fallback"
            }

# Create a global instance
cohere_service = CohereService()