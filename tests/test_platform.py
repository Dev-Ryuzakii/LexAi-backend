import csv
import io
import json

import pytest
import requests
import yaml

import batch
import resilience
import webhooks
from ai_service_manager import AIServiceManager
from resilience import CircuitBreaker, backoff_delay, retry_call
from scoring import ScoringError


@pytest.fixture(autouse=True)
def synchronous_background(monkeypatch):
    """Run webhook deliveries and jobs inline, and skip real backoff sleeps."""
    monkeypatch.setattr(webhooks, '_submit', lambda fn, *args: fn(*args))
    monkeypatch.setattr(batch, '_submit_job', lambda fn, *args: fn(*args))
    monkeypatch.setattr(resilience.time, 'sleep', lambda s: None)


@pytest.fixture
def deliveries(monkeypatch):
    """Capture webhook POSTs instead of sending them."""
    sent = []

    class Reply:
        status_code = 200

    def fake_post(url, data, headers, **kwargs):
        sent.append({'url': url, 'body': json.loads(data), 'raw': data, 'headers': headers})
        return Reply()

    monkeypatch.setattr(webhooks.requests, 'post', fake_post)
    monkeypatch.setattr(webhooks, 'check_target', lambda url: None)
    return sent


def new_key(client, headers, **extra):
    res = client.post('/api/v1/api-keys', headers=headers, json={'key_name': 'k', **extra})
    assert res.status_code == 201, res.get_json()
    body = res.get_json()['api_key']
    return body['id'], {'X-API-Key': body['api_key']}


def add_question(client, headers, text='What is X?'):
    return client.post('/api/v1/questions', headers=headers,
                       json={'question_text': text, 'marking_guide': 'X is Y'}).get_json()['question_id']


# --- Analytics -------------------------------------------------------------------------

def test_analytics_reflect_api_key_traffic(client, alice):
    _, key = new_key(client, alice)
    for _ in range(3):
        assert client.get('/api/v1/questions', headers=key).status_code == 200
    client.get('/api/v1/questions/999', headers=key)  # 404

    quota = client.get('/api/v1/analytics/quota', headers=alice).get_json()['quota_usage']
    assert quota['used'] == 4 and quota['quota'] == 10000 and quota['remaining'] == 9996

    stats = client.get('/api/v1/analytics/stats', headers=key).get_json()['statistics']
    assert stats['total_requests'] >= 4
    assert stats['error_requests'] >= 1
    assert stats['status_code_stats']['404'] == 1

    timeline = client.get('/api/v1/analytics/timeline?days=7&group_by=day', headers=alice).get_json()['timeline']
    assert len(timeline) == 1 and timeline[0]['count'] >= 4

    top = client.get('/api/v1/analytics/top-endpoints?limit=1', headers=key).get_json()['top_endpoints']
    assert top[0]['endpoint'] == '/api/v1/questions' and top[0]['count'] == 3


def test_analytics_compare_and_export(client, alice):
    client.get('/api/v1/questions', headers=alice)
    res = client.get('/api/v1/analytics/compare?period1_start=2020-01-01&period1_end=2020-01-31'
                     '&period2_start=2020-02-01&period2_end=2099-12-31', headers=alice)
    comparison = res.get_json()['comparison']
    assert comparison['period1']['stats']['total_requests'] == 0
    assert comparison['period2']['stats']['total_requests'] >= 1
    assert comparison['changes']['total_requests']['percentage'] == 100.0

    export = client.get('/api/v1/analytics/export?format=csv', headers=alice)
    assert export.mimetype == 'text/csv'
    assert 'endpoint' in export.get_data(as_text=True).splitlines()[0]
    assert client.get('/api/v1/analytics/stats?start_date=yesterday', headers=alice).status_code == 400


def test_users_only_see_their_own_usage(client, alice, bob):
    for _ in range(5):
        client.get('/api/v1/questions', headers=alice)
    stats = client.get('/api/v1/analytics/stats', headers=bob).get_json()['statistics']
    assert stats['total_requests'] == 0


# --- IP rules ----------------------------------------------------------------------------

def test_ip_allow_and_deny_rules(client, alice):
    key_id, key = new_key(client, alice)
    url = f'/api/v1/api-keys/{key_id}/ip-rules'
    assert client.post(url, headers=alice, json={'ip_address': 'not-an-ip'}).status_code == 400

    allow = client.post(url, headers=alice, json={'ip_address': '10.0.0.0/8', 'is_whitelist': True}).get_json()['rule']
    assert client.get('/api/v1/questions', headers=key).status_code == 403  # test client is 127.0.0.1

    client.delete(f"{url}/{allow['id']}", headers=alice)
    assert client.get('/api/v1/questions', headers=key).status_code == 200

    client.post(url, headers=alice, json={'ip_address': '127.0.0.1/32', 'is_whitelist': False})
    assert client.get('/api/v1/questions', headers=key).status_code == 403
    assert client.get(url, headers=alice).get_json()['ip_rules'][0]['ip_address'] == '127.0.0.1'


