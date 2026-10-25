"""
AI Service Manager for handling multiple AI providers.

score_answer() either returns a grade or a result with scoring_method == "unavailable".
Grades that should not be trusted without a human (low confidence, text-similarity
fallback) carry needs_review=True.
"""
import logging
import os
from typing import Dict, Any

from scoring import MAX_SCORE, ScoringError

logger = logging.getLogger(__name__)

from grading_helpers import fallback_similarity_score

# Try to import optional dependencies
from cencori_service import cencori_service

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


def _env_flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


class AIServiceManager:
    def __init__(self):
        self.services = {}
        self.services['cencori'] = cencori_service
        if palm_service:
            self.services['palm'] = palm_service
        if cohere_service:
            self.services['cohere'] = cohere_service
        if huggingface_service:
            self.services['huggingface'] = huggingface_service

        self.active_service = next(iter(self.services), None)
        self.fallback_chain = [s for s in ['cencori', 'palm', 'cohere', 'huggingface'] if s in self.services]
        self.review_confidence_threshold = float(os.environ.get('REVIEW_CONFIDENCE_THRESHOLD', '0.6'))
        self.allow_similarity_fallback = _env_flag('ALLOW_SIMILARITY_FALLBACK', True)

    def set_active_service(self, service_name: str) -> bool:
        if service_name in self.services:
            self.active_service = service_name
            logger.info(f"Active AI service set to: {service_name}")
            return True
        logger.error(f"Service {service_name} not found. Available services: {list(self.services.keys())}")
        return False

    def set_api_keys(self, api_keys: Dict[str, str]) -> None:
        for service_name, api_key in api_keys.items():
            service = self.services.get(service_name)
            if service is not None and hasattr(service, 'api_key'):
                service.api_key = api_key
                logger.info(f"API key set for {service_name}")
            else:
                logger.warning(f"Cannot set API key for {service_name}")

    def set_models(self, models: Dict[str, str]) -> None:
        for service_name, model in models.items():
            service = self.services.get(service_name)
            if service is not None and hasattr(service, 'model'):
                service.model = model
                logger.info(f"Model set for {service_name}: {model}")
            else:
                logger.warning(f"Cannot set model for {service_name}")

    @staticmethod
    def _unavailable(reason: str) -> Dict[str, Any]:
        return {
            "score": None,
            "confidence": 0.0,
            "feedback": reason,
            "strengths": [],
            "weaknesses": [],
            "model_used": "none",
            "scoring_method": "unavailable",
            "error": reason,
        }

    def score_answer(self, student_answer: str, marking_guide: str, question: str = "") -> Dict[str, Any]:
        if not student_answer or not marking_guide:
            return self._unavailable("Missing student answer or marking guide")

        service_order = []
        if self.active_service:
            service_order.append(self.active_service)
        service_order += [s for s in self.fallback_chain if s != self.active_service]

        errors = []
        for service_name in service_order:
            service = self.services[service_name]
            if not getattr(service, 'api_key', None):
                continue
            try:
                if not service.check_connection():
                    errors.append(f"{service_name}: unavailable")
                    continue
                result = service.score_answer(student_answer, marking_guide, question)
            except ScoringError as e:
                logger.error(f"{service_name} could not grade: {e}")
                errors.append(f"{service_name}: {e}")
                continue
            except Exception as e:
                logger.exception(f"Unexpected error from {service_name}")
                errors.append(f"{service_name}: {e}")
                continue

            if service_name == 'cencori':
                result['model_used'] = service.public_model_name
                result['scoring_method'] = 'lexai'
            else:
                result['scoring_method'] = service_name
            result["max_score"] = MAX_SCORE
            result["needs_review"] = result.get("confidence", 0.0) < self.review_confidence_threshold
            return result

        if self.allow_similarity_fallback and fallback_similarity_score:
            score = fallback_similarity_score(student_answer, marking_guide)
            logger.warning("No AI provider could grade; using text-similarity estimate flagged for review")
            return {
                "score": score,
                "confidence": 0.3,
                "feedback": "Estimated with text similarity because no AI provider was available. A lecturer should review this score.",
                "strengths": [],
                "weaknesses": [],
                "model_used": "basic_similarity",
                "scoring_method": "basic_similarity",
                "max_score": MAX_SCORE,
                "needs_review": True,
                "cached": False,
                "provider_errors": errors,
            }

        if errors:
            logger.warning('AI grading unavailable: %s', '; '.join(errors))
        return self._unavailable("No AI provider could grade this answer")

    def get_service_status(self) -> Dict[str, Dict[str, Any]]:
        status = {}
        for name, service in self.services.items():
            try:
                connected = service.check_connection()
                health = getattr(service, 'health_status', None)
                healthy = health.get('healthy', connected) if isinstance(health, dict) else getattr(health, 'healthy', connected)
                public_name = 'lexai' if name == 'cencori' else name
                public_model = getattr(service, 'public_model_name', getattr(service, 'model', 'N/A'))
                status[public_name] = {"connected": connected, "healthy": healthy, "model": public_model}
            except Exception as e:
                public_name = 'lexai' if name == 'cencori' else name
                public_model = getattr(service, 'public_model_name', getattr(service, 'model', 'N/A'))
                status[public_name] = {"connected": False, "healthy": False, "model": public_model}
        return status


ai_service_manager = AIServiceManager()
