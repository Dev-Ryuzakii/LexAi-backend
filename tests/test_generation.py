import json
import uuid

import pytest

import generation
from ai_service_manager import ai_service_manager
from database import ApiUsage, SessionLocal
from generation import (BLANK, GenerationParseError, InvalidQuestion, parse_generation_response, plan_slots,
                        validate_question)

URL = '/api/v1/generate-questions'


def mcq(text='Which organelle is the site of photosynthesis in plant cells?', options=None, answer='Chloroplast',
        topic='Photosynthesis', **extra):
    return {
        'type': 'MCQ', 'question_text': text,
        'options': options if options is not None else ['Chloroplast', 'Nucleus', 'Cell wall', 'Vacuole'],
        'correct_answer': answer, 'accepted_answers': [], 'marking_guide': 'Chloroplasts hold chlorophyll.',
        'explanation': 'Photosynthesis takes place in chloroplasts.', 'difficulty': 'easy', 'topic': topic,
        'learning_objective': 'Identify the site of photosynthesis.', 'common_mistakes': ['Choosing the nucleus'],
        'suggested_points': 1, **extra,
    }


def fill(text='Green plants make glucose by a process called ___.', answer='photosynthesis', **extra):
    return {
        'type': 'FILL_BLANK', 'question_text': text, 'options': [], 'correct_answer': answer,
        'accepted_answers': ['Photosynthesis', 'photo-synthesis'], 'marking_guide': '', 'explanation': 'Plants make food by photosynthesis.',
        'difficulty': 'medium', 'topic': 'Photosynthesis', 'learning_objective': 'Name the process.',
        'common_mistakes': [], 'suggested_points': 1, **extra,
    }


def theory(text='Explain how a leaf is adapted for photosynthesis.', guide=None, **extra):
    return {
        'type': 'THEORY', 'question_text': text, 'options': [], 'correct_answer': '', 'accepted_answers': [],
        'marking_guide': guide if guide is not None else
        '- Large surface area to absorb light (2 marks)\n- Thin for short diffusion distance (2 marks)\n- Stomata for gas exchange (2 marks)',
        'explanation': 'Leaves are broad, thin and have stomata.', 'difficulty': 'hard', 'topic': 'Plant cells',
        'learning_objective': 'Explain leaf adaptations.', 'common_mistakes': ['Ignoring stomata'],
        'suggested_points': 8, **extra,
    }


def reply(*questions):
    return json.dumps({'questions': list(questions)})


SPEC = {'subject': 'Basic Science', 'topics': ['Photosynthesis', 'Plant cells'], 'level': 'JSS 2', 'count': 3,
        'question_types': ['MCQ', 'FILL_BLANK', 'THEORY'], 'difficulty': 'mixed', 'instructions': '',
        'source_material': '', 'avoid_questions': []}


class FakeProvider:
    model = 'fake-model'

    def __init__(self, replies=None, connected=True):
        self.replies = list(replies or [])
        self.prompts = []
        self.connected = connected

    def check_connection(self):
        return self.connected

    def complete(self, prompt, max_tokens=2500, temperature=0.4):
        self.prompts.append(prompt)
        if not self.replies:
            return reply()
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(ai_service_manager, 'services', {'ollama': fake})
    monkeypatch.setattr(ai_service_manager, 'fallback_chain', ['ollama'])
    monkeypatch.setattr(ai_service_manager, 'active_service', 'ollama')
    monkeypatch.setattr(ai_service_manager, 'breakers', {})
    return fake


def body(**overrides):
    return {'subject': 'Basic Science', 'topics': ['Photosynthesis', 'Plant cells'], 'level': 'JSS 2', 'count': 3,
            'question_types': ['MCQ', 'FILL_BLANK', 'THEORY'], **overrides}


# --- Validation of single questions ---------------------------------------------------------

def test_valid_mcq_passes_through():
    q = validate_question(mcq(), SPEC)
    assert q['options'] == ['Chloroplast', 'Nucleus', 'Cell wall', 'Vacuole']
    assert q['correct_answer'] == 'Chloroplast' and q['accepted_answers'] == []
    assert q['marking_guide'] and q['suggested_points'] == 1


