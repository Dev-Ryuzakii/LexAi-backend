"""
Webhooks: subscriptions and signed, retried deliveries.

Each delivery is a POST with a JSON body {id, event, timestamp, data} and headers
  X-LexAi-Event, X-LexAi-Delivery, X-LexAi-Timestamp,
  X-LexAi-Signature: sha256=HMAC_SHA256(secret, "<timestamp>.<body>")
Receivers should recompute the signature and reject stale timestamps.

Deliveries run on a small thread pool, are retried with jittered exponential backoff on
network errors, 429 and 5xx, and never follow redirects. Targets that resolve to private,
loopback or link-local addresses are refused unless WEBHOOK_ALLOW_PRIVATE=1 (prevents
using webhooks to reach internal services).
"""
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict
from urllib.parse import urlparse

import requests
from flask import g, jsonify

from database import SessionLocal, Webhook
from resilience import retry_call

logger = logging.getLogger(__name__)

EVENTS = ('scoring.complete', 'quota.warning', 'quota.exceeded', 'api_key.rotated', 'api_key.revoked', 'error.occurred')
MAX_WEBHOOKS_PER_USER = 10
DELIVERY_ATTEMPTS = int(os.environ.get('WEBHOOK_DELIVERY_ATTEMPTS', '4'))
DELIVERY_TIMEOUT = float(os.environ.get('WEBHOOK_TIMEOUT_SECONDS', '5'))

_executor = ThreadPoolExecutor(max_workers=int(os.environ.get('WEBHOOK_WORKERS', '4')), thread_name_prefix='webhook')


def _allow_private() -> bool:
    return os.environ.get('WEBHOOK_ALLOW_PRIVATE', '0').lower() in ('1', 'true', 'yes')


class UnsafeTarget(Exception):
    pass


