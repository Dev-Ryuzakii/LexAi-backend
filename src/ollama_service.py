"""
Ollama service module for AI-powered answer scoring
"""
import requests
import json
import logging
import re
import time
import hashlib
import random
from datetime import datetime
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResponseCache:
    """Simple cache for Ollama responses to improve performance and reduce API load"""
    def __init__(self, max_size=1000, ttl=3600):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl  # Time to live in seconds
        
    def _generate_key(self, student_answer, marking_guide, question):
        """Generate a unique key for the cache based on the input"""
        combined = f"{student_answer.strip().lower()}|{marking_guide.strip().lower()}|{question.strip().lower()}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def get(self, student_answer, marking_guide, question):
        """Get cached response if available and not expired"""
        key = self._generate_key(student_answer, marking_guide, question)
        if key in self.cache:
            timestamp, response = self.cache[key]
            if time.time() - timestamp <= self.ttl:
                logger.info("Cache hit for scoring request")
                return response
            else:
                # Remove expired entry
                del self.cache[key]
        return None
    
    def set(self, student_answer, marking_guide, question, response):
        """Cache a response"""
        key = self._generate_key(student_answer, marking_guide, question)
        self.cache[key] = (time.time(), response)
        
        # Trim cache if it exceeds max size
        if len(self.cache) > self.max_size:
            # Remove oldest entries
            sorted_keys = sorted(self.cache.items(), key=lambda x: x[1][0])
            for k, _ in sorted_keys[:int(self.max_size * 0.2)]:  # Remove oldest 20%
                del self.cache[k]

