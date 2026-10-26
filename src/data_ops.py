"""
Bulk create/update/delete, CSV/JSON upload and CSV/JSON export for the caller's records.

Bulk operations validate every item, apply the valid ones in one transaction, and report
per-item failures by index instead of rejecting the whole request.
"""
import csv
import io
import json
from typing import Any, Dict, List, Tuple

from flask import g, jsonify, request

from analytics import file_response
from database import Question, Response, Student, effective_score, recalculate_student_score

BULK_MAX = 500
UPLOAD_MAX_ROWS = 1000


def _result(total: int) -> Dict[str, Any]:
    return {'success': True, 'total': total, 'failed': 0, 'failed_indices': [], 'errors': []}


def _fail(result: Dict[str, Any], index: int, message: str) -> None:
    result['failed'] += 1
    result['failed_indices'].append(index)
    result['errors'].append(f'Item {index}: {message}')
    result['success'] = False


def _read_upload() -> Tuple[List[Dict[str, Any]], str]:
    """Parse an uploaded .csv or .json file into a list of row dicts. Returns (rows, error)."""
    upload = request.files.get('file')
    if upload is None or not upload.filename:
        return [], 'Upload a file in the "file" form field'
    name = upload.filename.lower()
    try:
        text = upload.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        return [], 'File must be UTF-8 encoded'
    if name.endswith('.json'):
        try:
            rows = json.loads(text)
        except json.JSONDecodeError as e:
            return [], f'Invalid JSON: {e}'
        if isinstance(rows, dict):
            rows = rows.get('questions') or rows.get('students') or []
        if not isinstance(rows, list):
            return [], 'JSON file must contain a list of objects'
    elif name.endswith('.csv'):
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        return [], 'Only .csv and .json files are supported'
    if len(rows) > UPLOAD_MAX_ROWS:
        return [], f'File has {len(rows)} rows; the limit is {UPLOAD_MAX_ROWS}'
    return rows, ''


