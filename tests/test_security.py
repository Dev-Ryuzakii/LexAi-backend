from sqlalchemy.exc import OperationalError

import api_service
from database import APIKey, AuthToken, SessionLocal, User, hashlib, verify_password


def test_former_hardcoded_keys_are_rejected(client):
    for key in ('dev_key_123', 'test_key_789', 'dev_anything', 'test_anything'):
        res = client.get('/api/v1/questions', headers={'X-API-Key': key})
        assert res.status_code == 401, key
        assert res.get_json()['error']['code'] == 'AUTH_002'


def test_missing_credentials(client):
    res = client.get('/api/v1/questions')
    assert res.status_code == 401
    assert res.get_json()['error']['code'] == 'AUTH_001'


def test_auth_fails_closed_when_database_errors(client, monkeypatch):
    class BrokenSession:
        def query(self, *a, **k):
            raise OperationalError('SELECT', {}, Exception('db down'))

    monkeypatch.setattr(api_service, 'get_db', lambda: BrokenSession())
    res = client.get('/api/v1/questions', headers={'X-API-Key': 'dev_key_123'})
    assert res.status_code == 503
    assert res.get_json()['error']['code'] == 'AUTH_005'


def test_records_are_isolated_between_users(client, alice, bob):
    q = client.post('/api/v1/questions', headers=alice, json={'question_text': 'What is X?', 'marking_guide': 'X is Y'})
    s = client.post('/api/v1/students', headers=alice, json={'name': 'Ada', 'matric_number': 'M001'})
    qid, sid = q.get_json()['question_id'], s.get_json()['student_id']

    assert client.get('/api/v1/questions', headers=bob).get_json()['total_count'] == 0
    assert client.get('/api/v1/students', headers=bob).get_json()['total_count'] == 0
    assert client.get(f'/api/v1/questions/{qid}', headers=bob).status_code == 404
    assert client.put(f'/api/v1/questions/{qid}', headers=bob, json={'marking_guide': 'hijacked'}).status_code == 404
    assert client.delete(f'/api/v1/students/{sid}', headers=bob).status_code == 404
    assert client.post('/api/v1/submit-response', headers=bob,
                       json={'student_id': sid, 'question_id': qid, 'answer': 'x'}).status_code == 404

    assert client.get(f'/api/v1/questions/{qid}', headers=alice).get_json()['question']['marking_guide'] == 'X is Y'


def test_same_matric_number_allowed_for_different_owners(client, alice, bob):
    body = {'name': 'Ada', 'matric_number': 'M001'}
    assert client.post('/api/v1/students', headers=alice, json=body).status_code == 201
    assert client.post('/api/v1/students', headers=bob, json=body).status_code == 201


def test_api_key_is_created_for_the_caller_not_the_submitted_email(client, alice, bob):
    res = client.post('/api/v1/api-keys', headers=alice, json={'key_name': 'k', 'email': 'bob@example.com'})
    assert res.status_code == 201
    plaintext = res.get_json()['api_key']['api_key']

    db = SessionLocal()
    key = db.query(APIKey).one()
    alice_id = db.query(User).filter_by(email='alice@example.com').one().id
    db.close()
    assert key.user_id == alice_id
    assert client.get('/api/v1/api-keys', headers=bob).get_json()['total_count'] == 0

    # The key authenticates as Alice.
    client.post('/api/v1/questions', headers=alice, json={'question_text': 'Q', 'marking_guide': 'G'})
    assert client.get('/api/v1/questions', headers={'X-API-Key': plaintext}).get_json()['total_count'] == 1


def test_api_keys_are_stored_hashed_and_shown_once(client, alice):
    plaintext = client.post('/api/v1/api-keys', headers=alice, json={'key_name': 'k'}).get_json()['api_key']['api_key']
    db = SessionLocal()
    key = db.query(APIKey).one()
    db.close()
    assert key.key_hash == hashlib.sha256(plaintext.encode()).hexdigest()
    assert plaintext not in (key.key_hash, key.key_prefix)
    listed = client.get('/api/v1/api-keys', headers=alice).get_json()['api_keys'][0]
    assert listed['api_key'] != plaintext and plaintext.startswith(listed['key_prefix'])