class OllamaService:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2:latest"):
        """
        Initialize Ollama service with enhanced features
        
        Args:
            base_url: Ollama server URL
            model: Model to use for inference (llama3.2:latest, llama2, mistral, etc.)
        """
        self.base_url = base_url
        self.model = model
        self.api_url = f"{base_url}/api/generate"
        self.response_cache = ResponseCache()
        self.available_models = []
        self.health_status = {
            "healthy": False,
            "last_check": None,
            "error": None
        }
        self.retries = 3
        self.backoff_factor = 2
        self.timeout = 60
        
        # Initialize health check
        self._check_health()
        
    def _check_health(self) -> None:
        """Internal health check of Ollama service"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                self.health_status = {
                    "healthy": True,
                    "last_check": datetime.now().isoformat(),
                    "error": None
                }
                
                # Update available models
                data = response.json()
                self.available_models = [model["name"] for model in data.get("models", [])]
            else:
                self.health_status = {
                    "healthy": False,
                    "last_check": datetime.now().isoformat(),
                    "error": f"Unexpected status code: {response.status_code}"
                }
        except requests.exceptions.RequestException as e:
            self.health_status = {
                "healthy": False,
                "last_check": datetime.now().isoformat(),
                "error": str(e)
            }
        except Exception as e:
            self.health_status = {
                "healthy": False,
                "last_check": datetime.now().isoformat(),
                "error": f"Unexpected error: {str(e)}"
            }
    
    def check_connection(self) -> bool:
        """
        Public health check of Ollama service
        
        Returns:
            Boolean indicating if the service is available
        """
        # Only re-check if last check was more than 30 seconds ago
        if (not self.health_status["last_check"] or 
            (datetime.now() - datetime.fromisoformat(self.health_status["last_check"])).total_seconds() > 30):
            self._check_health()
            
        return self.health_status["healthy"]
    
    def score_answer(self, student_answer: str, marking_guide: str, question: str = "") -> Dict[str, Any]:
        """
        Score a student answer against a marking guide using Ollama with caching
        
        Args:
            student_answer: The student's answer
            marking_guide: The correct answer/marking guide
            question: The original question (optional for context)
            
        Returns:
            Dictionary containing score, feedback and metadata
        """
        # Input validation
        if not student_answer or not marking_guide:
            return {
                "score": 0,
                "confidence": 0.0,
                "feedback": "Missing student answer or marking guide",
                "strengths": [],
                "weaknesses": [],
                "model_used": "none",
                "scoring_method": "error"
            }
        
        # Try cache first
        cached_response = self.response_cache.get(student_answer, marking_guide, question)
        if cached_response:
            # Add cache info to response
            cached_response["cached"] = True
            return cached_response
            
        # Tracking for which method was used to score
        scoring_method = "ollama"
        model_used = self.model
        
        try:
            # Check Ollama connectivity first
            if self.check_connection():
                # Create a prompt for the AI to score the answer
                prompt = self._create_scoring_prompt(student_answer, marking_guide, question)
                
                for attempt in range(self.retries):
                    try:
                        response = self._call_ollama(prompt)
                        result = self._parse_scoring_response(response)
                        
                        # Add metadata
                        result["model_used"] = self.model
                        result["scoring_method"] = "ollama"
                        
                        # Cache successful response
                        self.response_cache.set(student_answer, marking_guide, question, result)
                        
                        return result
                    except requests.exceptions.Timeout:
                        logger.warning(f"Ollama timeout on attempt {attempt+1}/{self.retries}")
                        time.sleep(self.backoff_factor * (attempt + 1))
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Ollama request error on attempt {attempt+1}/{self.retries}: {e}")
                        time.sleep(self.backoff_factor * (attempt + 1))
                        
                # If we get here, all attempts failed
                logger.error(f"All {self.retries} attempts to call Ollama failed")
                scoring_method = "fallback_ml"
            else:
                logger.warning("Ollama service unavailable, using fallback")
                scoring_method = "fallback_ml"
                
            # Try ML model fallback
            try:
                import joblib
                import pandas as pd
                from sklearn.metrics.pairwise import cosine_similarity
                
                model = joblib.load('../models/marking_model.pkl')
                vectorizer = joblib.load('../models/vectorizer.pkl')
                
                # Vectorize inputs
                from sklearn.feature_extraction.text import TfidfVectorizer
                vectorizer = TfidfVectorizer(stop_words='english')
                
                # Process and vectorize
                processed_answer = student_answer.lower()
                processed_guide = marking_guide.lower()
                
                X = vectorizer.fit_transform([processed_answer, processed_guide])
                similarity = cosine_similarity(X[0:1], X[1:2])[0][0]
                
                # Convert to 0-5 scale
                score = int(round(similarity * 5))
                score = max(0, min(5, score))
                
                result = {
                    "score": score,
                    "confidence": 0.7,
                    "feedback": f"Answer similarity score: {score}/5. Based on text comparison with the marking guide.",
                    "strengths": ["Points reflected in the marking guide"],
                    "weaknesses": ["Detailed feedback not available in fallback mode"],
                    "model_used": "ml_fallback",
                    "scoring_method": scoring_method
                }
                
                # Cache fallback response
                self.response_cache.set(student_answer, marking_guide, question, result)
                
                return result
            except Exception as e:
                logger.error(f"ML fallback failed: {e}")
                scoring_method = "basic_similarity"
                
            # Ultimate text similarity fallback
            score = fallback_similarity_score(student_answer, marking_guide)
            result = {
                "score": score,
                "confidence": 0.5,
                "feedback": f"Basic similarity score: {score}/5. Based on word overlap analysis.",
                "strengths": [],
                "weaknesses": ["Could not perform detailed analysis"],
                "model_used": "basic_similarity",
                "scoring_method": scoring_method
            }
            
            # Cache basic fallback response
            self.response_cache.set(student_answer, marking_guide, question, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Complete scoring failure: {e}")
            return {
                "score": 0,
                "confidence": 0.0,
                "feedback": "Error occurred during scoring. Please try again later.",
                "strengths": [],
                "weaknesses": [],
                "error": str(e),
                "model_used": "error",
                "scoring_method": "error"
            }
    
    def _create_scoring_prompt(self, student_answer: str, marking_guide: str, question: str = "") -> str:
        """Create a prompt for scoring the student answer"""
        prompt = f"""
