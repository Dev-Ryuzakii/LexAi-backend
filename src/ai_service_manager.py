"""
AI Service Manager for handling multiple AI providers.

score_answer() either returns a grade or a result with scoring_method == "unavailable".
Grades that should not be trusted without a human (low confidence, text-similarity
fallback) carry needs_review=True.
"""
import logging
import os
from typing import Any, Dict, List, Tuple

import generation
from generation import GenerationUnavailable
from resilience import CircuitBreaker
from scoring import MAX_SCORE, ScoringError

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


def _env_flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


class AIServiceManager:
    def __init__(self):
        self.services = {}
        if ollama_service:
            self.services['ollama'] = ollama_service
        if palm_service:
            self.services['palm'] = palm_service
        if cohere_service:
            self.services['cohere'] = cohere_service
        if huggingface_service:
            self.services['huggingface'] = huggingface_service

        self.active_service = next(iter(self.services), None)
        self.fallback_chain = [s for s in ['ollama', 'palm', 'cohere', 'huggingface'] if s in self.services]
        self.review_confidence_threshold = float(os.environ.get('REVIEW_CONFIDENCE_THRESHOLD', '0.6'))
        self.allow_similarity_fallback = _env_flag('ALLOW_SIMILARITY_FALLBACK', True)
        # A provider that fails this many times in a row is skipped for breaker_reset seconds.
        self.breaker_threshold = int(os.environ.get('PROVIDER_FAILURE_THRESHOLD', '3'))
        self.breaker_reset = float(os.environ.get('PROVIDER_COOLDOWN_SECONDS', '60'))
        self.breakers: Dict[str, CircuitBreaker] = {}

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
            if service_name != 'ollama' and not getattr(service, 'api_key', None):
                continue
            breaker = self._breaker(service_name)
            if not breaker.allow():
                errors.append(f"{service_name}: skipped (circuit open after repeated failures)")
                continue
            try:
                if not service.check_connection():
                    breaker.record_failure()
                    errors.append(f"{service_name}: unavailable")
                    continue
                result = service.score_answer(student_answer, marking_guide, question)
                breaker.record_success()
            except ScoringError as e:
                breaker.record_failure()
                logger.error(f"{service_name} could not grade: {e}")
                errors.append(f"{service_name}: {e}")
                continue
            except Exception as e:
                breaker.record_failure()
                logger.exception(f"Unexpected error from {service_name}")
                errors.append(f"{service_name}: {e}")
                continue

            result["scoring_method"] = service_name
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

        return self._unavailable("No AI provider could grade this answer" + (f" ({'; '.join(errors)})" if errors else ""))

    def _breaker(self, service_name: str) -> CircuitBreaker:
        return self.breakers.setdefault(service_name, CircuitBreaker(
            service_name, failure_threshold=self.breaker_threshold, reset_timeout=self.breaker_reset))

    def generation_providers(self) -> List[str]:
        """Providers that can write questions (long JSON output): those with complete()."""
        order = ([self.active_service] if self.active_service else []) +             [s for s in self.fallback_chain if s != self.active_service]
        names = []
        for name in order:
            service = self.services.get(name)
            if service is None or not callable(getattr(service, 'complete', None)):
                continue
            if name != 'ollama' and not getattr(service, 'api_key', None):
                continue
            names.append(name)
        return names

    def generate_questions(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate questions for `spec` (see generation.generate). Each model call tries the
        capable providers in order with the same circuit breakers as grading; there is no
        non-AI fallback. Raises GenerationUnavailable / GenerationFailed.
        """
        providers = self.generation_providers()
        if not providers:
            raise GenerationUnavailable('No question-generation provider is configured')
        used: List[Tuple[str, str]] = []

        def call(prompt: str) -> str:
            errors = []
            for name in providers:
                service = self.services[name]
                breaker = self._breaker(name)
                if not breaker.allow():
                    errors.append(f"{name}: skipped (circuit open after repeated failures)")
                    continue
                try:
                    if not service.check_connection():
                        breaker.record_failure()
                        errors.append(f"{name}: unavailable")
                        continue
                    text = service.complete(prompt, max_tokens=generation.MAX_TOKENS,
                                            temperature=generation.TEMPERATURE)
                except Exception as e:
                    breaker.record_failure()
                    logger.exception(f"{name} could not generate questions")
                    errors.append(f"{name}: {e}")
                    continue
                breaker.record_success()
                entry = (name, getattr(service, 'model', 'unknown'))
                if entry not in used:
                    used.append(entry)
                return text
            raise GenerationUnavailable('; '.join(errors) or 'No provider could generate questions')

        result = generation.generate(spec, call)
        result['provider'] = ','.join(name for name, _ in used)
        result['model_used'] = ','.join(model for _, model in used)
        return result

    def get_service_status(self) -> Dict[str, Dict[str, Any]]:
        status = {}
        for name, service in self.services.items():
            try:
                connected = service.check_connection()
                health = getattr(service, 'health_status', None)
                healthy = health.get('healthy', connected) if isinstance(health, dict) else getattr(health, 'healthy', connected)
                breaker = self.breakers.get(name)
                status[name] = {"connected": connected, "healthy": healthy, "model": getattr(service, 'model', 'N/A'),
                                "circuit": breaker.state if breaker else 'closed'}
            except Exception as e:
                status[name] = {"connected": False, "healthy": False, "error": str(e), "model": getattr(service, 'model', 'N/A')}
        return status


ai_service_manager = AIServiceManager()
