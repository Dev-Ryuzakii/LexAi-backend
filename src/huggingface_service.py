"""
Hugging Face service module for AI-powered answer scoring
"""
import requests
import json
import logging
import time
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from ollama_service import ResponseCache, fallback_similarity_score

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HuggingFaceService:
    def __init__(self, api_key: str = "", model: str = "google/flan-t5-base"):
        """
        Initialize Hugging Face service with enhanced features
        
        Args:
            api_key: Hugging Face API key
            model: Model to use for inference (google/flan-t5-base, etc.)
        """
        self.api_key = api_key
        self.model = model
        self.api_url = f"https://api-inference.huggingface.co/models/{model}"
        self.response_cache = ResponseCache()
        self.health_status = {
            "healthy": False,
            "last_check": None,
            "error": None
        }
        self.retries = 3
        self.backoff_factor = 2
        self.timeout = 60
        self.wait_for_model = True
        
        # Initialize health check
        self._check_health()
        
    def _check_health(self) -> None:
        """Internal health check of Hugging Face service"""
        try:
            if not self.api_key:
                self.health_status = {
                    "healthy": False,
                    "last_check": datetime.now().isoformat(),
                    "error": "API key not provided"
                }
                return
                
            # Simple check by making a minimal API call
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            test_payload = {
                "inputs": "Hello"
            }
            
            response = requests.post(self.api_url, headers=headers, json=test_payload, timeout=5)
            
            if response.status_code == 200:
                self.health_status = {
                    "healthy": True,
                    "last_check": datetime.now().isoformat(),
                    "error": None
                }
            elif response.status_code == 401:
                self.health_status = {
                    "healthy": False,
                    "last_check": datetime.now().isoformat(),
                    "error": "Invalid API key"
                }
            elif response.status_code == 404:
                self.health_status = {
                    "healthy": False,
                    "last_check": datetime.now().isoformat(),
                    "error": f"Model {self.model} not found"
                }
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
        Public health check of Hugging Face service
        
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
        Score a student answer against a marking guide using Hugging Face with caching
        
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
        scoring_method = "huggingface"
        model_used = self.model
        
        try:
            # Check Hugging Face connectivity first
            if self.check_connection():
                # Create a prompt for the AI to score the answer
                prompt = self._create_scoring_prompt(student_answer, marking_guide, question)
                
                for attempt in range(self.retries):
                    try:
                        response = self._call_huggingface(prompt)
                        result = self._parse_scoring_response(response)
                        
                        # Add metadata
                        result["model_used"] = self.model
                        result["scoring_method"] = "huggingface"
                        
                        # Cache successful response
                        self.response_cache.set(student_answer, marking_guide, question, result)
                        
                        return result
                    except requests.exceptions.Timeout:
                        logger.warning(f"Hugging Face timeout on attempt {attempt+1}/{self.retries}")
                        time.sleep(self.backoff_factor * (attempt + 1))
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Hugging Face request error on attempt {attempt+1}/{self.retries}: {e}")
                        time.sleep(self.backoff_factor * (attempt + 1))
                        
                # If we get here, all attempts failed
                logger.error(f"All {self.retries} attempts to call Hugging Face failed")
                scoring_method = "fallback_ml"
            else:
                logger.warning("Hugging Face service unavailable, using fallback")
                scoring_method = "fallback_ml"
                
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
Task: Score this student answer based on meaning and understanding.

Question: {question if question else "Not provided"}

Marking Guide:
{marking_guide}

Student Answer:
{student_answer}

Scoring Scale (0-5):
0: No understanding
1: Poor understanding
2: Basic understanding
3: Adequate understanding
4: Good understanding
5: Excellent understanding

Provide response in JSON format:
{{
    "score": 4,
    "confidence": 0.9,
    "feedback": "The student demonstrates good understanding...",
    "strengths": ["Correct core concept"],
    "weaknesses": ["Missing one key point"]
}}
"""
        return prompt
    
    def _call_huggingface(self, prompt: str) -> str:
        """
        Make API call to Hugging Face with enhanced error handling and retries
        
        Args:
            prompt: The prompt to send to Hugging Face
            
        Returns:
            String response from Hugging Face
            
        Raises:
            Exception: Various exceptions for different failure modes
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 500,
                "temperature": 0.1,  # Low temperature for consistent scoring
                "top_p": 0.9,
                "return_full_text": False
            },
            "options": {
                "wait_for_model": self.wait_for_model
            }
        }
        
        # Implement retry logic with exponential backoff
        max_retries = self.retries
        base_delay = 1  # Start with 1 second delay
        
        for retry_num in range(max_retries + 1):  # +1 for initial attempt
            start_time = time.time()
            response = None  # Initialize response variable
            
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout  # Use instance timeout
                )
                
                # Handle model loading case
                if response.status_code == 503:
                    result = response.json()
                    if "estimated_time" in result:
                        estimated_time = result.get("estimated_time", 30)
                        logger.info(f"Model loading, waiting for {min(estimated_time, 60)} seconds...")
                        time.sleep(min(estimated_time, 60))
                        continue  # Retry the request
                
                response.raise_for_status()
                
                result = response.json()
                
                if isinstance(result, list) and len(result) > 0:
                    api_response = result[0].get("generated_text", "")
                else:
                    api_response = str(result)
                
                # Log performance metrics
                processing_time = time.time() - start_time
                logger.info(f"Hugging Face API call completed in {processing_time:.2f}s")
                
                return api_response
            except requests.exceptions.Timeout:
                logger.error(f"Hugging Face request timed out after {self.timeout}s (attempt {retry_num+1}/{max_retries+1})")
                self.health_status["healthy"] = False
                self.health_status["error"] = "Timeout"
                
                if retry_num == max_retries:  # Last attempt failed
                    raise Exception("Request timed out - model may be loading or overloaded")
                    
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if hasattr(e, 'response') else "unknown"
                logger.error(f"HTTP error {status_code} (attempt {retry_num+1}/{max_retries+1}): {e}")
                
                # Log response content for debugging
                if response is not None:
                    logger.error(f"Response content: {response.text}")
                
                if retry_num == max_retries:  # Last attempt failed
                    if status_code == 401:
                        raise Exception("Invalid API key for Hugging Face service")
                    elif status_code == 404:
                        raise Exception(f"Model {self.model} not found on Hugging Face service")
                    elif status_code == 429:
                        raise Exception("Rate limit exceeded for Hugging Face service")
                    elif status_code == 500:
                        raise Exception("Hugging Face server internal error")
                    else:
                        raise Exception(f"HTTP error {status_code}: {e}")
                    
            except requests.exceptions.ConnectionError:
                logger.error(f"Hugging Face server connection failed (attempt {retry_num+1}/{max_retries+1})")
                self.health_status["healthy"] = False
                self.health_status["error"] = "Connection Error"
                
                if retry_num == max_retries:  # Last attempt failed
                    raise Exception("Could not connect to Hugging Face server")
                
            except Exception as e:
                logger.error(f"Unexpected error calling Hugging Face (attempt {retry_num+1}/{max_retries+1}): {e}")
                
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
        logger.error(f"All {max_retries+1} Hugging Face API call attempts failed")
        raise Exception("All API call attempts failed")
    
    def _parse_scoring_response(self, response: str) -> Dict[str, Any]:
        """Parse the scoring response from Hugging Face"""
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
            logger.error(f"Failed to parse Hugging Face response: {e}")
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

# Create a global instance (will need API key to be set)
huggingface_service = HuggingFaceService()