You are an expert educator tasked with scoring student answers based on MEANING and UNDERSTANDING, not exact word matching.

Question: {question if question else "Not provided"}

Marking Guide/Expected Answer:
{marking_guide}

Student's Answer:
{student_answer}

Your task:
- Compare the MEANING of the student's answer with the marking guide
- The student's answer does NOT need to be word-for-word identical
- Focus on whether the student demonstrates understanding of the concept
- Award points based on how well the meaning aligns with the marking guide

Scoring Scale (INTEGER ONLY):
- 5: Excellent understanding, meaning perfectly aligns with marking guide
- 4: Good understanding, meaning mostly aligns with minor gaps
- 3: Adequate understanding, meaning somewhat aligns but missing some key points
- 2: Basic understanding, meaning partially aligns but significant gaps
- 1: Poor understanding, meaning barely aligns with marking guide
- 0: No understanding, meaning does not align or is completely incorrect

Please provide your response in the following JSON format:
{{
    "score": 4,
    "confidence": 0.9,
    "feedback": "The student demonstrates good understanding of the concept. The meaning aligns well with the marking guide despite different wording.",
    "strengths": ["Correct core concept", "Good explanation"],
    "weaknesses": ["Could be more detailed", "Missing one key point"]
}}

Important: 
- Score must be an INTEGER between 0-5
- Focus on MEANING and UNDERSTANDING, not exact words
- Consider different ways of expressing the same concept as correct

