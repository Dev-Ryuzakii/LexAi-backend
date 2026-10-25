"""Server-side Python example. Set LEXAI_API_KEY in the CBT backend environment."""
import os

import requests

BASE_URL = os.environ.get('LEXAI_BASE_URL', 'http://127.0.0.1:5001/api/v1').rstrip('/')
API_KEY = os.environ['LEXAI_API_KEY']


def grade_theory_answer(question_text: str, marking_guide: str, student_answer: str) -> dict:
    """Call after authenticating the student and loading the guide from your CBT database."""
    response = requests.post(
        f'{BASE_URL}/score',
        headers={'X-API-Key': API_KEY},
        json={
            'question_text': question_text,
            'marking_guide': marking_guide,
            'student_answer': student_answer,
        },
        timeout=90,
    )
    body = response.json()
    if response.status_code == 503 and body.get('error', {}).get('code') == 'SCORE_001':
        return {'status': 'pending', 'score': None}
    response.raise_for_status()
    return {
        'status': 'needs_review' if body['needs_review'] else 'graded',
        'score': body['data']['score'],
        'max_score': body['data']['max_score'],
        'feedback': body['data']['feedback'],
        'model': body['model_used'],
        'request_id': body['request_id'],
    }