@pytest.mark.parametrize('raw, reason', [
    (mcq(answer='Mitochondrion'), 'not one of the options'),
    (mcq(options=['Chloroplast', 'chloroplast', 'Cell wall', 'Vacuole']), 'not distinct'),
    (mcq(options=['Chloroplast', 'Nucleus', 'Cell wall']), 'exactly 4 options'),
    (mcq(options=['Chloroplast', 'Nucleus', 'Cell wall', 'Vacuole', 'Ribosome']), 'exactly 4 options'),
    (mcq(options=['Chloroplast', 'Nucleus', '', 'Vacuole', ]), 'exactly 4 options'),
    (mcq(options=['Chloroplast', 'Nucleus', 'Cell wall', 'None of the above']), 'all/none of the above'),
    (mcq(text='The chloroplast is where photosynthesis happens. Which organelle is that?'), 'gives away'),
    (mcq(explanation=''), 'explanation is missing'),
    (mcq(type='TRUE_FALSE'), 'unknown question type'),
    (mcq(topic='Genetics'), 'not one of the requested topics'),
    ('not an object', 'not an object'),
])
def test_invalid_mcq_is_rejected(raw, reason):
    with pytest.raises(InvalidQuestion, match=reason):
        validate_question(raw, SPEC)


def test_mcq_letter_labels_and_letter_answer_are_resolved():
    q = validate_question(mcq(options=['A. Chloroplast', 'B. Nucleus', 'C. Cell wall', 'D. Vacuole'], answer='A'), SPEC)
    assert q['options'][0] == 'Chloroplast' and q['correct_answer'] == 'Chloroplast'


def test_fill_blank_marker_is_normalized():
    q = validate_question(fill(), SPEC)
    assert q['question_text'] == f'Green plants make glucose by a process called {BLANK}.'
    assert q['accepted_answers'] == ['photosynthesis', 'photo-synthesis']  # primary first, case-duplicate removed
    assert q['options'] == [] and q['marking_guide']  # falls back to the explanation

    q = validate_question(fill(text='Green plants make glucose by a process called __________.'), SPEC)
    assert q['question_text'].count(BLANK) == 1 and '_____' not in q['question_text']


@pytest.mark.parametrize('raw, reason', [
    (fill(text='Green plants make glucose by a process called photosynthesis.'), 'exactly one blank'),
    (fill(text='Plants use ____ to make ____ in the leaves.'), 'exactly one blank'),
    (fill(text='Photosynthesis is the process called ____ in plants.'), 'gives away'),
    (fill(answer=''), 'correct_answer is missing'),
    (fill(answer='the process by which green plants make their own food'), 'too long'),
])
def test_invalid_fill_blank_is_rejected(raw, reason):
    with pytest.raises(InvalidQuestion, match=reason):
        validate_question(raw, SPEC)


def test_theory_requires_marking_guide():
    q = validate_question(theory(), SPEC)
    assert q['correct_answer'] == '' and q['options'] == [] and q['accepted_answers'] == []
    assert q['suggested_points'] == 6  # follows the marking guide's mark split
    assert len(q['marking_guide'].splitlines()) == 3
    with pytest.raises(InvalidQuestion, match='marking_guide is missing'):
        validate_question(theory(guide=''), SPEC)
    with pytest.raises(InvalidQuestion, match='at least two'):
        validate_question(theory(guide='Mention the leaf'), SPEC)


def test_type_not_requested_is_rejected():
    with pytest.raises(InvalidQuestion, match='not requested'):
        validate_question(theory(), {**SPEC, 'question_types': ['MCQ']})


def test_fixed_difficulty_and_points_are_clamped():
    q = validate_question(mcq(suggested_points=9, difficulty='impossible'), {**SPEC, 'difficulty': 'hard'})
    assert q['difficulty'] == 'hard' and q['suggested_points'] == 2


@pytest.mark.parametrize('text', ['', 'Sure! Here are your questions.', '{"questions": "none"}', '{"foo": 1'])
def test_unusable_replies_raise(text):
    with pytest.raises(GenerationParseError):
        parse_generation_response(text)


def test_reply_with_surrounding_text_parses():
    assert len(parse_generation_response('Here you go:\n' + reply(mcq()) + '\nGood luck!')) == 1


def test_plan_balances_types_and_topics():
    slots = plan_slots({'MCQ': 4, 'THEORY': 2}, ['A', 'B', 'C'], {}, 'mixed')
    assert [s['type'] for s in slots[:3]] == ['MCQ', 'THEORY', 'MCQ']
    assert sorted(s['topic'] for s in slots) == ['A', 'A', 'B', 'B', 'C', 'C']
    assert {s['difficulty'] for s in slots} == {'easy', 'medium', 'hard'}


# --- Endpoint ---------------------------------------------------------------------------------

