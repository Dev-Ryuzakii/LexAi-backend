"""
LexAi API routes.

Every assessment record (question, student, response) belongs to the user who
created it, and every query is scoped to the authenticated user.
"""
import hashlib
import ipaddress
import logging
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

import redis
from flask import g, jsonify, make_response, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ai_service_manager import ai_service_manager
from database import (
    APIKey, ApiUsage, AuthToken, GRADED, IdempotencyRecord, IPRule, NEEDS_REVIEW, Question, Response, SessionLocal, Student, User,
    effective_score, hash_password, hash_secret, password_needs_rehash, recalculate_student_score,
    verify_password,
)
from scoring import MAX_SCORE

API_VERSION = '1.3.0'

os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('logs/api.log')],
)
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


TOKEN_TTL_HOURS = _env_int('TOKEN_TTL_HOURS', 24)
SESSION_RATE_LIMIT = _env_int('SESSION_RATE_LIMIT', 1000)  # requests/hour for dashboard sessions
LOGIN_ATTEMPTS = _env_int('LOGIN_ATTEMPTS_PER_15_MIN', 10)
REGISTRATIONS = _env_int('REGISTRATIONS_PER_HOUR', 5)
MAX_ACTIVE_KEYS = _env_int('MAX_ACTIVE_API_KEYS', 20)
MAX_PAGE_SIZE = 500

# Upper bounds a user may request for a key on each plan.
PLAN_LIMITS = {
    'test': {'rate_limit': 100, 'monthly_quota': 1000},
    'production': {'rate_limit': 1000, 'monthly_quota': 10000},
}

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# --- Counters (rate limits and quotas) ----------------------------------------------

