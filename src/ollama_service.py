"""
Ollama service module for AI-powered answer scoring
"""
import requests
import logging
import os
import random
import time
from datetime import datetime
from typing import Dict, Any

from scoring import StrictScoringMixin
from grading_helpers import ResponseCache, create_scoring_prompt, fallback_similarity_score

logger = logging.getLogger(__name__)


class OllamaService(StrictScoringMixin):
    provider_name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2:latest"):
        """
        Args:
            base_url: Ollama server URL
            model: Model to use for inference (llama3.2:latest, llama2, mistral, etc.)
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.api_url = f"{self.base_url}/api/generate"
        self.response_cache = ResponseCache()
        self.available_models = []
        self.health_status = {
            "healthy": False,
            "last_check": None,
            "error": None
        }
        self.retries = 3
        self.timeout = 60
        # Health is checked lazily on first use, so importing this module never blocks on the network.

    def _check_health(self) -> None:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                self.health_status = {"healthy": True, "last_check": datetime.now().isoformat(), "error": None}
                data = response.json()
                self.available_models = [model["name"] for model in data.get("models", [])]
            else:
                self.health_status = {
                    "healthy": False,
                    "last_check": datetime.now().isoformat(),
                    "error": f"Unexpected status code: {response.status_code}"
                }
        except Exception as e:
            self.health_status = {"healthy": False, "last_check": datetime.now().isoformat(), "error": str(e)}

    def check_connection(self) -> bool:
        """Returns whether the service is available (re-checked at most every 30 seconds)"""
        if (not self.health_status["last_check"] or
                (datetime.now() - datetime.fromisoformat(self.health_status["last_check"])).total_seconds() > 30):
            self._check_health()
        return self.health_status["healthy"]

    _create_scoring_prompt = staticmethod(create_scoring_prompt)

    def _generate(self, prompt: str) -> str:
        return self._call_ollama(prompt)

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama with retries and exponential backoff. Raises on final failure."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,  # Low temperature for consistent scoring
                "top_p": 0.9,
                "num_predict": 500,
            }
        }

        last_error = None
        for attempt in range(self.retries + 1):
            start_time = time.time()
            try:
                response = requests.post(self.api_url, json=payload, timeout=self.timeout)
                if response.status_code == 404:
                    # Retrying will not make a missing model appear.
                    raise RuntimeError(f"Model {self.model} not found on Ollama server")
                response.raise_for_status()
                logger.info(f"Ollama API call completed in {time.time() - start_time:.2f}s")
                return response.json().get("response", "")
            except RuntimeError:
                raise
            except requests.exceptions.RequestException as e:
                last_error = e
                logger.error(f"Ollama call failed (attempt {attempt + 1}/{self.retries + 1}): {e}")
                if isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
                    self.health_status["healthy"] = False
                    self.health_status["error"] = type(e).__name__

            if attempt < self.retries:
                delay = 2 ** attempt
                time.sleep(delay + random.uniform(0, delay * 0.5))

        raise RuntimeError(f"All Ollama call attempts failed: {last_error}")

    def get_available_models(self) -> list:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                return [model["name"] for model in response.json().get("models", [])]
            return []
        except requests.exceptions.RequestException:
            return []

    def pull_model(self, model_name: str) -> bool:
        try:
            response = requests.post(f"{self.base_url}/api/pull", json={"name": model_name}, timeout=300)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False


ollama_service = OllamaService(
    base_url=os.environ.get('OLLAMA_HOST', 'http://localhost:11434'),
    model=os.environ.get('OLLAMA_MODEL', 'llama3.2:latest'),
)
