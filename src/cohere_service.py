"""
Cohere AI Service for the AI-CBT Platform
"""
import cohere
import os
import logging

from ollama_service import ResponseCache, OllamaService
from scoring import StrictScoringMixin

logger = logging.getLogger(__name__)


class CohereService(StrictScoringMixin):
    provider_name = "cohere"

    def __init__(self, api_key: str = "", model: str = "command"):
        self.api_key = api_key
        self.model = model
        self.client = None
        self.response_cache = ResponseCache()
        self.health_status = type('obj', (object,), {'healthy': False})()

    def check_connection(self) -> bool:
        """Check if Cohere service is available"""
        try:
            if not self.api_key:
                self.health_status.healthy = False
                return False

            self.client = cohere.Client(self.api_key)
            self.client.tokenize(text="test")
            self.health_status.healthy = True
            return True
        except Exception as e:
            logger.error(f"Cohere service connection failed: {e}")
            self.health_status.healthy = False
            return False

    # Same prompt and 0-5 scale as Ollama, so scores from every provider are comparable.
    _create_scoring_prompt = OllamaService._create_scoring_prompt

    def _generate(self, prompt: str) -> str:
        if not self.client:
            raise RuntimeError("Cohere client is not connected")
        response = self.client.generate(model=self.model, prompt=prompt, max_tokens=500, temperature=0.1)
        return response.generations[0].text


cohere_service = CohereService(
    api_key=os.environ.get("COHERE_API_KEY", ""),
    model=os.environ.get("COHERE_MODEL", "command"),
)
