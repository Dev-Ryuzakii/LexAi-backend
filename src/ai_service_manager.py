"""
AI Service Manager for handling multiple AI providers
"""
import logging
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    from ollama_service import ollama_service, fallback_similarity_score
except ImportError as e:
    logger.warning(f"Ollama service not available: {e}")
    ollama_service = None
    fallback_similarity_score = None

try:
    from palm_service import palm_service
except ImportError as e:
    logger.warning(f"PaLM service not available: {e}")
    palm_service = None

try:
    from cohere_service import cohere_service
except ImportError as e:
    logger.warning(f"Cohere service not available: {e}")
    cohere_service = None

try:
    from huggingface_service import huggingface_service
except ImportError as e:
    logger.warning(f"Hugging Face service not available: {e}")
    huggingface_service = None

class AIServiceManager:
    def __init__(self):
        """
        Initialize AI Service Manager with all available services
        """
        self.services = {}
        
        # Only add services that are available
        if ollama_service:
            self.services['ollama'] = ollama_service
        if palm_service:
            self.services['palm'] = palm_service
        if cohere_service:
            self.services['cohere'] = cohere_service
        if huggingface_service:
            self.services['huggingface'] = huggingface_service
            
        # Set default active service
        if self.services:
            self.active_service = next(iter(self.services))
        else:
            self.active_service = None
            
        self.fallback_chain = [s for s in ['ollama', 'palm', 'cohere', 'huggingface'] if s in self.services]
        
    def set_active_service(self, service_name: str) -> bool:
        """
        Set the active AI service to use
        
        Args:
            service_name: Name of the service to activate
            
        Returns:
            Boolean indicating if the service was successfully set
        """
        if service_name in self.services:
            self.active_service = service_name
            logger.info(f"Active AI service set to: {service_name}")
            return True
        else:
            logger.error(f"Service {service_name} not found. Available services: {list(self.services.keys())}")
            return False
    
    def set_api_keys(self, api_keys: Dict[str, str]) -> None:
        """
        Set API keys for the services that require them
        
        Args:
            api_keys: Dictionary with service names as keys and API keys as values
        """
        for service_name, api_key in api_keys.items():
            if service_name in self.services:
                if hasattr(self.services[service_name], 'api_key'):
                    self.services[service_name].api_key = api_key
                    logger.info(f"API key set for {service_name}")
                else:
                    logger.warning(f"Service {service_name} does not support API keys")
            else:
                logger.warning(f"Unknown service {service_name}")
    
    def set_models(self, models: Dict[str, str]) -> None:
        """
        Set models for the services
        
        Args:
            models: Dictionary with service names as keys and model names as values
        """
        for service_name, model in models.items():
            if service_name in self.services:
                if hasattr(self.services[service_name], 'model'):
                    self.services[service_name].model = model
                    logger.info(f"Model set for {service_name}: {model}")
                else:
                    logger.warning(f"Service {service_name} does not support model selection")
            else:
                logger.warning(f"Unknown service {service_name}")
    
    def score_answer(self, student_answer: str, marking_guide: str, question: str = "") -> Dict[str, Any]:
        """
        Score a student answer using the active service or fallback chain
        
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
        
        # Check if any services are available
        if not self.services:
            return {
                "score": 0,
                "confidence": 0.0,
                "feedback": "No AI services available",
                "strengths": [],
                "weaknesses": [],
                "model_used": "none",
                "scoring_method": "unavailable"
            }
        
        # Try the active service first
        service_order = [self.active_service] + [s for s in self.fallback_chain if s != self.active_service]
        
        for service_name in service_order:
            service = self.services.get(service_name)
            if not service:
                continue
                
            try:
                # Check if service is configured (has API key if needed)
                if hasattr(service, 'api_key') and service_name in ['palm', 'cohere', 'huggingface']:
                    if not getattr(service, 'api_key', None):
                        logger.warning(f"Skipping {service_name} - no API key configured")
                        continue
                
                # Check service health
                if service.check_connection():
                    result = service.score_answer(student_answer, marking_guide, question)
                    result["scoring_method"] = service_name
                    logger.info(f"Scored using {service_name}")
                    return result
                else:
                    logger.warning(f"{service_name} service unavailable")
            except Exception as e:
                logger.error(f"Error using {service_name} service: {e}")
                continue
        
        # Ultimate fallback - simple similarity if available
        if fallback_similarity_score:
            score = fallback_similarity_score(student_answer, marking_guide)
            logger.info("Scored using simple similarity fallback")
            return {
                "score": score,
                "confidence": 0.5,
                "feedback": "Scored using simple text similarity (basic fallback)",
                "strengths": [],
                "weaknesses": [],
                "model_used": "basic_similarity",
                "scoring_method": "basic_similarity"
            }
        else:
            # Final fallback - return a default response
            logger.info("No scoring methods available, returning default response")
            return {
                "score": 0,
                "confidence": 0.0,
                "feedback": "No scoring methods available",
                "strengths": [],
                "weaknesses": [],
                "model_used": "none",
                "scoring_method": "unavailable"
            }
    
    def get_service_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the status of all AI services
        
        Returns:
            Dictionary with service statuses
        """
        status = {}
        for name, service in self.services.items():
            try:
                connected = service.check_connection()
                status[name] = {
                    "connected": connected,
                    "healthy": getattr(service.health_status, 'healthy', False) if hasattr(service, 'health_status') else connected,
                    "model": getattr(service, 'model', 'unknown') if hasattr(service, 'model') else 'N/A'
                }
            except Exception as e:
                status[name] = {
                    "connected": False,
                    "healthy": False,
                    "error": str(e),
                    "model": getattr(service, 'model', 'unknown') if hasattr(service, 'model') else 'N/A'
                }
        return status

# Create a global instance
ai_service_manager = AIServiceManager()