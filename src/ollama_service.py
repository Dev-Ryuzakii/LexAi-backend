"""
Ollama service module for AI-powered answer scoring
"""
import requests
import logging
import os
import time
import hashlib
from datetime import datetime

from resilience import retry_call
from scoring import StrictScoringMixin, MAX_SCORE

logger = logging.getLogger(__name__)


class ResponseCache:
    """Simple in-process cache of successful gradings, keyed by the exact inputs"""
    def __init__(self, max_size=1000, ttl=3600):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl  # Time to live in seconds

    def _generate_key(self, student_answer, marking_guide, question):
        combined = f"{student_answer.strip().lower()}|{marking_guide.strip().lower()}|{(question or '').strip().lower()}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def get(self, student_answer, marking_guide, question):
        """Get a copy of the cached response if available and not expired"""
        key = self._generate_key(student_answer, marking_guide, question)
        if key in self.cache:
            timestamp, response = self.cache[key]
            if time.time() - timestamp <= self.ttl:
                logger.info("Cache hit for scoring request")
                return dict(response)
            del self.cache[key]
        return None

    def set(self, student_answer, marking_guide, question, response):
        key = self._generate_key(student_answer, marking_guide, question)
        self.cache[key] = (time.time(), dict(response))

        if len(self.cache) > self.max_size:
            # Remove oldest 20%
            sorted_keys = sorted(self.cache.items(), key=lambda x: x[1][0])
            for k, _ in sorted_keys[:int(self.max_size * 0.2)]:
                del self.cache[k]


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
        self.generation_timeout = float(os.environ.get('OLLAMA_GENERATION_TIMEOUT', '180'))
        self.generation_num_ctx = int(os.environ.get('OLLAMA_GENERATION_NUM_CTX', '8192'))
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

    def _create_scoring_prompt(self, student_answer: str, marking_guide: str, question: str = "") -> str:
        return f"""
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
- Score must be an INTEGER between 0-{MAX_SCORE}
- Confidence must be a number between 0 and 1
- Focus on MEANING and UNDERSTANDING, not exact words
- Consider different ways of expressing the same concept as correct

Respond only with the JSON object, no additional text.
"""

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

        def attempt() -> str:
            start_time = time.time()
            try:
                response = requests.post(self.api_url, json=payload, timeout=self.timeout)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                self.health_status["healthy"] = False
                self.health_status["error"] = type(e).__name__
                raise
            if response.status_code == 404:
                raise RuntimeError(f"Model {self.model} not found on Ollama server")
            response.raise_for_status()
            logger.info(f"Ollama API call completed in {time.time() - start_time:.2f}s")
            return response.json().get("response", "")

        def transient(e: BaseException) -> bool:
            # Network problems, 429 and 5xx are worth retrying; other client errors are not.
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                return e.response.status_code == 429 or e.response.status_code >= 500
            return isinstance(e, requests.exceptions.RequestException)

        return retry_call(attempt, attempts=self.retries + 1, base=1.0, cap=10.0,
                          retry_on=(requests.exceptions.RequestException,), should_retry=transient,
                          label='Ollama call')

    def complete(self, prompt: str, max_tokens: int = 2500, temperature: float = 0.4) -> str:
        """
        Long-form JSON generation (question writing). Separate from grading, which keeps its
        own short, low-temperature settings. Timeouts are not retried: a model that took the
        whole timeout once will not be faster the second time.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
                "num_predict": max_tokens,
                # The default 2048-token context is too small for the prompt plus the questions.
                "num_ctx": self.generation_num_ctx,
            }
        }

        def attempt() -> str:
            start_time = time.time()
            try:
                response = requests.post(self.api_url, json=payload, timeout=self.generation_timeout)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                self.health_status["healthy"] = False
                self.health_status["error"] = type(e).__name__
                raise
            if response.status_code == 404:
                raise RuntimeError(f"Model {self.model} not found on Ollama server")
            response.raise_for_status()
            logger.info(f"Ollama generation call completed in {time.time() - start_time:.2f}s")
            return response.json().get("response", "")

        def transient(e: BaseException) -> bool:
            if isinstance(e, requests.exceptions.Timeout):
                return False
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                return e.response.status_code == 429 or e.response.status_code >= 500
            return isinstance(e, requests.exceptions.RequestException)

        return retry_call(attempt, attempts=2, base=1.0, cap=5.0,
                          retry_on=(requests.exceptions.RequestException,), should_retry=transient,
                          label='Ollama generation call')

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


def fallback_similarity_score(student_answer: str, marking_guide: str) -> int:
    """
    Text-similarity estimate on the 0-5 scale. This is not an AI grade: callers
    must flag results from it for lecturer review.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words='english', lowercase=True)
        tfidf_matrix = vectorizer.fit_transform([student_answer.lower(), marking_guide.lower()])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return max(0, min(MAX_SCORE, int(similarity * MAX_SCORE)))
    except Exception:
        student_words = set(student_answer.lower().split())
        guide_words = set(marking_guide.lower().split())
        if not guide_words:
            return 0
        similarity = len(student_words & guide_words) / len(guide_words)
        return max(0, min(MAX_SCORE, int(similarity * MAX_SCORE)))