def test_ip_rules_follow_rotation_and_are_private(client, alice, bob):
    key_id, _ = new_key(client, alice)
    client.post(f'/api/v1/api-keys/{key_id}/ip-rules', headers=alice, json={'ip_address': '10.0.0.1'})
    assert client.get(f'/api/v1/api-keys/{key_id}/ip-rules', headers=bob).status_code == 404
    rotated = client.post(f'/api/v1/api-keys/{key_id}/rotate', headers=alice, json={}).get_json()
    rules = client.get(f"/api/v1/api-keys/{rotated['new_key_id']}/ip-rules", headers=alice).get_json()
    assert rules['total_count'] == 1


# --- Webhooks ------------------------------------------------------------------------------

def test_webhook_targets_must_be_public():
    for url in ('https://127.0.0.1/hook', 'https://10.1.2.3/hook', 'https://169.254.169.254/latest', 'ftp://8.8.8.8/x',
                'http://8.8.8.8/hook'):
        with pytest.raises(webhooks.UnsafeTarget):
            webhooks.check_target(url)
    webhooks.check_target('https://8.8.8.8/hook')


def test_webhook_lifecycle_and_signed_delivery(client, alice, bob, grader, deliveries):
    res = client.post('/api/v1/webhooks', headers=alice,
                      json={'url': 'https://hooks.example.com/lexai', 'events': ['scoring.complete']})
    assert res.status_code == 201
    secret = res.get_json()['webhook']['secret']
    assert secret.startswith('whsec_')
    listed = client.get('/api/v1/webhooks', headers=alice).get_json()['webhooks']
    assert 'secret' not in listed[0]
    assert client.get('/api/v1/webhooks', headers=bob).get_json()['total_count'] == 0

    client.post('/api/v1/score', headers=alice, json={'student_answer': 'a', 'marking_guide': 'b'})
    assert len(deliveries) == 1
    sent = deliveries[0]
    assert sent['body']['event'] == 'scoring.complete' and sent['body']['data']['score'] == 4
    expected = webhooks.sign(secret, sent['headers']['X-LexAi-Timestamp'], sent['raw'])
    assert sent['headers']['X-LexAi-Signature'] == expected

    hook_id = listed[0]['id']
    assert client.get('/api/v1/webhooks', headers=alice).get_json()['webhooks'][0]['last_status'] == '200'
    assert client.delete(f'/api/v1/webhooks/{hook_id}', headers=bob).status_code == 404
    assert client.delete(f'/api/v1/webhooks/{hook_id}', headers=alice).status_code == 200


def test_webhook_validation(client, alice, deliveries):
    assert client.post('/api/v1/webhooks', headers=alice,
                       json={'url': 'https://x.example.com', 'events': ['made.up']}).status_code == 400
    assert client.post('/api/v1/webhooks', headers=alice,
                       json={'url': 'https://x.example.com', 'events': ['scoring.complete'], 'secret': 'short'}).status_code == 400