Respond only with the JSON object, no additional text.
"""
        return prompt
    
    def _call_ollama(self, prompt: str) -> str:
        """
        Make API call to Ollama with enhanced error handling and retries
        
        Args:
            prompt: The prompt to send to Ollama
            
        Returns:
            String response from Ollama
            
        Raises:
            Exception: Various exceptions for different failure modes
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for consistent scoring
                "top_p": 0.9,
                "num_predict": 500,  # Limit response length
                "stop": ["```"]  # Stop generating at code blocks
            }
        }
        
        # Implement retry logic with exponential backoff
        max_retries = self.retries
        base_delay = 1  # Start with 1 second delay
        
        for retry_num in range(max_retries + 1):  # +1 for initial attempt
            start_time = time.time()
            
            try:
                response = requests.post(
                    self.api_url,
                    json=payload,
                    timeout=self.timeout  # Use instance timeout
                )
                response.raise_for_status()
                
                result = response.json()
                api_response = result.get("response", "")
                
                # Log performance metrics
                processing_time = time.time() - start_time
                logger.info(f"Ollama API call completed in {processing_time:.2f}s")
                
                return api_response
            except requests.exceptions.Timeout:
                logger.error(f"Ollama request timed out after {self.timeout}s (attempt {retry_num+1}/{max_retries+1})")
                self.health_status["healthy"] = False
                self.health_status["error"] = "Timeout"
                
                if retry_num == max_retries:  # Last attempt failed
                    raise Exception("Request timed out - model may be loading or overloaded")
                    
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if hasattr(e, 'response') else "unknown"
                logger.error(f"HTTP error {status_code} (attempt {retry_num+1}/{max_retries+1}): {e}")
                
                # Log response content for debugging
                if 'response' in locals():
                    logger.error(f"Response content: {response.text}")
                
                if retry_num == max_retries:  # Last attempt failed
                    if status_code == 404:
                        raise Exception(f"Model {self.model} not found on Ollama server")
                    elif status_code == 500:
                        raise Exception("Ollama server internal error")
                    else:
                        raise Exception(f"HTTP error {status_code}: {e}")
                    
            except requests.exceptions.ConnectionError:
                logger.error(f"Ollama server connection failed (attempt {retry_num+1}/{max_retries+1})")
                self.health_status["healthy"] = False
                self.health_status["error"] = "Connection Error"
                
                if retry_num == max_retries:  # Last attempt failed
                    raise Exception("Could not connect to Ollama server - is it running?")
                
            except Exception as e:
                logger.error(f"Unexpected error calling Ollama (attempt {retry_num+1}/{max_retries+1}): {e}")
                
                if retry_num == max_retries:  # Last attempt failed
                    raise Exception(f"Unexpected error: {e}")
            
            # Calculate delay with exponential backoff and jitter
            if retry_num < max_retries:
                import random
                delay = base_delay * (2 ** retry_num)  # Exponential backoff
                jitter = random.uniform(0, delay * 0.5)  # Add jitter up to 50% of delay
                total_delay = delay + jitter
                logger.info(f"Retrying in {total_delay:.2f} seconds...")
                time.sleep(total_delay)
            
        # If we exit the loop without returning, all attempts failed
        logger.error(f"All {max_retries+1} Ollama API call attempts failed")
        raise Exception("All API call attempts failed")
    
    def _parse_scoring_response(self, response: str) -> Dict[str, Any]:
        """Parse the scoring response from Ollama"""
        try:
            # Try to extract JSON from the response
            response = response.strip()
            
            # Find JSON object in the response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != 0:
                json_str = response[start_idx:end_idx]
                parsed = json.loads(json_str)
                
                # Validate and clean the parsed response
                score = int(parsed.get("score", 0))  # Convert to integer
                score = max(0, min(5, score))  # Clamp between 0 and 5
                
                return {
                    "score": score,
                    "confidence": float(parsed.get("confidence", 0.5)),
                    "feedback": parsed.get("feedback", "No feedback provided"),
                    "strengths": parsed.get("strengths", []),
                    "weaknesses": parsed.get("weaknesses", [])
                }
            else:
                raise ValueError("No valid JSON found in response")
                
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Failed to parse Ollama response: {e}")
            logger.error(f"Response was: {response}")
            
            # Fallback: try to extract just a number if JSON parsing fails
            try:
                # Look for numbers in the response that could be scores (0-5)
                import re
                numbers = re.findall(r'[0-5]', response)
                if numbers:
                    score = int(numbers[0])
                    score = max(0, min(5, score))
                    return {
                        "score": score,
                        "confidence": 0.5,
                        "feedback": "Basic scoring (parsing failed)",
                        "strengths": [],
                        "weaknesses": []
                    }
            except:
                pass
            
            return {
                "score": 0,
                "confidence": 0.0,
                "feedback": "Failed to parse scoring response",
                "strengths": [],
                "weaknesses": []
            }
    
    def get_available_models(self) -> list:
        """Get list of available models from Ollama"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
            return []
        except requests.exceptions.RequestException:
            return []
    
    def pull_model(self, model_name: str) -> bool:
        """Pull a model if it's not available"""
        try:
            payload = {"name": model_name}
            response = requests.post(f"{self.base_url}/api/pull", json=payload, timeout=300)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False

# Create a global instance
ollama_service = OllamaService()

# Fallback scoring function for when Ollama is not available
def fallback_similarity_score(student_answer: str, marking_guide: str) -> int:
    """
    Simple fallback scoring based on text similarity
    Used when Ollama is not available
    Returns integer score 0-5
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        
        vectorizer = TfidfVectorizer(stop_words='english', lowercase=True)
        texts = [student_answer.lower(), marking_guide.lower()]
        tfidf_matrix = vectorizer.fit_transform(texts)
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        
        # Convert similarity (0.0-1.0) to integer score (0-5)
        score = int(similarity * 5)
        return max(0, min(5, score))
    except Exception:
        # Ultimate fallback - simple word overlap
        student_words = set(student_answer.lower().split())
        guide_words = set(marking_guide.lower().split())
        
        if not guide_words:
            return 0
        
        overlap = len(student_words.intersection(guide_words))
        similarity = overlap / len(guide_words)
        score = int(similarity * 5)
        return max(0, min(5, score))
