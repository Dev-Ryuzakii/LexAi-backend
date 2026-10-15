import os
import sys
import tempfile

import pytest

# Configure before the app modules are imported: isolated SQLite file, in-memory counters.
_tmp = tempfile.mkdtemp(prefix='lexai-tests-')
os.environ['DATABASE_URL'] = f"sqlite:///{os.path.join(_tmp, 'test.db')}"
os.environ['REDIS_HOST'] = '127.0.0.1'
os.environ['REDIS_PORT'] = '1'  # nothing listens here, so the in-process counter is used
os.environ['DB_AUTO_CREATE'] = '1'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import api_service  # noqa: E402
from ai_service_manager import ai_service_manager  # noqa: E402
from app_api import app as flask_app  # noqa: E402
from database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    api_service.counter._memory.clear()
    yield


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


class FakeGrader:
    """Stands in for the AI providers; set .result to what the next grading returns."""

    def __init__(self):
        self.calls = 0
        self.result = self.grade(4)

    @staticmethod
    def grade(score, confidence=0.9, method='ollama', needs_review=False):
        return {
            'score': score, 'confidence': confidence, 'feedback': 'ok', 'strengths': ['a'], 'weaknesses': ['b'],
            'model_used': 'fake', 'scoring_method': method, 'max_score': 5, 'needs_review': needs_review,
            'cached': False,
        }

    @staticmethod
    def unavailable():
        return {'score': None, 'scoring_method': 'unavailable', 'error': 'all providers down'}

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return dict(self.result)


@pytest.fixture
def grader(monkeypatch):
    fake = FakeGrader()
    monkeypatch.setattr(ai_service_manager, 'score_answer', fake)
    return fake


PASSWORD = 'Str0ng!Pass'


def make_user(client, email):
    assert client.post('/api/v1/register', json={'email': email, 'password': PASSWORD}).status_code == 201
    res = client.post('/api/v1/login', json={'email': email, 'password': PASSWORD})
    assert res.status_code == 200, res.get_json()
    return {'Authorization': f"Bearer {res.get_json()['token']}"}


@pytest.fixture
def alice(client):
    return make_user(client, 'alice@example.com')


@pytest.fixture
def bob(client):
    return make_user(client, 'bob@example.com')