def test_webhook_delivery_retries_transient_failures(client, alice, monkeypatch):
    monkeypatch.setattr(webhooks, 'check_target', lambda url: None)
    calls = []

    class Reply:
        def __init__(self, code):
            self.status_code = code

    def flaky_post(url, data, headers, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise requests.exceptions.ConnectionError('reset')
        if len(calls) == 2:
            return Reply(503)
        return Reply(204)

    monkeypatch.setattr(webhooks.requests, 'post', flaky_post)
    client.post('/api/v1/webhooks', headers=alice, json={'url': 'https://h.example.com', 'events': ['api_key.revoked']})
    key_id, _ = new_key(client, alice)
    client.delete(f'/api/v1/api-keys/{key_id}', headers=alice)
    assert len(calls) == 3
    assert client.get('/api/v1/webhooks', headers=alice).get_json()['webhooks'][0]['last_status'] == '204'


def test_quota_warning_and_exceeded_events(client, alice, deliveries):
    client.post('/api/v1/webhooks', headers=alice,
                json={'url': 'https://h.example.com', 'events': ['quota.warning', 'quota.exceeded']})
    _, key = new_key(client, alice, plan_type='test', monthly_quota=5)
    codes = [client.get('/api/v1/questions', headers=key).status_code for _ in range(6)]
    assert codes[-1] == 429
    assert [d['body']['event'] for d in deliveries] == ['quota.warning', 'quota.exceeded']


# --- Batch scoring and jobs ------------------------------------------------------------------

def test_batch_scoring_reports_per_item(client, alice, grader):
    answers = [{'student_answer': 'a', 'marking_guide': 'g', 'metadata': {'n': 1}},
               {'student_answer': '', 'marking_guide': 'g'},
               'not an object',
               {'student_answer': 'b', 'marking_guide': 'g', 'student_name': 'Ada'}]
    body = client.post('/api/v1/score/batch', headers=alice, json={'answers': answers}).get_json()
    assert (body['total'], body['processed'], body['failed']) == (4, 2, 2)
    assert body['results'][0]['metadata'] == {'n': 1}
    assert body['results'][3]['student_info']['name'] == 'Ada'
    assert not body['results'][1]['success'] and 'student_answer' in body['results'][1]['error']
    assert client.post('/api/v1/score/batch', headers=alice, json={'answers': [{}] * 101}).status_code == 400


def test_batch_counts_each_answer_against_quota(client, alice, grader):
    _, key = new_key(client, alice, plan_type='test', monthly_quota=3)
    answers = [{'student_answer': 'a', 'marking_guide': 'g'}] * 3
    assert client.post('/api/v1/score/batch', headers=key, json={'answers': answers}).status_code == 200
    res = client.get('/api/v1/questions', headers=key)
    assert res.status_code == 429 and int(res.headers['Retry-After']) > 0


def test_async_batch_job(client, alice, bob, grader):
    res = client.post('/api/v1/score/batch?async=true', headers=alice,
                      json={'answers': [{'student_answer': 'a', 'marking_guide': 'g'}]})
    assert res.status_code == 202
    job_id = res.get_json()['job_id']
    job = client.get(f'/api/v1/jobs/{job_id}', headers=alice).get_json()['job']
    assert job['status'] == 'finished' and job['result']['processed'] == 1
    assert client.get(f'/api/v1/jobs/{job_id}', headers=bob).status_code == 404


# --- Bulk, upload, export ----------------------------------------------------------------------

def test_bulk_questions_and_students(client, alice, grader):
    created = client.post('/api/v1/bulk/questions', headers=alice, json={'questions': [
        {'question_text': 'Q1', 'marking_guide': 'G1'}, {'question_text': 'Q2'}, {'question_text': 'Q3', 'marking_guide': 'G3'},
    ]}).get_json()['result']
    assert created['created'] == 2 and created['failed_indices'] == [1]
    q1, q3 = created['created_ids']

    students = client.post('/api/v1/bulk/students', headers=alice, json={'students': [
        {'name': 'Ada', 'matric_number': 'M1'}, {'name': 'Bo', 'matric_number': 'M1'},
    ]}).get_json()['result']
    assert students['created'] == 1 and students['failed'] == 1
    sid = students['created_ids'][0]

    updated = client.put('/api/v1/bulk/questions/update', headers=alice, json={'updates': [
        {'id': q1, 'marking_guide': 'New'}, {'id': 99999, 'marking_guide': 'x'}]}).get_json()['result']
    assert updated['updated'] == 1 and updated['failed'] == 1
    assert client.get(f'/api/v1/questions/{q1}', headers=alice).get_json()['question']['marking_guide'] == 'New'

    client.post('/api/v1/submit-response', headers=alice, json={'student_id': sid, 'question_id': q1, 'answer': 'a'})
    deleted = client.post('/api/v1/bulk/questions/delete', headers=alice,
                          json={'question_ids': [q1, q3, 424242]}).get_json()['result']
    assert deleted['deleted_ids'] == [q1, q3] and deleted['failed_ids'] == [424242]
    assert client.get(f'/api/v1/students/{sid}', headers=alice).get_json()['student']['score'] == 0


def test_upload_and_export(client, alice):
    csv_file = io.BytesIO(b'question_text,marking_guide\n=CMD(),Guide one\nQuestion two,Guide two\n,missing\n')
    res = client.post('/api/v1/upload/questions', headers=alice, data={'file': (csv_file, 'q.csv')},
                      content_type='multipart/form-data')
    body = res.get_json()
    assert body['total_in_file'] == 3 and body['result']['created'] == 2

    json_file = io.BytesIO(json.dumps([{'name': 'Ada', 'matric_number': 'M1'}]).encode())
    res = client.post('/api/v1/upload/students', headers=alice, data={'file': (json_file, 's.json')},
                      content_type='multipart/form-data')
    assert res.get_json()['result']['created'] == 1

    bad = client.post('/api/v1/upload/students', headers=alice, data={'file': (io.BytesIO(b'x'), 's.txt')},
                      content_type='multipart/form-data')
    assert bad.status_code == 400

    exported = client.get('/api/v1/export/questions?format=csv', headers=alice)
    rows = list(csv.DictReader(io.StringIO(exported.get_data(as_text=True))))
    assert rows[0]['question_text'] == "'=CMD()"  # neutralised spreadsheet formula
    assert 'attachment' in exported.headers['Content-Disposition']
    assert len(client.get('/api/v1/export/students?format=json', headers=alice).get_json()) == 1


# --- Changelog and OpenAPI ------------------------------------------------------------------------

def test_changelog_is_public(client):
    body = client.get('/api/v1/changelog').get_json()
    assert body['latest_version'] == '1.3.0' and body['total_versions'] == 4
    assert client.get('/api/v1/changelog?version=1.1.0').get_json()['changelog'][0]['version'] == '1.1.0'
    assert client.get('/api/v1/changelog/breaking-changes').get_json()['breaking_changes']
    assert client.get('/api/v1/changelog/deprecations').get_json()['deprecations']


def test_openapi_is_generated_from_routes(client):
    spec = client.get('/api/v1/openapi.json').get_json()
    score = spec['paths']['/score']['post']
    assert 'student_answer' in score['requestBody']['content']['application/json']['schema']['required']
    assert {'ApiKeyAuth': []} in score['security']
    assert spec['paths']['/api-keys']['post']['security'] == [{'BearerAuth': []}]
    assert spec['paths']['/health']['get']['security'] == []
    assert '/webhooks' in spec['paths'] and '/analytics/stats' in spec['paths']
    assert yaml.safe_load(client.get('/api/v1/openapi.yaml').get_data(as_text=True))['openapi'] == '3.0.3'


# --- Idempotency and retries -------------------------------------------------------------------

def test_idempotency_key_replays_instead_of_duplicating(client, alice):
    headers = {**alice, 'Idempotency-Key': 'create-q-1'}
    body = {'question_text': 'Q', 'marking_guide': 'G'}
    first = client.post('/api/v1/questions', headers=headers, json=body)
    second = client.post('/api/v1/questions', headers=headers, json=body)
    assert first.status_code == second.status_code == 201
    assert second.headers['Idempotent-Replayed'] == 'true'
    assert first.get_json()['question_id'] == second.get_json()['question_id']
    assert client.get('/api/v1/questions', headers=alice).get_json()['total_count'] == 1

    changed = client.post('/api/v1/questions', headers=headers, json={**body, 'question_text': 'Other'})
    assert changed.status_code == 422


def test_idempotency_does_not_cache_server_errors(client, alice, grader):
    qid = add_question(client, alice)
    sid = client.post('/api/v1/students', headers=alice, json={'name': 'A', 'matric_number': 'M'}).get_json()['student_id']
    headers = {**alice, 'Idempotency-Key': 'submit-1'}
    body = {'student_id': sid, 'question_id': qid, 'answer': 'x'}
    grader.result = grader.unavailable()
    failed = client.post('/api/v1/submit-response', headers=headers, json=body)
    assert failed.status_code == 503 and failed.headers['Retry-After']
    grader.result = grader.grade(4)
    assert client.post('/api/v1/submit-response', headers=headers, json=body).status_code == 201
    assert client.post('/api/v1/submit-response', headers=headers, json=body).headers.get('Idempotent-Replayed') == 'true'


def test_retry_call_with_jitter():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError('blip')
        return 'ok'

    assert retry_call(flaky, attempts=3, sleep=lambda s: None) == 'ok'
    with pytest.raises(ValueError):
        retry_call(lambda: (_ for _ in ()).throw(ValueError('no')), attempts=5,
                   should_retry=lambda e: False, sleep=lambda s: None)
    delays = [backoff_delay(4, base=1, cap=5) for _ in range(200)]
    assert all(0 <= d <= 5 for d in delays) and len(set(delays)) > 100  # bounded and randomised


def test_circuit_breaker_skips_failing_provider():
    calls = []

    class Failing:
        model = 'fake'

        def check_connection(self):
            return True

        def score_answer(self, *args):
            calls.append(1)
            raise ScoringError('down')

    manager = AIServiceManager()
    manager.services = {'ollama': Failing()}
    manager.fallback_chain = ['ollama']
    manager.active_service = 'ollama'
    manager.breaker_threshold = 2
    manager.allow_similarity_fallback = False
    for _ in range(4):
        assert manager.score_answer('a', 'b')['scoring_method'] == 'unavailable'
    assert len(calls) == 2  # the last two calls were short-circuited
    assert manager.breakers['ollama'].state == 'open'

    breaker = CircuitBreaker('x', failure_threshold=1, reset_timeout=0)
    breaker.record_failure()
    assert breaker.state == 'half_open' and breaker.allow()
