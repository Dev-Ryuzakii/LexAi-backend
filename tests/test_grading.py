import pytest

import ai_service_manager as manager_module
from ai_service_manager import AIServiceManager
from database import Response, SessionLocal
from ollama_service import OllamaService
from scoring import ScoringError, ScoringParseError, parse_scoring_response


def setup_exam(client, headers):
    qid = client.post('/api/v1/questions', headers=headers,
                      json={'question_text': 'What is X?', 'marking_guide': 'X is Y'}).get_json()['question_id']
    q2 = client.post('/api/v1/questions', headers=headers,
                     json={'question_text': 'What is Z?', 'marking_guide': 'Z is W'}).get_json()['question_id']
    sid = client.post('/api/v1/students', headers=headers,
                      json={'name': 'Ada', 'matric_number': 'M001'}).get_json()['student_id']
    return sid, qid, q2


def submit(client, headers, sid, qid, answer='an answer'):
    return client.post('/api/v1/submit-response', headers=headers,
                       json={'student_id': sid, 'question_id': qid, 'answer': answer})


def student_score(client, headers, sid):
    return client.get(f'/api/v1/students/{sid}', headers=headers).get_json()['student']['score']


# --- Parser ------------------------------------------------------------------------------

def test_provider_error_text_is_not_a_grade():
    with pytest.raises(ScoringParseError):
        parse_scoring_response('Provider error 503: temporarily unavailable')


@pytest.mark.parametrize('reply', [
    '{"score": 7}', '{"score": -1}', '{"score": 4.5}', '{"score": "4"}', '{"score": true}',
    '{"feedback": "great"}', '{"score": 4', '', 'The score is 3',
])
def test_invalid_replies_raise(reply):
    with pytest.raises(ScoringParseError):
        parse_scoring_response(reply)


def test_valid_reply_parses():
    result = parse_scoring_response('Here you go: {"score": 4, "confidence": 85, "feedback": "Good", "strengths": "clear"}')
    assert result['score'] == 4
    assert result['confidence'] == 0.85
    assert result['strengths'] == ['clear']


def test_provider_retries_bad_output_then_gives_up(monkeypatch):
    service = OllamaService()
    replies = iter(['garbage', 'still garbage'])
    monkeypatch.setattr(service, '_generate', lambda prompt: next(replies))
    with pytest.raises(ScoringError):
        service.score_answer('answer', 'guide')

    replies = iter(['garbage', '{"score": 3, "confidence": 0.8}'])
    monkeypatch.setattr(service, '_generate', lambda prompt: next(replies))
    assert service.score_answer('answer', 'guide')['score'] == 3


class FailingProvider:
    model = 'fake'

    def check_connection(self):
        return True

    def score_answer(self, *args):
        raise ScoringError('model returned junk')


def test_manager_flags_similarity_fallback_for_review(monkeypatch):
    monkeypatch.setattr(manager_module, 'palm_service', None)
    manager = AIServiceManager()
    manager.services = {'ollama': FailingProvider()}
    manager.fallback_chain = ['ollama']
    manager.active_service = 'ollama'

    result = manager.score_answer('X is Y', 'X is Y')
    assert result['scoring_method'] == 'basic_similarity'
    assert result['needs_review'] is True

    manager.allow_similarity_fallback = False
    assert manager.score_answer('X is Y', 'X is Y')['scoring_method'] == 'unavailable'


# --- Submissions -------------------------------------------------------------------------

def test_submit_returns_201_and_total(client, alice, grader):
    sid, qid, _ = setup_exam(client, alice)
    res = submit(client, alice, sid, qid)
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body['scoring']['score'] == 4
    assert body['student_total_score'] == 4
    assert body['grading_status'] == 'graded'


def test_resubmission_is_rejected_and_total_does_not_inflate(client, alice, grader):
    sid, qid, q2 = setup_exam(client, alice)
    submit(client, alice, sid, qid)
    again = submit(client, alice, sid, qid)
    assert again.status_code == 409
    assert grader.calls == 1  # duplicate rejected before calling the AI
    grader.result = grader.grade(3)
    submit(client, alice, sid, q2)
    assert student_score(client, alice, sid) == 7

    db = SessionLocal()
    assert db.query(Response).filter_by(student_id=sid, question_id=qid).count() == 1
    db.close()


def test_scoring_failure_stores_nothing(client, alice, grader):
    sid, qid, _ = setup_exam(client, alice)
    grader.result = grader.unavailable()
    res = submit(client, alice, sid, qid)
    assert res.status_code == 503
    assert res.get_json()['error']['code'] == 'SCORE_001'
    assert student_score(client, alice, sid) == 0
    assert client.get('/api/v1/responses', headers=alice).get_json()['total_count'] == 0

    # Nothing was stored, so a retry succeeds.
    grader.result = grader.grade(5)
    assert submit(client, alice, sid, qid).status_code == 201


def test_score_endpoint_reports_unavailable_as_error(client, alice, grader):
    grader.result = grader.unavailable()
    res = client.post('/api/v1/score', headers=alice, json={'student_answer': 'a', 'marking_guide': 'b'})
    assert res.status_code == 503


def test_review_grades_do_not_count_until_a_lecturer_confirms(client, alice, grader):
    sid, qid, _ = setup_exam(client, alice)
    grader.result = grader.grade(2, confidence=0.3, method='basic_similarity', needs_review=True)
    res = submit(client, alice, sid, qid).get_json()
    assert res['grading_status'] == 'needs_review'
    assert res['student_total_score'] == 0

    put = client.put(f"/api/v1/responses/{res['response_id']}", headers=alice, json={'score': 3})
    assert put.status_code == 200
    assert student_score(client, alice, sid) == 3


def test_updating_and_deleting_responses_recalculates_total(client, alice, grader):
    sid, qid, q2 = setup_exam(client, alice)
    r1 = submit(client, alice, sid, qid).get_json()['response_id']
    submit(client, alice, sid, q2)
    assert student_score(client, alice, sid) == 8

    client.put(f'/api/v1/responses/{r1}', headers=alice, json={'score': 1})
    assert student_score(client, alice, sid) == 5

    assert client.put(f'/api/v1/responses/{r1}', headers=alice, json={'score': 6}).status_code == 400

    client.delete(f'/api/v1/responses/{r1}', headers=alice)
    assert student_score(client, alice, sid) == 4

    client.delete(f'/api/v1/questions/{q2}', headers=alice)
    assert student_score(client, alice, sid) == 0


def test_student_total_cannot_be_set_directly(client, alice):
    sid, _, _ = setup_exam(client, alice)
    assert client.put(f'/api/v1/students/{sid}', headers=alice, json={'score': 100}).status_code == 400