class Counter:
    """Fixed-window counters in Redis, or in process memory when Redis is unreachable."""

    def __init__(self):
        self._memory: Dict[str, Tuple[int, float]] = {}
        self._lock = threading.Lock()
        self.redis = None
        try:
            client = redis.Redis(
                host=os.environ.get('REDIS_HOST', 'localhost'),
                port=_env_int('REDIS_PORT', 6379),
                password=os.environ.get('REDIS_PASSWORD') or None,
                db=0,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            self.redis = client
            logger.info("Redis connected for rate limiting")
        except Exception as e:
            logger.warning(f"Redis unavailable, using per-process rate limiting: {e}")

    def incr(self, key: str, ttl_seconds: int) -> int:
        return self.incr_by(key, 1, ttl_seconds)

    def incr_by(self, key: str, amount: int, ttl_seconds: int) -> int:
        if self.redis is not None:
            try:
                count = self.redis.incrby(key, amount)
                if count == amount:
                    self.redis.expire(key, ttl_seconds)
                return int(count)
            except Exception as e:
                logger.error(f"Redis counter error, falling back to memory: {e}")
        now = time.time()
        with self._lock:
            count, expires = self._memory.get(key, (0, now + ttl_seconds))
            if expires <= now:
                count, expires = 0, now + ttl_seconds
            count += amount
            self._memory[key] = (count, expires)
            if len(self._memory) > 50000:
                self._memory = {k: v for k, v in self._memory.items() if v[1] > now}
            return count


counter = Counter()


# --- Errors, sessions, validation ----------------------------------------------------

def api_error(status: int, code: str, message: str, retry_after: Optional[int] = None, **details):
    body = {
        'success': False,
        'error': {'code': code, 'message': message, 'details': details},
        'message': message,
        'request_id': getattr(g, 'request_id', None),
        'timestamp': datetime.utcnow().isoformat(),
    }
    response = jsonify(body)
    response.status_code = status
    if retry_after is None and status == 503:
        retry_after = 5
    if retry_after is not None:
        # Tells clients how long to wait before retrying (seconds).
        response.headers['Retry-After'] = str(max(int(retry_after), 1))
    return response


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def get_db():
    if 'db' not in g:
        g.db = SessionLocal()
    return g.db


def validate_fields(data: Dict[str, Any], rules: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Check `data` against `rules`; returns (cleaned values, errors).
    Rule keys: type (str|int|float|bool|list|dict), required, max_length, min, max, choices, max_items.
    """
    cleaned, errors = {}, []

    def fail(field, message, kind, value=None):
        errors.append({'field': field, 'message': message, 'type': kind, 'input': value})

    for field, rule in rules.items():
        if field not in data or data[field] is None:
            if rule.get('required'):
                fail(field, 'Field is required', 'missing')
            continue
        value = data[field]
        kind = rule['type']
        if kind is str:
            if not isinstance(value, str):
                fail(field, 'Must be a string', 'type_error', value)
                continue
            value = value.strip()
            if rule.get('required') and not value:
                fail(field, 'Must not be empty', 'value_error')
                continue
            if len(value) > rule.get('max_length', 10000):
                fail(field, f"Must be at most {rule.get('max_length', 10000)} characters", 'value_error')
                continue
        elif kind is bool:
            if not isinstance(value, bool):
                fail(field, 'Must be true or false', 'type_error', value)
                continue
        elif kind in (list, dict):
            if not isinstance(value, kind):
                fail(field, f"Must be {'a list' if kind is list else 'an object'}", 'type_error')
                continue
            if kind is list and rule.get('required') and not value:
                fail(field, 'Must not be empty', 'value_error')
                continue
            if kind is list and len(value) > rule.get('max_items', 1000):
                fail(field, f"Must have at most {rule.get('max_items', 1000)} items", 'value_error')
                continue
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                fail(field, 'Must be a number', 'type_error', value)
                continue
            if kind is int and value != int(value):
                fail(field, 'Must be a whole number', 'type_error', value)
                continue
            value = kind(value)
            if 'min' in rule and value < rule['min']:
                fail(field, f"Must be at least {rule['min']}", 'value_error', value)
                continue
            if 'max' in rule and value > rule['max']:
                fail(field, f"Must be at most {rule['max']}", 'value_error', value)
                continue
        if 'choices' in rule and value not in rule['choices']:
            fail(field, f"Must be one of: {', '.join(map(str, rule['choices']))}", 'value_error', value)
            continue
        cleaned[field] = value
    return cleaned, errors


def validation_error(errors: List[Dict[str, Any]]):
    summary = '; '.join(f"{e['field']}: {e['message']}" for e in errors)
    return api_error(400, 'VAL_001', f'Validation failed: {summary}', validation_errors=errors)


def validate_body(rules: Dict[str, Dict[str, Any]], allow_empty: bool = False):
    """Validate the JSON body against `rules` and store the cleaned values in g.body."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            data = request.get_json(silent=True)
            if data is None and allow_empty:
                data = {}
            if not isinstance(data, dict):
                return api_error(400, 'VAL_002', 'Request body must be a JSON object')
            cleaned, errors = validate_fields(data, rules)
            if errors:
                return validation_error(errors)
            g.body = cleaned
            return f(*args, **kwargs)
        wrapper._body_rules = rules  # read by the OpenAPI generator
        return wrapper
    return decorator


def pagination() -> Tuple[int, int]:
    try:
        limit = min(max(int(request.args.get('limit', MAX_PAGE_SIZE)), 1), MAX_PAGE_SIZE)
        offset = max(int(request.args.get('offset', 0)), 0)
    except ValueError:
        limit, offset = MAX_PAGE_SIZE, 0
    return limit, offset


def client_ip() -> str:
    return request.remote_addr or 'unknown'


# --- Authentication -------------------------------------------------------------------

def _authenticate() -> Optional[tuple]:
    """Resolve the caller into g.principal. Returns an error response, or None on success."""
    auth_header = request.headers.get('Authorization', '')
    bearer = auth_header[7:].strip() if auth_header.startswith('Bearer ') else None
    api_key = request.headers.get('X-API-Key')

    if not bearer and not api_key:
        return api_error(401, 'AUTH_001', 'Provide an API key in the X-API-Key header or a session token in the Authorization header')

    db = get_db()
    try:
        if bearer:
            row = db.query(AuthToken, User).join(User, AuthToken.user_id == User.id).filter(
                AuthToken.token == hash_secret(bearer),
                AuthToken.is_active.is_(True),
                AuthToken.expires_at > datetime.utcnow(),
                User.is_active.is_(True),
            ).first()
            if not row:
                return api_error(401, 'AUTH_002', 'The session token is invalid or has expired')
            token, user = row
            g.principal = {
                'kind': 'session',
                'user_id': user.id,
                'email': user.email,
                'token_id': token.id,
                'limit_key': f'user:{user.id}',
                'rate_limit': SESSION_RATE_LIMIT,
                'monthly_quota': None,
            }
        else:
            row = db.query(APIKey, User).join(User, APIKey.user_id == User.id).filter(
                APIKey.key_hash == hash_secret(api_key),
                APIKey.is_active.is_(True),
                User.is_active.is_(True),
            ).first()
            if not row:
                return api_error(401, 'AUTH_002', 'The API key is invalid or has been revoked')
            key, user = row
            denied = _check_ip_rules(db, key.id)
            if denied:
                return denied
            g.principal = {
                'kind': 'api_key',
                'user_id': user.id,
                'email': user.email,
                'key_id': key.id,
                'limit_key': f'key:{key.id}',
                'rate_limit': key.rate_limit or 0,
                'monthly_quota': key.monthly_quota or 0,
            }
    except SQLAlchemyError:
        logger.exception(f"Request {g.request_id}: authentication lookup failed")
        # Fail closed: never let a request through because the credential store is down.
        return api_error(503, 'AUTH_005', 'Authentication is temporarily unavailable')
    return None


def _check_ip_rules(db, key_id: int) -> Optional[tuple]:
    """Blacklist rules always deny; if any whitelist rule exists, the caller must match one."""
    rules = db.query(IPRule).filter_by(api_key_id=key_id).all()
    if not rules:
        return None
    try:
        ip = ipaddress.ip_address(client_ip())
    except ValueError:
        return api_error(403, 'AUTH_006', 'Request IP address could not be verified for this API key')

    def matches(rule):
        try:
            return ip in ipaddress.ip_network(rule.ip_address, strict=False)
        except ValueError:
            return False

    if any(matches(r) for r in rules if not r.is_whitelist):
        return api_error(403, 'AUTH_006', 'This IP address is blocked for this API key')
    whitelist = [r for r in rules if r.is_whitelist]
    if whitelist and not any(matches(r) for r in whitelist):
        return api_error(403, 'AUTH_006', 'This IP address is not allowed for this API key')
    return None


def consume_quota(units: int = 1) -> Optional[tuple]:
    """Charge `units` against the caller's monthly quota (API keys only). Returns an error if exhausted."""
    p = g.principal
    quota = p['monthly_quota']
    if quota is None or units <= 0:
        return None
    now = datetime.utcnow()
    used = counter.incr_by(f"quota:{p['limit_key']}:{now:%Y%m}", units, 32 * 24 * 3600)
    before = used - units

    import webhooks  # local import: webhooks imports this module
    warning_at = int(quota * 0.8)
    if before < warning_at <= used <= quota:
        webhooks.emit(p['user_id'], 'quota.warning', {'api_key_id': p.get('key_id'), 'used': used, 'quota': quota})
    if before <= quota < used:
        webhooks.emit(p['user_id'], 'quota.exceeded', {'api_key_id': p.get('key_id'), 'used': used, 'quota': quota})

    if used > quota:
        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return api_error(429, 'RATE_002', f"Monthly quota of {quota} requests exhausted",
                         retry_after=(next_month - now).total_seconds(), quota=quota, reset_time=next_month.isoformat())
    return None


def _enforce_limits() -> Optional[tuple]:
    p = g.principal
    now = datetime.utcnow()

    hour_start = now.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)
    used = counter.incr(f"rl:{p['limit_key']}:{hour_start:%Y%m%d%H}", 3600)
    g.rate_limit_headers = {
        'X-RateLimit-Limit': str(p['rate_limit']),
        'X-RateLimit-Used': str(used),
        'X-RateLimit-Remaining': str(max(p['rate_limit'] - used, 0)),
        'X-RateLimit-Reset': hour_end.isoformat(),
    }
    if used > p['rate_limit']:
        return api_error(429, 'RATE_001', f"Rate limit of {p['rate_limit']} requests per hour exceeded",
                         retry_after=(hour_end - now).total_seconds(),
                         limit=p['rate_limit'], reset_time=hour_end.isoformat())

    return consume_quota(1)


def require_auth(f):
    """Accepts an API key or a dashboard session token; applies rate limit and monthly quota."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        failure = _authenticate() or _enforce_limits()
        if failure:
            return failure
        return f(*args, **kwargs)
    wrapper._auth = 'api_key_or_session'
    return wrapper


def require_session(f):
    """Account management (API keys, logout) needs a logged-in session, not an API key."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        failure = _authenticate()
        if failure:
            return failure
        if g.principal['kind'] != 'session':
            return api_error(403, 'AUTH_003', 'This endpoint requires a logged-in session, not an API key')
        failure = _enforce_limits()
        if failure:
            return failure
        return f(*args, **kwargs)
    wrapper._auth = 'session'
    return wrapper


IDEMPOTENCY_TTL = timedelta(hours=24)


def idempotent(f):
    """
    Honour an Idempotency-Key header on POSTs: the first request runs, and a retry with the
    same key and body within 24h gets the stored response instead of running again.
    Server errors (5xx) are not stored, so the client can retry them. Place below @require_auth.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        key = request.headers.get('Idempotency-Key')
        if not key:
            return f(*args, **kwargs)
        if len(key) > 100:
            return api_error(400, 'IDEMP_003', 'Idempotency-Key must be at most 100 characters')

        user_id = current_user_id()
        fingerprint = hashlib.sha256(
            request.method.encode() + b' ' + request.path.encode() + b'\n' + request.get_data()).hexdigest()
        db = SessionLocal()
        try:
            db.query(IdempotencyRecord).filter(
                IdempotencyRecord.created_at < datetime.utcnow() - IDEMPOTENCY_TTL).delete(synchronize_session=False)
            existing = db.query(IdempotencyRecord).filter_by(user_id=user_id, key=key).first()
            if existing:
                if existing.fingerprint != fingerprint:
                    return api_error(422, 'IDEMP_001', 'This Idempotency-Key was already used with a different request')
                if existing.status_code is None:
                    return api_error(409, 'IDEMP_002', 'A request with this Idempotency-Key is still being processed',
                                     retry_after=2)
                replay = app_response(existing.response_body, existing.status_code)
                replay.headers['Idempotent-Replayed'] = 'true'
                return replay
            db.add(IdempotencyRecord(user_id=user_id, key=key, fingerprint=fingerprint))
            try:
                db.commit()
            except IntegrityError:
                # A concurrent request with the same key just claimed it.
                db.rollback()
                return api_error(409, 'IDEMP_002', 'A request with this Idempotency-Key is still being processed',
                                 retry_after=2)
        finally:
            db.close()

        result = None
        try:
            result = f(*args, **kwargs)
            return result
        finally:
            db = SessionLocal()
            try:
                record = db.query(IdempotencyRecord).filter_by(user_id=user_id, key=key).first()
                response = make_response(result) if result is not None else None
                if response is None or response.status_code >= 500:
                    db.delete(record)
                else:
                    record.status_code = response.status_code
                    record.response_body = response.get_data(as_text=True)
                db.commit()
            except Exception:
                logger.exception('Could not store idempotent response')
            finally:
                db.close()
    return wrapper


def app_response(body: str, status: int):
    response = make_response(body, status)
    response.mimetype = 'application/json'
    return response


def limit_by_ip(name: str, limit: int, window_seconds: int):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            now = time.time()
            window = int(now) // window_seconds
            if counter.incr(f"ip:{name}:{client_ip()}:{window}", window_seconds) > limit:
                return api_error(429, 'RATE_003', 'Too many attempts. Try again later.',
                                 retry_after=(window + 1) * window_seconds - now)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def current_user_id() -> int:
    return g.principal['user_id']


# --- Serializers ------------------------------------------------------------------------

def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def question_json(q: Question) -> Dict[str, Any]:
    return {'id': q.id, 'question_text': q.question_text, 'marking_guide': q.marking_guide, 'created_at': _iso(q.created_at)}


def student_json(s: Student) -> Dict[str, Any]:
    return {'id': s.id, 'name': s.name, 'matric_number': s.matric_number, 'score': s.score or 0.0, 'created_at': _iso(s.created_at)}


def response_json(r: Response) -> Dict[str, Any]:
    return {
        'id': r.id,
        'student_id': r.student_id,
        'question_id': r.question_id,
        'answer': r.answer,
        'score': effective_score(r),
        'max_score': r.max_score,
        'grading_status': r.grading_status,
        'scoring_method': r.scoring_method,
        'ai_score': r.ai_score,
        'lecturer_score': r.lecturer_score,
        'ai_feedback': r.ai_feedback,
        'ai_confidence': r.ai_confidence,
        'created_at': _iso(r.created_at),
    }


def api_key_json(k: APIKey) -> Dict[str, Any]:
    return {
        'id': k.id,
        'key_name': k.key_name,
        # The full key is never stored, so lists only show its prefix.
        'api_key': f'{k.key_prefix}…',
        'key_prefix': k.key_prefix,
        'user_id': k.user_id,
        'plan_type': k.plan_type,
        'rate_limit': k.rate_limit,
        'monthly_quota': k.monthly_quota,
        'is_active': k.is_active,
        'created_at': _iso(k.created_at),
    }


def new_api_key(db, user_id: int, key_name: str, plan_type: str, rate_limit: int, monthly_quota: int) -> Tuple[APIKey, str]:
    plaintext = f"lexai_{secrets.token_urlsafe(32)}"
    key = APIKey(
        key_name=key_name,
        key_hash=hash_secret(plaintext),
        key_prefix=plaintext[:12],
        user_id=user_id,
        plan_type=plan_type,
        rate_limit=rate_limit,
        monthly_quota=monthly_quota,
        is_active=True,
    )
    db.add(key)
    return key, plaintext


# --- Scoring -----------------------------------------------------------------------------

def score_answer(student_answer: str, marking_guide: str, question_text: str = "") -> Dict[str, Any]:
    """Grade an answer. success=False means no grade was produced; it never means a zero."""
    start = time.time()
    try:
        result = ai_service_manager.score_answer(student_answer, marking_guide, question_text)
    except Exception:
        logger.exception("Scoring raised unexpectedly")
        result = {'scoring_method': 'unavailable', 'error': 'Unexpected scoring error'}
    elapsed = round(time.time() - start, 3)

    if result.get('scoring_method') in ('unavailable', 'error') or result.get('score') is None:
        return {
            'success': False,
            'scoring_method': 'unavailable',
            'processing_time': elapsed,
            'message': result.get('error') or 'No scoring method was available',
        }

    return {
        'success': True,
        'scoring_method': result['scoring_method'],
        'processing_time': elapsed,
        'model_used': result.get('model_used', 'unknown'),
        'cached': result.get('cached', False),
        'needs_review': bool(result.get('needs_review', False)),
        'data': {
            'score': result['score'],
            'max_score': result.get('max_score', MAX_SCORE),
            'confidence': result.get('confidence', 0.0),
            'feedback': result.get('feedback', ''),
            'strengths': result.get('strengths', []),
            'weaknesses': result.get('weaknesses', []),
        },
    }


# --- Usage tracking ------------------------------------------------------------------------

def record_usage(response) -> None:
    """Log the request for analytics, and emit error.occurred on server-side failures. Never raises."""
    p = g.principal
    try:
        size = response.calculate_content_length()
        if size is None and not response.is_streamed:
            size = len(response.get_data())
        db = SessionLocal()
        try:
            db.add(ApiUsage(
                user_id=p['user_id'],
                api_key_id=p.get('key_id'),
                method=request.method,
                endpoint=request.url_rule.rule if request.url_rule else request.path,
                status_code=response.status_code,
                response_time=round(time.time() - g.start_time, 4),
                request_size=request.content_length or 0,
                response_size=size or 0,
                units=g.get('usage_units', 1),
            ))
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.exception("Could not record API usage")

    if response.status_code >= 500:
        import webhooks
        webhooks.emit(p['user_id'], 'error.occurred', {
            'request_id': g.get('request_id'),
            'method': request.method,
            'endpoint': request.path,
            'status_code': response.status_code,
        })


# --- Routes ------------------------------------------------------------------------------

TEXT_LIMITS = {'answer': 20000, 'marking_guide': 20000, 'question_text': 5000}

SCORE_RULES = {
    'student_answer': {'type': str, 'required': True, 'max_length': TEXT_LIMITS['answer']},
    'marking_guide': {'type': str, 'required': True, 'max_length': TEXT_LIMITS['marking_guide']},
    'question_text': {'type': str, 'max_length': TEXT_LIMITS['question_text']},
    'student_name': {'type': str, 'max_length': 100},
    'matric_number': {'type': str, 'max_length': 50},
    'metadata': {'type': dict},
}

GENERATE_RULES = {
    'subject': {'type': str, 'required': True, 'max_length': 200},
    'topics': {'type': list, 'required': True, 'max_items': 10},
    'level': {'type': str, 'max_length': 100},
    'count': {'type': int, 'required': True, 'min': 1, 'max': 30},
    'question_types': {'type': list, 'required': True, 'max_items': 3},
    'difficulty': {'type': str, 'choices': ['easy', 'medium', 'hard', 'mixed']},
    'instructions': {'type': str, 'max_length': 2000},
    'source_material': {'type': str, 'max_length': 20000},
    'avoid_questions': {'type': list, 'max_items': 100},
}


def generation_spec(body: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Check the list items validate_body cannot, and build the generation spec."""
    from generation import QUESTION_TYPES
    errors: List[Dict[str, Any]] = []

    def strings(field: str, max_length: int) -> List[str]:
        out = []
        for i, item in enumerate(body.get(field) or []):
            if not isinstance(item, str) or not item.strip():
                errors.append({'field': f'{field}[{i}]', 'message': 'Must be a non-empty string', 'type': 'type_error', 'input': item})
            elif len(item.strip()) > max_length:
                errors.append({'field': f'{field}[{i}]', 'message': f'Must be at most {max_length} characters', 'type': 'value_error', 'input': None})
            elif item.strip() not in out:
                out.append(item.strip())
        return out

    topics = strings('topics', 200)
    avoid = strings('avoid_questions', 1000)
    types = strings('question_types', 20)
    for qtype in types:
        if qtype not in QUESTION_TYPES:
            errors.append({'field': 'question_types', 'message': f"Must contain only: {', '.join(QUESTION_TYPES)}",
                           'type': 'value_error', 'input': qtype})
    spec = {
        'subject': body['subject'], 'topics': topics, 'level': body.get('level') or '', 'count': body['count'],
        'question_types': types, 'difficulty': body.get('difficulty') or 'mixed',
        'instructions': body.get('instructions') or '', 'source_material': body.get('source_material') or '',
        'avoid_questions': avoid,
    }
    return spec, errors


def register_api_routes(app):

    @app.before_request
    def before_request():
        g.start_time = time.time()
        g.request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())

    @app.after_request
    def after_request(response):
        for header, value in getattr(g, 'rate_limit_headers', {}).items():
            response.headers[header] = value
        if 'principal' in g:
            record_usage(response)
        response.headers['X-Request-ID'] = g.get('request_id', '')
        if hasattr(g, 'start_time'):
            logger.info(f"Request {g.request_id}: {request.method} {request.path} -> {response.status_code} "
                        f"in {time.time() - g.start_time:.3f}s")
        return response

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop('db', None)
        if db is not None:
            if exc is not None:
                db.rollback()
            db.close()

    @app.errorhandler(404)
    def not_found(_):
        return api_error(404, 'RES_001', 'Endpoint not found')

    @app.errorhandler(405)
    def method_not_allowed(_):
        return api_error(405, 'REQ_001', 'Method not allowed')

    @app.errorhandler(SQLAlchemyError)
    def database_error(e):
        logger.exception(f"Request {g.get('request_id')}: database error")
        if 'db' in g:
            g.db.rollback()
        return api_error(500, 'DB_001', 'A database error occurred')

    @app.errorhandler(Exception)
    def unhandled(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return api_error(e.code or 500, 'HTTP_' + str(e.code), e.description or e.name)
        logger.exception(f"Request {g.get('request_id')}: unhandled error")
        return api_error(500, 'SRV_001', 'Internal server error')

    # --- Service info -------------------------------------------------------------------

    @app.route('/', methods=['GET'])
    def api_root():
        return jsonify({
            'service': 'LexAi-API-SERVICES',
            'version': API_VERSION,
            'description': 'AI-powered Computer-Based Testing API for educational assessment systems',
            'endpoints': {
                'health': '/api/v1/health',
                'questions': '/api/v1/questions',
                'students': '/api/v1/students',
                'responses': '/api/v1/responses',
                'scoring': '/api/v1/score',
                'generate_questions': '/api/v1/generate-questions',
                'submit_response': '/api/v1/submit-response',
                'api_keys': '/api/v1/api-keys',
            },
            'timestamp': now_iso(),
        })

    @app.route('/api/v1/health', methods=['GET'])
    def api_health():
        database_ok = True
        try:
            get_db().execute(text('SELECT 1'))
        except SQLAlchemyError:
            database_ok = False
        return jsonify({
            'status': 'healthy' if database_ok else 'degraded',
            'timestamp': now_iso(),
            'version': API_VERSION,
            'services': {
                'ai_providers': ai_service_manager.get_service_status(),
                'database': database_ok,
                'redis': counter.redis is not None,
            },
        }), 200 if database_ok else 503

    # --- Stateless scoring ----------------------------------------------------------------

    @app.route('/api/v1/score', methods=['POST'])
    @require_auth
    @idempotent
    @validate_body(SCORE_RULES)
    def api_score_answer():
        """Grade one answer against a marking guide (nothing is stored)."""
        import webhooks
        body = g.body
        result = score_answer(body['student_answer'], body['marking_guide'], body.get('question_text', ''))
        if not result['success']:
            return api_error(503, 'SCORE_001', 'The answer could not be graded right now. Retry later.',
                             reason=result['message'])

        payload = {'timestamp': now_iso(), 'request_id': g.request_id, **result}
        if body.get('student_name') or body.get('matric_number'):
            payload['student_info'] = {'name': body.get('student_name'), 'matric_number': body.get('matric_number')}
        if body.get('metadata'):
            payload['metadata'] = body['metadata']
        webhooks.emit(current_user_id(), 'scoring.complete', {
            'request_id': g.request_id, 'score': result['data']['score'], 'max_score': result['data']['max_score'],
            'needs_review': result['needs_review'], 'processing_time': result['processing_time'],
            'metadata': body.get('metadata'),
        })
        return jsonify(payload)

    # --- Question generation ---------------------------------------------------------------

    @app.route('/api/v1/generate-questions', methods=['POST'])
    @require_auth
    @idempotent
    @validate_body(GENERATE_RULES)
    def api_generate_questions():
        """Generate exam questions (MCQ, fill-in-the-blank, theory) with answer keys and marking guides."""
        from generation import GenerationFailed, GenerationUnavailable
        spec, errors = generation_spec(g.body)
        if errors:
            return validation_error(errors)

        started = time.time()
        try:
            result = ai_service_manager.generate_questions(spec)
        except GenerationUnavailable as e:
            logger.warning(f"Request {g.request_id}: question generation unavailable: {e}")
            return api_error(503, 'GEN_001', 'Question generation is unavailable right now', reason=str(e))
        except GenerationFailed as e:
            return api_error(422, 'GEN_002', 'No valid questions could be generated. Try rephrasing the topics or '
                             'instructions, or try again.', reasons=e.reasons)

        generated = len(result['questions'])
        g.usage_units = max(generated, 1)
        # The request itself already used one unit. The questions exist now, so an exhausted
        # quota is not reported here; the next request is refused instead.
        consume_quota(generated - 1)
        return jsonify({
            'success': True,
            'request_id': g.request_id,
            'timestamp': now_iso(),
            'processing_time': round(time.time() - started, 3),
            'model_used': result.get('model_used') or 'unknown',
            'provider': result.get('provider') or 'unknown',
            'data': {
                'requested': result['requested'],
                'generated': generated,
                'warnings': result['warnings'],
                'questions': result['questions'],
            },
        })

    # --- Questions --------------------------------------------------------------------------

    def owned_question(db, question_id: int) -> Optional[Question]:
        return db.query(Question).filter_by(id=question_id, owner_id=current_user_id()).first()

    def owned_student(db, student_id: int) -> Optional[Student]:
        return db.query(Student).filter_by(id=student_id, owner_id=current_user_id()).first()

    def owned_response(db, response_id: int) -> Optional[Response]:
        return db.query(Response).filter_by(id=response_id, owner_id=current_user_id()).first()

    @app.route('/api/v1/questions', methods=['GET'])
    @require_auth
    def api_get_questions():
        db = get_db()
        limit, offset = pagination()
        query = db.query(Question).filter_by(owner_id=current_user_id())
        total = query.count()
        questions = query.order_by(Question.id).offset(offset).limit(limit).all()
        return jsonify({'questions': [question_json(q) for q in questions], 'total_count': total, 'timestamp': now_iso()})

    @app.route('/api/v1/questions', methods=['POST'])
    @require_auth
    @idempotent
    @validate_body({
        'question_text': {'type': str, 'required': True, 'max_length': TEXT_LIMITS['question_text']},
        'marking_guide': {'type': str, 'required': True, 'max_length': TEXT_LIMITS['marking_guide']},
    })
    def api_create_question():
        db = get_db()
        question = Question(owner_id=current_user_id(), **g.body)
        db.add(question)
        db.commit()
        return jsonify({'success': True, 'message': 'Question created successfully', 'question_id': question.id,
                        'question': question_json(question), 'timestamp': now_iso()}), 201

    @app.route('/api/v1/questions/<int:question_id>', methods=['GET'])
    @require_auth
    def api_get_question(question_id):
        question = owned_question(get_db(), question_id)
        if not question:
            return api_error(404, 'RES_001', 'Question not found')
        return jsonify({'question': question_json(question), 'timestamp': now_iso()})

    @app.route('/api/v1/questions/<int:question_id>', methods=['PUT'])
    @require_auth
    @validate_body({
        'question_text': {'type': str, 'max_length': TEXT_LIMITS['question_text']},
        'marking_guide': {'type': str, 'max_length': TEXT_LIMITS['marking_guide']},
    })
    def api_update_question(question_id):
        db = get_db()
        question = owned_question(db, question_id)
        if not question:
            return api_error(404, 'RES_001', 'Question not found')
        for field, value in g.body.items():
            if value:
                setattr(question, field, value)
        db.commit()
        return jsonify({'success': True, 'message': 'Question updated successfully', 'question_id': question_id,
                        'timestamp': now_iso()})

    @app.route('/api/v1/questions/<int:question_id>', methods=['DELETE'])
    @require_auth
    def api_delete_question(question_id):
        db = get_db()
        question = owned_question(db, question_id)
        if not question:
            return api_error(404, 'RES_001', 'Question not found')
        affected = [sid for (sid,) in db.query(Response.student_id).filter_by(question_id=question_id).distinct()]
        db.query(Response).filter_by(question_id=question_id).delete(synchronize_session=False)
        db.delete(question)
        db.flush()
        for student_id in affected:
            recalculate_student_score(db, student_id)
        db.commit()
        return jsonify({'success': True, 'message': 'Question deleted successfully', 'question_id': question_id,
                        'timestamp': now_iso()})

    # --- Students ---------------------------------------------------------------------------

    @app.route('/api/v1/students', methods=['GET'])
    @require_auth
    def api_get_students():
        db = get_db()
        limit, offset = pagination()
        query = db.query(Student).filter_by(owner_id=current_user_id())
        total = query.count()
        students = query.order_by(Student.id).offset(offset).limit(limit).all()
        return jsonify({'students': [student_json(s) for s in students], 'total_count': total, 'timestamp': now_iso()})

    @app.route('/api/v1/students', methods=['POST'])
    @require_auth
    @idempotent
    @validate_body({
        'name': {'type': str, 'required': True, 'max_length': 100},
        'matric_number': {'type': str, 'required': True, 'max_length': 50},
    })
    def api_create_student():
        db = get_db()
        existing = db.query(Student).filter_by(owner_id=current_user_id(), matric_number=g.body['matric_number']).first()
        if existing:
            return jsonify({'success': True, 'message': 'Student already exists', 'student_id': existing.id,
                            'student': student_json(existing), 'timestamp': now_iso()})
        student = Student(owner_id=current_user_id(), name=g.body['name'], matric_number=g.body['matric_number'], score=0.0)
        db.add(student)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return api_error(409, 'RES_002', 'A student with this matric number already exists')
        return jsonify({'success': True, 'message': 'Student created successfully', 'student_id': student.id,
                        'student': student_json(student), 'timestamp': now_iso()}), 201

    @app.route('/api/v1/students/<int:student_id>', methods=['GET'])
    @require_auth
    def api_get_student(student_id):
        student = owned_student(get_db(), student_id)
        if not student:
            return api_error(404, 'RES_001', 'Student not found')
        return jsonify({'student': student_json(student), 'timestamp': now_iso()})

    @app.route('/api/v1/students/<int:student_id>', methods=['PUT'])
    @require_auth
    @validate_body({
        'name': {'type': str, 'max_length': 100},
        'matric_number': {'type': str, 'max_length': 50},
        'score': {'type': float},
    })
    def api_update_student(student_id):
        if 'score' in g.body:
            return api_error(400, 'VAL_001', "A student's score is the sum of their graded responses; update the responses instead")
        db = get_db()
        student = owned_student(db, student_id)
        if not student:
            return api_error(404, 'RES_001', 'Student not found')
        for field, value in g.body.items():
            if value:
                setattr(student, field, value)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return api_error(409, 'RES_002', 'A student with this matric number already exists')
        return jsonify({'success': True, 'message': 'Student updated successfully', 'student_id': student_id,
                        'timestamp': now_iso()})

    @app.route('/api/v1/students/<int:student_id>', methods=['DELETE'])
    @require_auth
    def api_delete_student(student_id):
        db = get_db()
        student = owned_student(db, student_id)
        if not student:
            return api_error(404, 'RES_001', 'Student not found')
        db.query(Response).filter_by(student_id=student_id).delete(synchronize_session=False)
        db.delete(student)
        db.commit()
        return jsonify({'success': True, 'message': 'Student deleted successfully', 'student_id': student_id,
                        'timestamp': now_iso()})

    # --- Responses --------------------------------------------------------------------------

    @app.route('/api/v1/responses', methods=['GET'])
    @require_auth
    def api_get_responses():
        db = get_db()
        limit, offset = pagination()
        query = db.query(Response).filter_by(owner_id=current_user_id())
        for param in ('student_id', 'question_id'):
            value = request.args.get(param, type=int)
            if value is not None:
                query = query.filter(getattr(Response, param) == value)
        status = request.args.get('grading_status')
        if status:
            query = query.filter(Response.grading_status == status)
        total = query.count()
        responses = query.order_by(Response.id).offset(offset).limit(limit).all()
        return jsonify({'responses': [response_json(r) for r in responses], 'total_count': total, 'timestamp': now_iso()})

    @app.route('/api/v1/responses', methods=['POST'])
    @require_auth
    @idempotent
    @validate_body({
        'student_id': {'type': int, 'required': True, 'min': 1},
        'question_id': {'type': int, 'required': True, 'min': 1},
        'answer': {'type': str, 'required': True, 'max_length': TEXT_LIMITS['answer']},
    })
    def api_create_response():
        """Store an answer without grading it. It counts towards the total once a score is set."""
        db = get_db()
        if not owned_student(db, g.body['student_id']):
            return api_error(404, 'RES_001', 'Student not found')
        if not owned_question(db, g.body['question_id']):
            return api_error(404, 'RES_001', 'Question not found')
        response = Response(owner_id=current_user_id(), grading_status=NEEDS_REVIEW, score=0.0,
                            max_score=MAX_SCORE, scoring_method='manual', **g.body)
        db.add(response)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return api_error(409, 'RES_003', 'This student already has a response for this question')
        return jsonify({'success': True, 'message': 'Response created successfully', 'response_id': response.id,
                        'timestamp': now_iso()}), 201

    @app.route('/api/v1/responses/<int:response_id>', methods=['GET'])
    @require_auth
    def api_get_response(response_id):
        response = owned_response(get_db(), response_id)
        if not response:
            return api_error(404, 'RES_001', 'Response not found')
        return jsonify({'response': response_json(response), 'timestamp': now_iso()})

    @app.route('/api/v1/responses/<int:response_id>', methods=['PUT'])
    @require_auth
    @validate_body({
        'answer': {'type': str, 'max_length': TEXT_LIMITS['answer']},
        'score': {'type': float, 'min': 0},
        'admin_comments': {'type': str, 'max_length': 5000},
        'student_id': {'type': int},
        'question_id': {'type': int},
    })
    def api_update_response(response_id):
        body = g.body
        if 'student_id' in body or 'question_id' in body:
            return api_error(400, 'VAL_001', 'A response cannot be moved to another student or question; delete it and submit again')
        db = get_db()
        response = owned_response(db, response_id)
        if not response:
            return api_error(404, 'RES_001', 'Response not found')

        if body.get('answer') and body['answer'] != response.answer:
            response.answer = body['answer']
            # The previous grade was for different text.
            response.grading_status = NEEDS_REVIEW
        if 'score' in body:
            if body['score'] > (response.max_score or MAX_SCORE):
                return api_error(400, 'VAL_001', f"Score must be at most {response.max_score or MAX_SCORE}")
            response.lecturer_score = body['score']
            response.final_score = body['score']
            response.grading_status = GRADED
            response.admin_approved = True
        if 'admin_comments' in body:
            response.admin_comments = body['admin_comments']

        db.flush()
        recalculate_student_score(db, response.student_id)
        db.commit()
        return jsonify({'success': True, 'message': 'Response updated successfully', 'response_id': response_id,
                        'response': response_json(response), 'timestamp': now_iso()})

    @app.route('/api/v1/responses/<int:response_id>', methods=['DELETE'])
    @require_auth
    def api_delete_response(response_id):
        db = get_db()
        response = owned_response(db, response_id)
        if not response:
            return api_error(404, 'RES_001', 'Response not found')
        student_id = response.student_id
        db.delete(response)
        db.flush()
        recalculate_student_score(db, student_id)
        db.commit()
        return jsonify({'success': True, 'message': 'Response deleted successfully', 'response_id': response_id,
                        'timestamp': now_iso()})

    @app.route('/api/v1/submit-response', methods=['POST'])
    @require_auth
    @idempotent
    @validate_body({
        'student_id': {'type': int, 'required': True, 'min': 1},
        'question_id': {'type': int, 'required': True, 'min': 1},
        'answer': {'type': str, 'required': True, 'max_length': TEXT_LIMITS['answer']},
    })
    def api_submit_response():
        """Grade an answer and store it. One submission per student per question."""
        body = g.body
        db = get_db()
        student = owned_student(db, body['student_id'])
        if not student:
            return api_error(404, 'RES_001', 'Student not found')
        question = owned_question(db, body['question_id'])
        if not question:
            return api_error(404, 'RES_001', 'Question not found')

        existing = db.query(Response.id).filter_by(student_id=student.id, question_id=question.id).first()
        if existing:
            return api_error(409, 'RES_003', 'This student already submitted an answer to this question',
                             response_id=existing.id)

        result = score_answer(body['answer'], question.marking_guide, question.question_text)
        if not result['success']:
            # Nothing is stored, so the client can safely retry.
            return api_error(503, 'SCORE_001', 'The answer could not be graded right now. Nothing was saved; retry later.',
                             reason=result['message'])

        data = result['data']
        status = NEEDS_REVIEW if result['needs_review'] else GRADED
        response = Response(
            owner_id=current_user_id(),
            student_id=student.id,
            question_id=question.id,
            answer=body['answer'],
            score=data['score'],
            max_score=data['max_score'],
            ai_score=data['score'],
            grading_status=status,
            scoring_method=result['scoring_method'],
            ai_feedback=data['feedback'],
            ai_confidence=data['confidence'],
            ai_strengths='; '.join(data['strengths']),
            ai_weaknesses='; '.join(data['weaknesses']),
            is_processed=True,
        )
        db.add(response)
        try:
            db.flush()
            total = recalculate_student_score(db, student.id)
            db.commit()
        except IntegrityError:
            # A concurrent request for the same student/question won the race.
            db.rollback()
            return api_error(409, 'RES_003', 'This student already submitted an answer to this question')

        import webhooks
        webhooks.emit(current_user_id(), 'scoring.complete', {
            'request_id': g.request_id, 'response_id': response.id, 'student_id': student.id,
            'question_id': question.id, 'score': data['score'], 'max_score': data['max_score'],
            'grading_status': status, 'processing_time': result['processing_time'],
        })
        return jsonify({
            'success': True,
            'message': 'Response submitted and scored successfully' if status == GRADED
                       else 'Response submitted; the grade needs lecturer review before it counts',
            'response_id': response.id,
            'grading_status': status,
            'scoring': {
                'score': data['score'],
                'max_score': data['max_score'],
                'feedback': data['feedback'],
                'confidence': data['confidence'],
                'strengths': response.ai_strengths,
                'weaknesses': response.ai_weaknesses,
                'method': result['scoring_method'],
                'needs_review': result['needs_review'],
            },
            'student_total_score': total,
            'timestamp': now_iso(),
        }), 201

    @app.route('/api/v1/student/<int:student_id>/responses', methods=['GET'])
    @require_auth
    def api_get_student_responses(student_id):
        db = get_db()
        student = owned_student(db, student_id)
        if not student:
            return api_error(404, 'RES_001', 'Student not found')
        rows = (db.query(Response, Question)
                .join(Question, Response.question_id == Question.id)
                .filter(Response.student_id == student_id, Response.owner_id == current_user_id())
                .order_by(Response.id)
                .all())
        items = [{
            'response_id': r.id,
            'question': {'id': q.id, 'text': q.question_text, 'marking_guide': q.marking_guide},
            'answer': r.answer,
            'score': effective_score(r),
            'max_score': r.max_score,
            'grading_status': r.grading_status,
            'ai_score': r.ai_score,
            'ai_feedback': r.ai_feedback,
            'ai_confidence': r.ai_confidence,
            'ai_strengths': r.ai_strengths,
            'ai_weaknesses': r.ai_weaknesses,
            'submitted_at': _iso(r.created_at),
        } for r, q in rows]
        return jsonify({
            'student': {'id': student.id, 'name': student.name, 'matric_number': student.matric_number,
                        'total_score': student.score or 0.0},
            'responses': items,
            'total_responses': len(items),
            'timestamp': now_iso(),
        })

    # --- API keys -----------------------------------------------------------------------------

    @app.route('/api/v1/api-keys', methods=['GET'])
    @require_session
    def api_get_api_keys():
        keys = get_db().query(APIKey).filter_by(user_id=current_user_id()).order_by(APIKey.id).all()
        return jsonify({'api_keys': [api_key_json(k) for k in keys], 'total_count': len(keys), 'timestamp': now_iso()})

    @app.route('/api/v1/api-keys', methods=['POST'])
    @require_session
    @idempotent
    @validate_body({
        'key_name': {'type': str, 'required': True, 'max_length': 100},
        'plan_type': {'type': str, 'choices': tuple(PLAN_LIMITS)},
        'rate_limit': {'type': int, 'min': 1},
        'monthly_quota': {'type': int, 'min': 1},
        # Accepted for backward compatibility and ignored: keys always belong to the caller.
        'email': {'type': str, 'max_length': 120},
    })
    def api_create_api_key():
        body = g.body
        plan = body.get('plan_type', 'production')
        caps = PLAN_LIMITS[plan]
        rate_limit = body.get('rate_limit', caps['rate_limit'])
        monthly_quota = body.get('monthly_quota', caps['monthly_quota'])
        for field, value in (('rate_limit', rate_limit), ('monthly_quota', monthly_quota)):
            if value > caps[field]:
                return api_error(400, 'VAL_001', f"{field} cannot exceed {caps[field]} on the {plan} plan")

        db = get_db()
        active = db.query(APIKey).filter_by(user_id=current_user_id(), is_active=True).count()
        if active >= MAX_ACTIVE_KEYS:
            return api_error(400, 'VAL_001', f'You can have at most {MAX_ACTIVE_KEYS} active API keys; revoke one first')

        key, plaintext = new_api_key(db, current_user_id(), body['key_name'], plan, rate_limit, monthly_quota)
        db.commit()
        return jsonify({
            'success': True,
            'message': 'API key created. Copy it now; it will not be shown again.',
            'api_key': {**api_key_json(key), 'api_key': plaintext},
            'timestamp': now_iso(),
        }), 201

    @app.route('/api/v1/api-keys/<int:key_id>', methods=['DELETE'])
    @require_session
    def api_revoke_api_key(key_id):
        db = get_db()
        key = db.query(APIKey).filter_by(id=key_id, user_id=current_user_id()).first()
        if not key:
            return api_error(404, 'RES_001', 'API key not found')
        key.is_active = False
        db.commit()
        import webhooks
        webhooks.emit(current_user_id(), 'api_key.revoked', {'api_key_id': key_id, 'key_name': key.key_name})
        return jsonify({'success': True, 'message': 'API key revoked successfully', 'api_key_id': key_id,
                        'timestamp': now_iso()})

    @app.route('/api/v1/api-keys/<int:key_id>/rotate', methods=['POST'])
    @require_session
    @idempotent
    @validate_body({'key_name': {'type': str, 'max_length': 100}}, allow_empty=True)
    def api_rotate_api_key(key_id):
        db = get_db()
        old = db.query(APIKey).filter_by(id=key_id, user_id=current_user_id(), is_active=True).first()
        if not old:
            return api_error(404, 'RES_001', 'Active API key not found')
        old.is_active = False
        name = g.body.get('key_name') or old.key_name
        key, plaintext = new_api_key(db, current_user_id(), name, old.plan_type, old.rate_limit, old.monthly_quota)
        db.flush()  # assigns key.id
        # IP rules follow the key to its replacement.
        for rule in db.query(IPRule).filter_by(api_key_id=old.id).all():
            db.add(IPRule(api_key_id=key.id, ip_address=rule.ip_address, is_whitelist=rule.is_whitelist))
        db.commit()
        import webhooks
        webhooks.emit(current_user_id(), 'api_key.rotated', {'old_key_id': old.id, 'new_key_id': key.id, 'key_name': name})
        return jsonify({
            'success': True,
            'message': 'API key rotated. Copy the new key now; it will not be shown again.',
            'old_key_id': old.id,
            'new_key_id': key.id,
            'new_api_key': plaintext,
            'key_name': name,
            'timestamp': now_iso(),
        })

    # --- Accounts -----------------------------------------------------------------------------

    def password_problems(password: str) -> List[str]:
        problems = []
        if len(password) < 8:
            problems.append('at least 8 characters')
        if len(password) > 128:
            problems.append('at most 128 characters')
        if not re.search(r'[A-Z]', password):
            problems.append('an uppercase letter')
        if not re.search(r'[a-z]', password):
            problems.append('a lowercase letter')
        if not re.search(r'[0-9]', password):
            problems.append('a number')
        if not re.search(r'[^A-Za-z0-9]', password):
            problems.append('a special character')
        return problems

    @app.route('/api/v1/register', methods=['POST'])
    @limit_by_ip('register', REGISTRATIONS, 3600)
    @validate_body({
        'email': {'type': str, 'required': True, 'max_length': 120},
        'password': {'type': str, 'required': True, 'max_length': 256},
    })
    def api_register():
        email = g.body['email'].lower()
        password = request.get_json(silent=True)['password']  # unstripped
        if not EMAIL_RE.match(email):
            return api_error(400, 'VAL_001', 'Validation failed: email is not a valid address',
                             validation_errors=[{'field': 'email', 'message': 'Invalid email address', 'type': 'value_error'}])
        problems = password_problems(password)
        if problems:
            message = 'Password must contain ' + ', '.join(problems)
            return api_error(400, 'VAL_001', f'Validation failed: {message}',
                             validation_errors=[{'field': 'password', 'message': message, 'type': 'value_error'}])

        db = get_db()
        if db.query(User.id).filter_by(email=email).first():
            return api_error(409, 'RES_002', 'A user with this email already exists')
        user = User(email=email, password_hash=hash_password(password))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return api_error(409, 'RES_002', 'A user with this email already exists')
        return jsonify({'success': True, 'message': 'User registered successfully',
                        'user': {'id': user.id, 'email': user.email, 'created_at': _iso(user.created_at)},
                        'timestamp': now_iso()}), 201

    @app.route('/api/v1/login', methods=['POST'])
    @limit_by_ip('login', LOGIN_ATTEMPTS, 900)
    @validate_body({
        'email': {'type': str, 'required': True, 'max_length': 120},
        'password': {'type': str, 'required': True, 'max_length': 256},
    })
    def api_login():
        email = g.body['email'].lower()
        password = request.get_json(silent=True)['password']
        db = get_db()
        user = db.query(User).filter_by(email=email).first()
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            return api_error(401, 'AUTH_004', 'Invalid email or password')

        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS)
        db.add(AuthToken(token=hash_secret(token), user_id=user.id, expires_at=expires_at))
        db.commit()
        return jsonify({'success': True, 'message': 'Login successful', 'token': token,
                        'expires_at': expires_at.isoformat(),
                        'user': {'id': user.id, 'email': user.email, 'created_at': _iso(user.created_at)},
                        'timestamp': now_iso()})

    @app.route('/api/v1/logout', methods=['POST'])
    @require_session
    def api_logout():
        db = get_db()
        db.query(AuthToken).filter_by(id=g.principal['token_id']).update({AuthToken.is_active: False})
        db.commit()
        return jsonify({'success': True, 'message': 'Logout successful', 'timestamp': now_iso()})

    # --- Platform features (separate modules) --------------------------------------------------
    from analytics import register_analytics_routes
    from batch import register_batch_routes
    from data_ops import register_data_routes
    from ip_rules import register_ip_rule_routes
    from meta import register_meta_routes
    from webhooks import register_webhook_routes

    register_analytics_routes(app)
    register_batch_routes(app)
    register_data_routes(app)
    register_ip_rule_routes(app)
    register_meta_routes(app)
    register_webhook_routes(app)
