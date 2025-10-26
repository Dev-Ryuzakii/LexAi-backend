"""
Google PaLM/Bard service module for AI-powered answer scoring
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

class PalmService:
    def __init__(self, api_key: str = "", model: str = "chat-bison-001"):
        """
        Initialize Google PaLM service with enhanced features
        
        Args:
            api_key: Google PaLM API key
            model: Model to use for inference (chat-bison-001, text-bison-001, etc.)
        """
        self.api_key = api_key
        self.model = model
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta2/models/{model}:generateMessage"
        self.response_cache = ResponseCache()
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
        """Internal health check of PaLM service"""
        try:
            if not self.api_key:
                self.health_status = {
                    "healthy": False,
                    "last_check": datetime.now().isoformat(),
                    "error": "API key not provided"
                }
                return
                
            # Simple check by making a minimal API call
            test_url = f"https://generativelanguage.googleapis.com/v1beta2/models/{self.model}?key={self.api_key}"
            response = requests.get(test_url, timeout=5)
            
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
        Public health check of PaLM service
        
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
        Score a student answer against a marking guide using PaLM with caching
        
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
        scoring_method = "palm"
        model_used = self.model
        
        try:
            # Check PaLM connectivity first
            if self.check_connection():
                # Create a prompt for the AI to score the answer
                prompt = self._create_scoring_prompt(student_answer, marking_guide, question)
                
                for attempt in range(self.retries):
                    try:
                        response = self._call_palm(prompt)
                        result = self._parse_scoring_response(response)
                        
                        # Add metadata
                        result["model_used"] = self.model
                        result["scoring_method"] = "palm"
                        
                        # Cache successful response
                        self.response_cache.set(student_answer, marking_guide, question, result)
                        
                        return result
                    except requests.exceptions.Timeout:
                        logger.warning(f"PaLM timeout on attempt {attempt+1}/{self.retries}")
                        time.sleep(self.backoff_factor * (attempt + 1))
                    except requests.exceptions.RequestException as e:
                        logger.error(f"PaLM request error on attempt {attempt+1}/{self.retries}: {e}")
                        time.sleep(self.backoff_factor * (attempt + 1))
                        
                # If we get here, all attempts failed
                logger.error(f"All {self.retries} attempts to call PaLM failed")
                scoring_method = "fallback_ml"
            else:
                logger.warning("PaLM service unavailable, using fallback")
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
    
    def _create_scoring_prompt(self, student_answer: str, marking_guide: str, question: str = "") -> Dict[str, Any]:
        """Create a prompt for scoring the student answer"""
        prompt_text = f"""
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
        
        return {
            "prompt": {
                "messages": [
                    {
                        "content": prompt_text
                    }
                ]
            }
        }
    
    def _call_palm(self, prompt: Dict[str, Any]) -> str:
        """
        Make API call to PaLM with enhanced error handling and retries
        
        Args:
            prompt: The prompt to send to PaLM
            
        Returns:
            String response from PaLM
            
        Raises:
            Exception: Various exceptions for different failure modes
        """
        url = f"{self.api_url}?key={self.api_key}"
        
        payload = {
            **prompt,
            "temperature": 0.1,  # Low temperature for consistent scoring
            "topP": 0.9,
            "candidateCount": 1
        }
        
        # Implement retry logic with exponential backoff
        max_retries = self.retries
        base_delay = 1  # Start with 1 second delay
        
        for retry_num in range(max_retries + 1):  # +1 for initial attempt
            start_time = time.time()
            response = None  # Initialize response variable
            
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.timeout  # Use instance timeout
                )
                response.raise_for_status()
                
                result = response.json()
                
                if "candidates" in result and len(result["candidates"]) > 0:
                    api_response = result["candidates"][0].get("content", "")
                else:
                    api_response = ""
                
                # Log performance metrics
                processing_time = time.time() - start_time
                logger.info(f"PaLM API call completed in {processing_time:.2f}s")
                
                return api_response
            except requests.exceptions.Timeout:
                logger.error(f"PaLM request timed out after {self.timeout}s (attempt {retry_num+1}/{max_retries+1})")
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
                        raise Exception("Invalid API key for PaLM service")
                    elif status_code == 404:
                        raise Exception(f"Model {self.model} not found on PaLM service")
                    elif status_code == 429:
                        raise Exception("Rate limit exceeded for PaLM service")
                    elif status_code == 500:
                        raise Exception("PaLM server internal error")
                    else:
                        raise Exception(f"HTTP error {status_code}: {e}")
                    
            except requests.exceptions.ConnectionError:
                logger.error(f"PaLM server connection failed (attempt {retry_num+1}/{max_retries+1})")
                self.health_status["healthy"] = False
                self.health_status["error"] = "Connection Error"
                
                if retry_num == max_retries:  # Last attempt failed
                    raise Exception("Could not connect to PaLM server")
                
            except Exception as e:
                logger.error(f"Unexpected error calling PaLM (attempt {retry_num+1}/{max_retries+1}): {e}")
                
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
        logger.error(f"All {max_retries+1} PaLM API call attempts failed")
        raise Exception("All API call attempts failed")
    
    def _parse_scoring_response(self, response: str) -> Dict[str, Any]:
        """Parse the scoring response from PaLM"""
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
            logger.error(f"Failed to parse PaLM response: {e}")
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
palm_service = PalmService()