"""Cencori request contract and the public LexAI model label."""
import requests
import pytest

from ai_service_manager import AIServiceManager
from cencori_service import CencoriService
from scoring import ScoringError


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {'choices': [{'message': {'content': '{"score": 4, "confidence": 0.9}'}}]}


def test_cencori_grading_uses_luna_and_secret_server_side(monkeypatch):
    service = CencoriService(api_key='test-secret')
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(requests, 'post', fake_post)
    result = service.score_answer('Student answer', 'Marking guide', 'Question')

    assert result['score'] == 4
    assert result['model_used'] == 'gpt-6-luna'  # private service result
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == 'https://api.cencori.com/v1/chat/completions'
    assert kwargs['headers']['Authorization'] == 'Bearer test-secret'
    assert kwargs['json']['model'] == 'gpt-6-luna'
    assert 'Student answer' in kwargs['json']['messages'][0]['content']


def test_cencori_missing_key_does_not_call_network(monkeypatch):
    service = CencoriService(api_key='')
    monkeypatch.setattr(requests, 'post', lambda *a, **k: pytest.fail('network called'))
    assert service.check_connection() is False
    with pytest.raises(ScoringError):
        service.score_answer('answer', 'guide')


def test_manager_exposes_lexai_name_not_provider_model(monkeypatch):
    service = CencoriService(api_key='test-secret')
    monkeypatch.setattr(service, '_generate', lambda prompt: '{"score": 5, "confidence": 0.9}')
    manager = AIServiceManager()
    manager.services = {'cencori': service}
    manager.active_service = 'cencori'
    manager.fallback_chain = ['cencori']

    result = manager.score_answer('answer', 'guide')
    assert result['model_used'] == 'LexAI 3.0'
    assert result['scoring_method'] == 'lexai'
    assert manager.get_service_status()['lexai']['model'] == 'LexAI 3.0'