def register_data_routes(app):
    from api_service import (TEXT_LIMITS, api_error, current_user_id, get_db, idempotent, now_iso, question_json,
                             require_auth, student_json, response_json, validate_body, validate_fields)

    question_rules = {
        'question_text': {'type': str, 'required': True, 'max_length': TEXT_LIMITS['question_text']},
        'marking_guide': {'type': str, 'required': True, 'max_length': TEXT_LIMITS['marking_guide']},
    }
    student_rules = {
        'name': {'type': str, 'required': True, 'max_length': 100},
        'matric_number': {'type': str, 'required': True, 'max_length': 50},
    }

    def create_questions(items: List[Any]) -> Dict[str, Any]:
        db = get_db()
        result = {**_result(len(items)), 'created': 0, 'created_indices': [], 'created_ids': []}
        created = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                _fail(result, index, 'must be an object')
                continue
            cleaned, errors = validate_fields(item, question_rules)
            if errors:
                _fail(result, index, '; '.join(f"{e['field']}: {e['message']}" for e in errors))
                continue
            question = Question(owner_id=current_user_id(), **cleaned)
            db.add(question)
            created.append((index, question))
        db.commit()
        for index, question in created:
            result['created'] += 1
            result['created_indices'].append(index)
            result['created_ids'].append(question.id)
        return result

    def create_students(items: List[Any]) -> Dict[str, Any]:
        db = get_db()
        result = {**_result(len(items)), 'created': 0, 'created_indices': [], 'created_ids': []}
        existing = {m for (m,) in db.query(Student.matric_number).filter_by(owner_id=current_user_id())}
        created = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                _fail(result, index, 'must be an object')
                continue
            cleaned, errors = validate_fields(item, student_rules)
            if errors:
                _fail(result, index, '; '.join(f"{e['field']}: {e['message']}" for e in errors))
                continue
            if cleaned['matric_number'] in existing:
                _fail(result, index, f"matric number {cleaned['matric_number']} already exists")
                continue
            existing.add(cleaned['matric_number'])
            student = Student(owner_id=current_user_id(), score=0.0, **cleaned)
            db.add(student)
            created.append((index, student))
        db.commit()
        for index, student in created:
            result['created'] += 1
            result['created_indices'].append(index)
            result['created_ids'].append(student.id)
        return result

    # --- Bulk -------------------------------------------------------------------------

    @app.route('/api/v1/bulk/questions', methods=['POST'])
    @require_auth
    @idempotent
    @validate_body({'questions': {'type': list, 'required': True, 'max_items': BULK_MAX}})
    def api_bulk_create_questions():
        """Create up to 500 questions."""
        return jsonify({'success': True, 'result': create_questions(g.body['questions']), 'timestamp': now_iso()})

    @app.route('/api/v1/bulk/students', methods=['POST'])
    @require_auth
    @idempotent
    @validate_body({'students': {'type': list, 'required': True, 'max_items': BULK_MAX}})
    def api_bulk_create_students():
        """Create up to 500 students. Existing matric numbers are reported as failures."""
        return jsonify({'success': True, 'result': create_students(g.body['students']), 'timestamp': now_iso()})

    @app.route('/api/v1/bulk/questions/update', methods=['PUT'])
    @require_auth
    @validate_body({'updates': {'type': list, 'required': True, 'max_items': BULK_MAX}})
    def api_bulk_update_questions():
        """Update up to 500 questions by id."""
        db = get_db()
        items = g.body['updates']
        result = {**_result(len(items)), 'updated': 0, 'updated_indices': []}
        rules = {'id': {'type': int, 'required': True, 'min': 1},
                 'question_text': {'type': str, 'max_length': TEXT_LIMITS['question_text']},
                 'marking_guide': {'type': str, 'max_length': TEXT_LIMITS['marking_guide']}}
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                _fail(result, index, 'must be an object')
                continue
            cleaned, errors = validate_fields(item, rules)
            if errors:
                _fail(result, index, '; '.join(f"{e['field']}: {e['message']}" for e in errors))
                continue
            question = db.query(Question).filter_by(id=cleaned['id'], owner_id=current_user_id()).first()
            if not question:
                _fail(result, index, f"question {cleaned['id']} not found")
                continue
            for field in ('question_text', 'marking_guide'):
                if cleaned.get(field):
                    setattr(question, field, cleaned[field])
            result['updated'] += 1
            result['updated_indices'].append(index)
        db.commit()
        return jsonify({'success': True, 'result': result, 'timestamp': now_iso()})

    @app.route('/api/v1/bulk/questions/delete', methods=['POST'])
    @require_auth
    @validate_body({'question_ids': {'type': list, 'required': True, 'max_items': BULK_MAX}})
    def api_bulk_delete_questions():
        """Delete up to 500 questions (and their responses) by id."""
        db = get_db()
        ids = g.body['question_ids']
        result = {**_result(len(ids)), 'deleted': 0, 'deleted_ids': [], 'failed_ids': []}
        affected_students = set()
        for index, qid in enumerate(ids):
            if isinstance(qid, bool) or not isinstance(qid, int):
                _fail(result, index, 'id must be a whole number')
                result['failed_ids'].append(qid)
                continue
            question = db.query(Question).filter_by(id=qid, owner_id=current_user_id()).first()
            if not question:
                _fail(result, index, f'question {qid} not found')
                result['failed_ids'].append(qid)
                continue
            affected_students.update(s for (s,) in db.query(Response.student_id).filter_by(question_id=qid))
            db.query(Response).filter_by(question_id=qid).delete(synchronize_session=False)
            db.delete(question)
            result['deleted'] += 1
            result['deleted_ids'].append(qid)
        db.flush()
        for student_id in affected_students:
            recalculate_student_score(db, student_id)
        db.commit()
        return jsonify({'success': True, 'result': result, 'timestamp': now_iso()})

    # --- Upload -------------------------------------------------------------------------

    @app.route('/api/v1/upload/questions', methods=['POST'])
    @require_auth
    def api_upload_questions():
        """Import questions from a .csv (columns question_text, marking_guide) or .json file."""
        rows, error = _read_upload()
        if error:
            return api_error(400, 'VAL_001', error)
        return jsonify({'success': True, 'file_processed': True, 'total_in_file': len(rows),
                        'result': create_questions(rows), 'timestamp': now_iso()})

    @app.route('/api/v1/upload/students', methods=['POST'])
    @require_auth
    def api_upload_students():
        """Import students from a .csv (columns name, matric_number) or .json file."""
        rows, error = _read_upload()
        if error:
            return api_error(400, 'VAL_001', error)
        return jsonify({'success': True, 'file_processed': True, 'total_in_file': len(rows),
                        'result': create_students(rows), 'timestamp': now_iso()})

    # --- Export -------------------------------------------------------------------------

    def export_format():
        fmt = request.args.get('format', 'json')
        return fmt if fmt in ('csv', 'json') else None

    @app.route('/api/v1/export/questions', methods=['GET'])
    @require_auth
    def api_export_questions():
        """Download your questions as CSV or JSON."""
        fmt = export_format()
        if not fmt:
            return api_error(400, 'VAL_001', 'format must be csv or json')
        rows = get_db().query(Question).filter_by(owner_id=current_user_id()).order_by(Question.id).all()
        return file_response([question_json(q) for q in rows], fmt, 'lexai-questions')

    @app.route('/api/v1/export/students', methods=['GET'])
    @require_auth
    def api_export_students():
        """Download your students as CSV or JSON."""
        fmt = export_format()
        if not fmt:
            return api_error(400, 'VAL_001', 'format must be csv or json')
        rows = get_db().query(Student).filter_by(owner_id=current_user_id()).order_by(Student.id).all()
        return file_response([student_json(s) for s in rows], fmt, 'lexai-students')

    @app.route('/api/v1/export/responses', methods=['GET'])
    @require_auth
    def api_export_responses():
        """Download your responses as CSV or JSON, optionally for one student or question."""
        fmt = export_format()
        if not fmt:
            return api_error(400, 'VAL_001', 'format must be csv or json')
        query = get_db().query(Response).filter_by(owner_id=current_user_id())
        for param in ('student_id', 'question_id'):
            value = request.args.get(param, type=int)
            if value is not None:
                query = query.filter(getattr(Response, param) == value)
        rows = query.order_by(Response.id).all()
        return file_response([{**response_json(r), 'score': effective_score(r)} for r in rows], fmt, 'lexai-responses')