def check_target(url: str) -> None:
    """Raise UnsafeTarget unless url is http(s) and resolves only to public addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname:
        raise UnsafeTarget('URL must be http(s) with a host')
    if parsed.scheme == 'http' and not _allow_private():
        raise UnsafeTarget('Webhook URLs must use https')
    if _allow_private():
        return
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except socket.gaierror as e:
        raise UnsafeTarget(f'Host does not resolve: {e}')
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise UnsafeTarget('URL resolves to a private or reserved address')


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return 'sha256=' + hmac.new(secret.encode(), timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()


def _submit(fn, *args) -> None:
    """Indirection so tests can run deliveries synchronously."""
    _executor.submit(fn, *args)


def _deliver(webhook_id: int, url: str, secret: str, event: str, data: Dict[str, Any]) -> None:
    delivery_id = str(uuid.uuid4())
    body = json.dumps({'id': delivery_id, 'event': event, 'timestamp': datetime.utcnow().isoformat() + 'Z',
                       'data': data}, default=str).encode()

    def attempt():
        check_target(url)  # re-checked per attempt: DNS can change after the webhook was saved
        ts = str(int(time.time()))
        response = requests.post(url, data=body, timeout=DELIVERY_TIMEOUT, allow_redirects=False, headers={
            'Content-Type': 'application/json',
            'User-Agent': 'LexAi-Webhooks/1.0',
            'X-LexAi-Event': event,
            'X-LexAi-Delivery': delivery_id,
            'X-LexAi-Timestamp': ts,
            'X-LexAi-Signature': sign(secret, ts, body),
        })
        if response.status_code == 429 or response.status_code >= 500:
            raise requests.exceptions.HTTPError(f'HTTP {response.status_code}', response=response)
        return response.status_code

    try:
        status = str(retry_call(attempt, attempts=DELIVERY_ATTEMPTS, base=1.0, cap=60.0,
                                retry_on=(requests.exceptions.RequestException,), label=f'webhook {webhook_id}'))
    except UnsafeTarget as e:
        status = f'blocked: {e}'[:50]
    except Exception as e:
        status = f'failed: {type(e).__name__}'[:50]
    logger.info(f"Webhook {webhook_id} {event} delivery {delivery_id}: {status}")

    db = SessionLocal()
    try:
        db.query(Webhook).filter_by(id=webhook_id).update(
            {Webhook.last_delivery_at: datetime.utcnow(), Webhook.last_status: status})
        db.commit()
    except Exception:
        logger.exception('Could not record webhook delivery status')
    finally:
        db.close()


def emit(user_id: int, event: str, data: Dict[str, Any]) -> None:
    """Queue `event` for every active webhook of `user_id` subscribed to it. Never raises."""
    try:
        db = SessionLocal()
        try:
            hooks = db.query(Webhook).filter_by(user_id=user_id, is_active=True).all()
            targets = [(h.id, h.url, h.secret) for h in hooks if event in json.loads(h.events)]
        finally:
            db.close()
        for webhook_id, url, secret in targets:
            _submit(_deliver, webhook_id, url, secret, event, data)
    except Exception:
        logger.exception(f'Could not queue webhook event {event}')


def webhook_json(h: Webhook) -> Dict[str, Any]:
    return {
        'id': h.id, 'url': h.url, 'events': json.loads(h.events), 'is_active': h.is_active,
        'last_delivery_at': h.last_delivery_at.isoformat() if h.last_delivery_at else None,
        'last_status': h.last_status, 'created_at': h.created_at.isoformat() if h.created_at else None,
    }


def register_webhook_routes(app):
    from api_service import api_error, current_user_id, get_db, idempotent, now_iso, require_auth, validate_body

    @app.route('/api/v1/webhooks', methods=['GET'])
    @require_auth
    def api_list_webhooks():
        """List your webhooks."""
        hooks = get_db().query(Webhook).filter_by(user_id=current_user_id()).order_by(Webhook.id).all()
        return jsonify({'webhooks': [webhook_json(h) for h in hooks], 'total_count': len(hooks),
                        'timestamp': now_iso(), 'request_id': g.request_id})

    @app.route('/api/v1/webhooks', methods=['POST'])
    @require_auth
    @idempotent
    @validate_body({
        'url': {'type': str, 'required': True, 'max_length': 2000},
        'events': {'type': list, 'required': True, 'max_items': len(EVENTS)},
        'secret': {'type': str, 'max_length': 100},
    })
    def api_create_webhook():
        """Subscribe a URL to events. The signing secret is returned only in this response."""
        body = g.body
        unknown = [e for e in body['events'] if e not in EVENTS]
        if unknown or not all(isinstance(e, str) for e in body['events']):
            return api_error(400, 'VAL_001', f"Unknown events: {unknown}. Valid events: {', '.join(EVENTS)}")
        try:
            check_target(body['url'])
        except UnsafeTarget as e:
            return api_error(400, 'VAL_001', f'Webhook URL rejected: {e}')
        if body.get('secret') and len(body['secret']) < 16:
            return api_error(400, 'VAL_001', 'secret must be at least 16 characters (or omit it to generate one)')

        db = get_db()
        if db.query(Webhook).filter_by(user_id=current_user_id(), is_active=True).count() >= MAX_WEBHOOKS_PER_USER:
            return api_error(400, 'VAL_001', f'You can have at most {MAX_WEBHOOKS_PER_USER} webhooks')
        secret = body.get('secret') or f'whsec_{secrets.token_urlsafe(24)}'
        hook = Webhook(user_id=current_user_id(), url=body['url'], events=json.dumps(sorted(set(body['events']))),
                       secret=secret, is_active=True)
        db.add(hook)
        db.commit()
        return jsonify({'success': True, 'message': 'Webhook created. Store the signing secret now; it is not shown again.',
                        'webhook': {**webhook_json(hook), 'secret': secret},
                        'timestamp': now_iso(), 'request_id': g.request_id}), 201

    @app.route('/api/v1/webhooks/<int:webhook_id>', methods=['DELETE'])
    @require_auth
    def api_delete_webhook(webhook_id):
        """Delete a webhook."""
        db = get_db()
        hook = db.query(Webhook).filter_by(id=webhook_id, user_id=current_user_id()).first()
        if not hook:
            return api_error(404, 'RES_001', 'Webhook not found')
        db.delete(hook)
        db.commit()
        return jsonify({'success': True, 'message': 'Webhook deleted', 'webhook_id': webhook_id,
                        'timestamp': now_iso(), 'request_id': g.request_id})