def test_generates_valid_batch(client, alice, provider):
    provider.replies = [reply(mcq(), fill(), theory())]
    res = client.post(URL, headers=alice, json=body(level='JSS 2', instructions='Use Nigerian examples',
                                                    source_material='Plants make food in chloroplasts.'))
    assert res.status_code == 200, res.get_json()
    out = res.get_json()
    assert out['success'] is True and out['provider'] == 'ollama' and out['model_used'] == 'fake-model'
    assert out['request_id'] and out['timestamp'] and isinstance(out['processing_time'], float)
    data = out['data']
    assert data['requested'] == 3 and data['generated'] == 3 and data['warnings'] == []
    assert [q['type'] for q in data['questions']] == ['MCQ', 'FILL_BLANK', 'THEORY']
    keys = {'type', 'question_text', 'options', 'correct_answer', 'accepted_answers', 'marking_guide', 'explanation',
            'difficulty', 'topic', 'learning_objective', 'common_mistakes', 'suggested_points'}
    assert all(set(q) == keys for q in data['questions'])
    prompt = provider.prompts[0]
    assert 'JSS 2' in prompt and 'Use Nigerian examples' in prompt and 'Plants make food in chloroplasts.' in prompt
    assert len(provider.prompts) == 1


def test_invalid_questions_are_dropped_and_retried(client, alice, provider):
    provider.replies = [
        reply(mcq(answer='Mitochondrion'), mcq(text='Which gas do plants absorb for photosynthesis?',
                                               options=['Carbon dioxide', 'Oxygen', 'Nitrogen', 'Hydrogen'],
                                               answer='Carbon dioxide')),
        reply(mcq(text='Which pigment makes leaves green?', options=['Chlorophyll', 'Haemoglobin', 'Melanin', 'Keratin'],
                  answer='Chlorophyll')),
    ]
    res = client.post(URL, headers=alice, json=body(count=2, question_types=['MCQ']))
    data = res.get_json()['data']
    assert res.status_code == 200 and data['generated'] == 2 and data['warnings'] == []
    assert len(provider.prompts) == 2
    # The retry prompt tells the model what was already generated.
    assert 'Which gas do plants absorb for photosynthesis?' in provider.prompts[1]


def test_batches_are_at_most_five(client, alice, provider):
    def batch(start, n):
        return reply(*[mcq(text=f'What does the code {uuid.uuid4().hex} stand for in lesson {i}?',
                           options=[f'Answer {i}', f'Wrong {i}a', f'Wrong {i}b', f'Wrong {i}c'], answer=f'Answer {i}')
                       for i in range(start, start + n)])
    provider.replies = [batch(0, 5), batch(5, 5), batch(10, 2)]
    res = client.post(URL, headers=alice, json=body(count=12, question_types=['MCQ']))
    assert res.get_json()['data']['generated'] == 12
    assert len(provider.prompts) == 3
    assert 'Write exactly 5 questions' in provider.prompts[0] and 'Write exactly 2 questions' in provider.prompts[2]


def test_duplicates_of_avoid_questions_are_dropped(client, alice, provider):
    existing = 'Which organelle is the site of photosynthesis in plant cells?'
    provider.replies = [reply(mcq(), mcq(text='which organelle is the site of photosynthesis in plant cells'))] + [reply()] * 2
    res = client.post(URL, headers=alice, json=body(count=1, question_types=['MCQ'], avoid_questions=[existing]))
    assert res.status_code == 422
    assert 'duplicate' in ' '.join(res.get_json()['error']['details']['reasons'])
    assert existing in provider.prompts[0]


def test_duplicates_within_a_request_are_dropped(client, alice, provider):
    provider.replies = [reply(mcq(), mcq())] + [reply()] * 2
    res = client.post(URL, headers=alice, json=body(count=2, question_types=['MCQ']))
    data = res.get_json()['data']
    assert res.status_code == 200 and data['generated'] == 1
    assert data['warnings'] and 'Only 1 of 2' in data['warnings'][-1]
    assert len(provider.prompts) == 3  # first round plus two bounded retries


def test_unparseable_output_then_nothing_valid_is_422(client, alice, provider):
    provider.replies = ['not json', reply(mcq(answer='Ribosome')), reply()]
    res = client.post(URL, headers=alice, json=body(count=1, question_types=['MCQ']))
    assert res.status_code == 422
    err = res.get_json()['error']
    assert err['code'] == 'GEN_002'
    assert any('not one of the options' in r for r in err['details']['reasons'])


def test_no_provider_is_503(client, alice, provider):
    provider.connected = False
    res = client.post(URL, headers=alice, json=body())
    assert res.status_code == 503
    assert res.get_json()['error']['code'] == 'GEN_001'
    assert res.get_json()['error']['message'] == 'Question generation is unavailable right now'
    assert res.headers.get('Retry-After')


