"""
Batch scoring (up to 100 answers) and background jobs.

POST /score/batch grades answers in parallel and returns all results. With ?async=true it
returns 202 and a job id at once; poll GET /jobs/{id} for the result. Each answer counts
as one unit against the monthly quota.
"""
import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List

from flask import g, jsonify, request

from database import Job, SessionLocal

logger = logging.getLogger(__name__)

BATCH_MAX = 100
BATCH_CONCURRENCY = int(os.environ.get('BATCH_CONCURRENCY', '4'))
_job_executor = ThreadPoolExecutor(max_workers=int(os.environ.get('JOB_WORKERS', '2')), thread_name_prefix='job')


def _submit_job(fn, *args) -> None:
    """Indirection so tests can run jobs synchronously."""
    _job_executor.submit(fn, *args)


def run_batch(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Grade validated items ({index, body} or {index, error}) and build the batch result."""
    from api_service import score_answer

    def grade(item):
        if 'error' in item:
            return {'index': item['index'], 'success': False, 'error': item['error']}
        body = item['body']
        result = score_answer(body['student_answer'], body['marking_guide'], body.get('question_text', ''))
        out: Dict[str, Any] = {'index': item['index'], 'success': result['success']}
        if result['success']:
            out.update(data=result['data'], scoring_method=result['scoring_method'],
                       processing_time=result['processing_time'], needs_review=result['needs_review'])
        else:
            out['error'] = result['message']
        if body.get('student_name') or body.get('matric_number'):
            out['student_info'] = {'name': body.get('student_name'), 'matric_number': body.get('matric_number')}
        if body.get('metadata'):
            out['metadata'] = body['metadata']
        return out

    with ThreadPoolExecutor(max_workers=BATCH_CONCURRENCY) as pool:
        results = list(pool.map(grade, items))
    processed = sum(1 for r in results if r['success'])
    return {
        'success': processed == len(results),
        'total': len(results),
        'processed': processed,
        'failed': len(results) - processed,
        'results': results,
    }


def _run_job(job_id: str, user_id: int, items: List[Dict[str, Any]]) -> None:
    import webhooks
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        job.status, job.started_at = 'started', datetime.utcnow()
        db.commit()
        try:
            result = run_batch(items)
            job.status, job.result = 'finished', json.dumps(result)
        except Exception as e:
            logger.exception(f'Job {job_id} failed')
            job.status, job.error = 'failed', str(e)[:2000]
        job.ended_at = datetime.utcnow()
        db.commit()
        webhooks.emit(user_id, 'scoring.complete', {'job_id': job_id, 'status': job.status, 'batch': True})
    finally:
        db.close()


def job_json(job: Job) -> Dict[str, Any]:
    return {
        'id': job.id, 'type': job.type, 'status': job.status,
        'result': json.loads(job.result) if job.result else None, 'error': job.error,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'ended_at': job.ended_at.isoformat() if job.ended_at else None,
    }


def register_batch_routes(app):
    from api_service import (SCORE_RULES, api_error, consume_quota, current_user_id, get_db, idempotent, now_iso,
                             require_auth, validate_body, validate_fields)

    @app.route('/api/v1/score/batch', methods=['POST'])
    @require_auth
    @idempotent
    @validate_body({'answers': {'type': list, 'required': True, 'max_items': BATCH_MAX}})
    def api_score_batch():
        """Grade up to 100 answers. Add ?async=true to run as a background job."""
        import webhooks
        items = []
        for index, raw in enumerate(g.body['answers']):
            if not isinstance(raw, dict):
                items.append({'index': index, 'error': 'Each answer must be an object'})
                continue
            cleaned, errors = validate_fields(raw, SCORE_RULES)
            if errors:
                items.append({'index': index, 'error': '; '.join(f"{e['field']}: {e['message']}" for e in errors)})
            else:
                items.append({'index': index, 'body': cleaned})

        gradable = sum(1 for i in items if 'body' in i)
        g.usage_units = max(gradable, 1)
        exhausted = consume_quota(gradable - 1)  # the request itself already used one unit
        if exhausted:
            return exhausted

        if request.args.get('async', '').lower() in ('1', 'true', 'yes'):
            job = Job(id=str(uuid.uuid4()), user_id=current_user_id(), type='score_batch', status='queued')
            db = get_db()
            db.add(job)
            db.commit()
            _submit_job(_run_job, job.id, current_user_id(), items)
            return jsonify({'success': True, 'job_id': job.id, 'status': 'queued',
                            'status_url': f'/api/v1/jobs/{job.id}', 'timestamp': now_iso(),
                            'request_id': g.request_id}), 202

        started = time.time()
        result = run_batch(items)
        webhooks.emit(current_user_id(), 'scoring.complete', {
            'request_id': g.request_id, 'batch': True, 'total': result['total'], 'processed': result['processed'],
            'failed': result['failed'], 'processing_time': round(time.time() - started, 3)})
        return jsonify({**result, 'timestamp': now_iso(), 'request_id': g.request_id})

    @app.route('/api/v1/jobs/<job_id>', methods=['GET'])
    @require_auth
    def api_get_job(job_id):
        """Status and result of a background job."""
        job = get_db().query(Job).filter_by(id=job_id, user_id=current_user_id()).first()
        if not job:
            return api_error(404, 'RES_001', 'Job not found')
        return jsonify({'job': job_json(job), 'timestamp': now_iso()})
