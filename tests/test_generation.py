import json

import pytest

import api_service
from question_generation import GenerationError, cencori_service, generate_questions


SPEC = {
    'subject': 'Science', 'topics': ['Planets'], 'count': 1,
    'question_types': ['MCQ'], 'difficulty': 'easy', 'level': '',
    'instructions': '', 'source_material': '', 'avoid_questions': [],
}


def test_generation_route_accepts_cbt_contract(client, alice, monkeypatch):
    captured = []
    monkeypatch.setattr(api_service, 'generate_questions', lambda spec: captured.append(spec) or {
        'questions': [{'type': 'MCQ', 'question_text': 'Which is the Red Planet?'}], 'warnings': [],
    })
    response = client.post('/api/v1/generate-questions', headers=alice, json=SPEC)
    assert response.status_code == 200
    assert response.get_json()['model_used'] == 'LexAI 3.0'
    assert captured[0]['question_types'] == ['MCQ']


@pytest.mark.parametrize('bad', [
    {**SPEC, 'count': 0}, {**SPEC, 'question_types': ['UNKNOWN']},
    {**SPEC, 'difficulty': []}, {**SPEC, 'topics': []},
])
def test_generation_rejects_invalid_requests(client, alice, bad):
    response = client.post('/api/v1/generate-questions', headers=alice, json=bad)
    assert response.status_code == 400


def test_generation_validates_model_output(monkeypatch):
    monkeypatch.setattr(cencori_service, 'api_key', 'test-key')
    good = {'questions': [{
        'type': 'MCQ', 'question_text': 'Which is the Red Planet?',
        'options': ['Mars', 'Jupiter', 'Venus'], 'correct_answer': 'Mars',
        'marking_guide': 'Mars is the Red Planet.', 'suggested_points': 2,
    }]}
    monkeypatch.setattr(cencori_service, 'generate_text', lambda *a, **k: json.dumps(good))
    result = generate_questions(SPEC)
    assert result['questions'][0]['correct_answer'] == 'Mars'

    bad = {'questions': [{**good['questions'][0], 'correct_answer': 'Neptune'}]}
    monkeypatch.setattr(cencori_service, 'generate_text', lambda *a, **k: json.dumps(bad))
    with pytest.raises(GenerationError) as error:
        generate_questions(SPEC)
    assert error.value.status == 422