def test_providers_without_complete_are_not_used(client, alice, monkeypatch):
    class GradingOnly:
        model = 'flan'
        api_key = 'k'

        def check_connection(self):
            return True

    monkeypatch.setattr(ai_service_manager, 'services', {'huggingface': GradingOnly()})
    monkeypatch.setattr(ai_service_manager, 'fallback_chain', ['huggingface'])
    monkeypatch.setattr(ai_service_manager, 'active_service', 'huggingface')
    res = client.post(URL, headers=alice, json=body())
    assert res.status_code == 503 and res.get_json()['error']['code'] == 'GEN_001'


def test_falls_back_to_next_provider(client, alice, monkeypatch):
    down = FakeProvider(replies=[RuntimeError('boom')])
    up = FakeProvider(replies=[reply(mcq())])
    up.api_key = 'k'
    monkeypatch.setattr(ai_service_manager, 'services', {'ollama': down, 'cohere': up})
    monkeypatch.setattr(ai_service_manager, 'fallback_chain', ['ollama', 'cohere'])
    monkeypatch.setattr(ai_service_manager, 'active_service', 'ollama')
    monkeypatch.setattr(ai_service_manager, 'breakers', {})
    res = client.post(URL, headers=alice, json=body(count=1, question_types=['MCQ']))
    assert res.status_code == 200 and res.get_json()['provider'] == 'cohere'


def test_partial_result_when_provider_goes_down(client, alice, provider):
    provider.replies = [reply(mcq())]
    provider_down = iter([True, False, False])
    provider.check_connection = lambda: next(provider_down, False)
    res = client.post(URL, headers=alice, json=body(count=6, question_types=['MCQ']))
    data = res.get_json()['data']
    assert res.status_code == 200 and data['generated'] == 1 and data['requested'] == 6
    assert any('unavailable' in w for w in data['warnings'])


def test_time_budget_stops_new_calls(client, alice, provider, monkeypatch):
    monkeypatch.setattr(generation, 'TIME_BUDGET_SECONDS', -1)
    res = client.post(URL, headers=alice, json=body())
    assert res.status_code == 503 and provider.prompts == []


@pytest.mark.parametrize('payload, field', [
    (body(subject=''), 'subject'),
    (body(subject='x' * 201), 'subject'),
    (body(topics=[]), 'topics'),
    (body(topics=['t'] * 11), 'topics'),
    (body(topics=['ok', '']), 'topics[1]'),
    (body(topics=['x' * 201]), 'topics[0]'),
    (body(count=0), 'count'),
    (body(count=31), 'count'),
    (body(count=2.5), 'count'),
    (body(question_types=[]), 'question_types'),
    (body(question_types=['ESSAY']), 'question_types'),
    (body(difficulty='brutal'), 'difficulty'),
    (body(level='x' * 101), 'level'),
    (body(instructions='x' * 2001), 'instructions'),
    (body(source_material='x' * 20001), 'source_material'),
    (body(avoid_questions=['q'] * 101), 'avoid_questions'),
    (body(avoid_questions=['x' * 1001]), 'avoid_questions[0]'),
    ({'topics': ['a'], 'count': 1, 'question_types': ['MCQ']}, 'subject'),
])
def test_validation_errors(client, alice, provider, payload, field):
    res = client.post(URL, headers=alice, json=payload)
    assert res.status_code == 400, res.get_json()
    fields = [e['field'] for e in res.get_json()['error']['details']['validation_errors']]
    assert field in fields
    assert provider.prompts == []


def test_auth_required(client, provider):
    assert client.post(URL, json=body()).status_code == 401
    assert client.post(URL, headers={'X-API-Key': 'nope'}, json=body()).status_code == 401


def test_api_key_auth_and_usage_units(client, alice, provider):
    key = client.post('/api/v1/api-keys', headers=alice, json={'key_name': 'lexlearn'}).get_json()['api_key']['api_key']
    provider.replies = [reply(mcq(), fill(), theory())]
    res = client.post(URL, headers={'X-API-Key': key}, json=body())
    assert res.status_code == 200 and res.get_json()['data']['generated'] == 3
    db = SessionLocal()
    try:
        usage = db.query(ApiUsage).filter_by(endpoint=URL).one()
        assert usage.units == 3
    finally:
        db.close()


def test_route_is_listed(client):
    assert client.get('/').get_json()['endpoints']['generate_questions'] == URL
    spec = client.get('/api/v1/openapi.json').get_json()
    op = spec['paths']['/generate-questions']['post']
    assert op['requestBody']['content']['application/json']['schema']['required'] == \
        ['subject', 'topics', 'count', 'question_types']