def test_key_management_requires_a_session(client, alice):
    plaintext = client.post('/api/v1/api-keys', headers=alice, json={'key_name': 'k'}).get_json()['api_key']['api_key']
    res = client.post('/api/v1/api-keys', headers={'X-API-Key': plaintext}, json={'key_name': 'more'})
    assert res.status_code == 403


def test_key_limits_cannot_exceed_plan(client, alice):
    res = client.post('/api/v1/api-keys', headers=alice, json={'key_name': 'k', 'plan_type': 'test', 'rate_limit': 100000})
    assert res.status_code == 400


def test_revoked_and_rotated_keys_stop_working(client, alice):
    created = client.post('/api/v1/api-keys', headers=alice, json={'key_name': 'k'}).get_json()['api_key']
    rotated = client.post(f"/api/v1/api-keys/{created['id']}/rotate", headers=alice, json={}).get_json()
    assert client.get('/api/v1/questions', headers={'X-API-Key': created['api_key']}).status_code == 401
    assert client.get('/api/v1/questions', headers={'X-API-Key': rotated['new_api_key']}).status_code == 200
    client.delete(f"/api/v1/api-keys/{rotated['new_key_id']}", headers=alice)
    assert client.get('/api/v1/questions', headers={'X-API-Key': rotated['new_api_key']}).status_code == 401


def test_monthly_quota_is_enforced(client, alice):
    plaintext = client.post('/api/v1/api-keys', headers=alice,
                            json={'key_name': 'k', 'plan_type': 'test', 'monthly_quota': 3}).get_json()['api_key']['api_key']
    codes = [client.get('/api/v1/questions', headers={'X-API-Key': plaintext}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_passwords_and_tokens_are_not_stored_in_plaintext(client, alice):
    db = SessionLocal()
    user = db.query(User).filter_by(email='alice@example.com').one()
    tokens = [t.token for t in db.query(AuthToken).all()]
    db.close()
    assert 'Str0ng!Pass' not in user.password_hash and user.password_hash.count('$') >= 2
    assert alice['Authorization'].split(' ')[1] not in tokens


def test_legacy_password_hash_still_logs_in_and_is_upgraded(client):
    salt = 'abcd'
    legacy = hashlib.sha256(('Str0ng!Pass' + salt).encode()).hexdigest() + ':' + salt
    db = SessionLocal()
    db.add(User(email='old@example.com', password_hash=legacy))
    db.commit()
    db.close()

    assert client.post('/api/v1/login', json={'email': 'old@example.com', 'password': 'Str0ng!Pass'}).status_code == 200
    db = SessionLocal()
    upgraded = db.query(User).filter_by(email='old@example.com').one().password_hash
    db.close()
    assert upgraded != legacy and verify_password('Str0ng!Pass', upgraded)


def test_login_is_rate_limited(client):
    codes = [client.post('/api/v1/login', json={'email': 'x@example.com', 'password': 'wrong'}).status_code
             for _ in range(api_service.LOGIN_ATTEMPTS + 1)]
    assert codes[:-1] == [401] * api_service.LOGIN_ATTEMPTS
    assert codes[-1] == 429


def test_weak_password_rejected(client):
    res = client.post('/api/v1/register', json={'email': 'a@b.co', 'password': 'password'})
    assert res.status_code == 400
    assert res.get_json()['error']['code'] == 'VAL_001'


def test_logout_invalidates_token(client, alice):
    assert client.post('/api/v1/logout', headers=alice).status_code == 200
    assert client.get('/api/v1/questions', headers=alice).status_code == 401


def test_wrong_types_are_400_not_500(client, alice):
    for body in ({'question_text': 123, 'marking_guide': 'g'}, {'question_text': ['a'], 'marking_guide': 'g'}):
        assert client.post('/api/v1/questions', headers=alice, json=body).status_code == 400
    assert client.post('/api/v1/submit-response', headers=alice,
                       json={'student_id': '1', 'question_id': True, 'answer': 'x'}).status_code == 400
    assert client.post('/api/v1/questions', headers=alice, data='not json',
                       content_type='application/json').status_code == 400
