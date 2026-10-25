"""Cencori-backed grading for LexAI 3.0."""
import logging
import os
import time

import requests

from grading_helpers import ResponseCache, create_scoring_prompt
from scoring import ScoringError, StrictScoringMixin

logger = logging.getLogger(__name__)


class CencoriService(StrictScoringMixin):
    provider_name = 'cencori'
    public_model_name = 'LexAI 3.0'
    _create_scoring_prompt = staticmethod(create_scoring_prompt)

    def __init__(self, api_key: str = '', model: str = 'gpt-6-luna',
                 base_url: str = 'https://api.cencori.com/v1'):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.response_cache = ResponseCache()
        self.timeout = 60

    def check_connection(self) -> bool:
        # Cencori has no documented unauthenticated health endpoint. A configured
        # key means the service can be attempted; the request determines health.
        return bool(self.api_key)

    def _generate(self, prompt: str) -> str:
        return self.generate_text(prompt)

    def generate_text(self, prompt: str, timeout: int | None = None) -> str:
        if not self.api_key:
            raise ScoringError('CENCORI_API_KEY is not configured')

        payload = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': False,
        }
        started = time.monotonic()
        try:
            response = requests.post(
                f'{self.base_url}/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                },
                json=payload,
                timeout=timeout or self.timeout,
            )
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            if not isinstance(content, str):
                raise ValueError('Cencori returned non-text content')
            logger.info('Cencori grading call completed in %.2fs', time.monotonic() - started)
            return content
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            # Never include response bodies or request headers: they may contain
            # student data or credentials.
            logger.warning('Cencori grading call failed: %s', type(exc).__name__)
            raise ScoringError(f'Cencori request failed: {type(exc).__name__}') from exc


cencori_service = CencoriService(
    api_key=os.environ.get('CENCORI_API_KEY', ''),
    model=os.environ.get('CENCORI_MODEL', 'gpt-6-luna'),
    base_url=os.environ.get('CENCORI_BASE_URL', 'https://api.cencori.com/v1'),
)
