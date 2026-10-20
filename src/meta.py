"""
Public, unauthenticated metadata: changelog and an OpenAPI 3 spec generated from the
registered routes (so it cannot drift from the code). Request bodies come from each
route's @validate_body rules and security from @require_auth / @require_session.
"""
import re
from typing import Any, Dict

import yaml
from flask import current_app, jsonify, make_response, request

CHANGELOG = [
    {
        'version': '1.3.0',
        'date': '2026-10-20',
        'changes': [
            {'type': 'added', 'category': 'generation', 'description': 'AI question generation: MCQ, fill-in-the-blank and theory questions with answer keys, marking guides and explanations.',
             'endpoints': ['/generate-questions']},
        ],
    },
    {
        'version': '1.2.0',
        'date': '2026-10-15',
        'changes': [
            {'type': 'added', 'category': 'analytics', 'description': 'Usage analytics: quota, statistics, timeline, top endpoints, period comparison and CSV/JSON export.',
             'endpoints': ['/analytics/quota', '/analytics/stats', '/analytics/timeline', '/analytics/top-endpoints', '/analytics/compare', '/analytics/export']},
            {'type': 'added', 'category': 'webhooks', 'description': 'Signed webhooks for scoring, quota, API key and error events, delivered with retries.',
             'endpoints': ['/webhooks']},
            {'type': 'added', 'category': 'security', 'description': 'Per-key IP allow and deny rules (single addresses or CIDR ranges).',
             'endpoints': ['/api-keys/{id}/ip-rules']},
            {'type': 'added', 'category': 'scoring', 'description': 'Batch scoring of up to 100 answers, optionally as a background job.',
             'endpoints': ['/score/batch', '/jobs/{id}']},
            {'type': 'added', 'category': 'data', 'description': 'Bulk create, update and delete; CSV/JSON upload and export.',
             'endpoints': ['/bulk/questions', '/bulk/students', '/upload/questions', '/upload/students', '/export/questions', '/export/students', '/export/responses']},
            {'type': 'added', 'category': 'reliability', 'description': 'Idempotency-Key header on POST endpoints, Retry-After on 429/503, provider circuit breakers and jittered retries.'},
            {'type': 'added', 'category': 'documentation', 'description': 'Generated OpenAPI specification.', 'endpoints': ['/openapi.json', '/openapi.yaml']},
        ],
    },
    {
        'version': '1.1.0',
        'date': '2026-10-15',
        'changes': [
            {'type': 'removed', 'category': 'breaking', 'description': 'Built-in development API keys (dev_key_123, test_key_789) no longer work.'},
            {'type': 'removed', 'category': 'breaking', 'description': 'The api_key query parameter is no longer accepted; send the X-API-Key header.'},
            {'type': 'changed', 'category': 'breaking', 'description': 'Questions, students and responses are private to the account that created them.'},
            {'type': 'changed', 'category': 'breaking', 'description': 'A student can submit one response per question; repeats return 409.', 'endpoints': ['/submit-response']},
            {'type': 'changed', 'category': 'breaking', 'description': 'When no AI provider can grade, scoring returns 503 instead of a zero score.', 'endpoints': ['/score', '/submit-response']},
            {'type': 'changed', 'category': 'breaking', 'description': 'API keys are shown once at creation; lists show only a prefix. Key management requires a logged-in session.', 'endpoints': ['/api-keys']},
            {'type': 'changed', 'category': 'scoring', 'description': 'Low-confidence and fallback grades are marked needs_review and excluded from totals until confirmed.'},
            {'type': 'changed', 'category': 'breaking', 'description': 'Errors use {success:false, error:{code, message, details}}.'},
            {'type': 'added', 'category': 'security', 'description': 'Login and registration rate limits, monthly quota enforcement, hashed credentials.'},
        ],
    },
    {
        'version': '1.0.0',
        'date': '2025-10-26',
        'changes': [
            {'type': 'added', 'category': 'core', 'description': 'Initial release: AI scoring, questions, students, responses, API keys.'},
        ],
    },
]

BREAKING_CHANGES = [
    {'version': '1.1.0', 'date': '2026-10-15', 'planned': False, 'changes': [
        {'type': 'removed', 'category': 'authentication', 'description': 'Built-in development API keys removed.',
         'migration': 'Register, log in and create a key on the API Keys page.'},
        {'type': 'removed', 'category': 'authentication', 'description': 'api_key query parameter removed.',
         'migration': 'Send the key in the X-API-Key header.'},
        {'type': 'changed', 'category': 'data', 'description': 'Records are scoped to their owner.',
         'migration': 'Records created before this version have no owner until an administrator assigns them during the database migration.'},
        {'type': 'changed', 'category': 'scoring', 'description': 'One submission per student per question.',
         'migration': 'Handle 409 RES_003; the response includes the existing response_id.', 'endpoints': ['/submit-response']},
        {'type': 'changed', 'category': 'scoring', 'description': 'Grading failures return 503 SCORE_001 and store nothing.',
         'migration': 'Retry after the Retry-After interval; send an Idempotency-Key to make retries safe.', 'endpoints': ['/score', '/submit-response']},
        {'type': 'changed', 'category': 'api-keys', 'description': 'Full keys are returned only when created or rotated.',
         'migration': 'Store the key from the create/rotate response; rotate to obtain a new one.', 'endpoints': ['/api-keys']},
    ]},
    {'version': '2.0.0', 'date': '2027-04-01', 'planned': True, 'changes': [
        {'type': 'removed', 'category': 'api-keys', 'description': 'The ignored email field on POST /api-keys will be rejected.',
         'migration': 'Stop sending email when creating keys.', 'endpoints': ['/api-keys']},
    ]},
]

DEPRECATIONS = [
    {'endpoint': 'POST /api/v1/api-keys (email field)', 'deprecated_since': '1.1.0', 'removed_in': '2.0.0',
     'replacement': 'Omit email; keys always belong to the logged-in user.', 'reason': 'Allowed creating keys for other accounts.'},
    {'endpoint': 'GET /api/v1/student/{id}/responses', 'deprecated_since': '1.2.0', 'removed_in': '2.0.0',
     'replacement': 'GET /api/v1/responses?student_id={id}', 'reason': 'Consolidating response listing.'},
]


def _schema_for(rule: Dict[str, Any]) -> Dict[str, Any]:
    kind = rule['type']
    schema: Dict[str, Any] = {
        str: {'type': 'string'}, int: {'type': 'integer'}, float: {'type': 'number'},
        bool: {'type': 'boolean'}, list: {'type': 'array', 'items': {}}, dict: {'type': 'object'},
    }[kind]
    if 'max_length' in rule:
        schema['maxLength'] = rule['max_length']
    if 'min' in rule:
        schema['minimum'] = rule['min']
    if 'max' in rule:
        schema['maximum'] = rule['max']
    if 'max_items' in rule:
        schema['maxItems'] = rule['max_items']
    if 'choices' in rule:
        schema['enum'] = list(rule['choices'])
    return schema


def build_openapi(app) -> Dict[str, Any]:
    from api_service import API_VERSION

    error_ref = {'$ref': '#/components/schemas/Error'}
    paths: Dict[str, Dict[str, Any]] = {}
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if not rule.rule.startswith('/api/v1/'):
            continue
        view = app.view_functions[rule.endpoint]
        path = re.sub(r'<(?:(\w+):)?(\w+)>', r'{\2}', rule.rule[len('/api/v1'):])
        params = [{'name': name, 'in': 'path', 'required': True,
                   'schema': {'type': 'integer' if conv == 'int' else 'string'}}
                  for conv, name in re.findall(r'<(?:(\w+):)?(\w+)>', rule.rule)]
        doc = (view.__doc__ or '').strip().splitlines()
        auth = getattr(view, '_auth', None)
        security = ([{'ApiKeyAuth': []}, {'BearerAuth': []}] if auth == 'api_key_or_session'
                    else [{'BearerAuth': []}] if auth == 'session' else [])
        tag = path.strip('/').split('/')[0] or 'service'

        for method in sorted(rule.methods - {'HEAD', 'OPTIONS'}):
            op: Dict[str, Any] = {
                'operationId': rule.endpoint,
                'summary': doc[0] if doc else rule.endpoint.replace('api_', '').replace('_', ' ').capitalize(),
                'tags': [tag],
                'security': security,
                'responses': {
                    '200': {'description': 'Success'},
                    '400': {'description': 'Validation error', 'content': {'application/json': {'schema': error_ref}}},
                    '401': {'description': 'Missing or invalid credentials', 'content': {'application/json': {'schema': error_ref}}},
                    '429': {'description': 'Rate limit or quota exceeded (see Retry-After)', 'content': {'application/json': {'schema': error_ref}}},
                },
            }
            if params:
                op['parameters'] = params
            body_rules = getattr(view, '_body_rules', None)
            if body_rules:
                op['requestBody'] = {'required': True, 'content': {'application/json': {'schema': {
                    'type': 'object',
                    'properties': {name: _schema_for(r) for name, r in body_rules.items()},
                    'required': [name for name, r in body_rules.items() if r.get('required')],
                }}}}
            if method == 'POST' and security:
                op.setdefault('parameters', []).append({
                    'name': 'Idempotency-Key', 'in': 'header', 'required': False, 'schema': {'type': 'string', 'maxLength': 100},
                    'description': 'Supported on create endpoints: retries with the same key replay the first response.'})
            paths.setdefault(path, {})[method.lower()] = op

    return {
        'openapi': '3.0.3',
        'info': {'title': 'LexAi API', 'version': API_VERSION,
                 'description': 'AI-assisted grading and question generation for computer-based tests.'},
        'servers': [{'url': request.host_url.rstrip('/') + '/api/v1'}],
        'components': {
            'securitySchemes': {
                'ApiKeyAuth': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key'},
                'BearerAuth': {'type': 'http', 'scheme': 'bearer', 'description': 'Session token from POST /login'},
            },
            'schemas': {'Error': {'type': 'object', 'properties': {
                'success': {'type': 'boolean'},
                'error': {'type': 'object', 'properties': {
                    'code': {'type': 'string'}, 'message': {'type': 'string'}, 'details': {'type': 'object'}}},
                'message': {'type': 'string'}, 'request_id': {'type': 'string'}, 'timestamp': {'type': 'string'},
            }}},
        },
        'paths': paths,
    }


def register_meta_routes(app):
    from api_service import API_VERSION, now_iso

    @app.route('/api/v1/changelog', methods=['GET'])
    def api_changelog():
        """API version history."""
        version = request.args.get('version')
        entries = [e for e in CHANGELOG if not version or e['version'] == version]
        return jsonify({'changelog': entries, 'latest_version': CHANGELOG[0]['version'],
                        'total_versions': len(CHANGELOG), 'timestamp': now_iso()})

    @app.route('/api/v1/changelog/breaking-changes', methods=['GET'])
    def api_breaking_changes():
        """Released and planned breaking changes, with migration notes."""
        return jsonify({'breaking_changes': BREAKING_CHANGES, 'current_version': API_VERSION, 'timestamp': now_iso()})

    @app.route('/api/v1/changelog/deprecations', methods=['GET'])
    def api_deprecations():
        """Deprecated endpoints and fields."""
        return jsonify({'deprecations': DEPRECATIONS, 'current_version': API_VERSION, 'timestamp': now_iso()})

    @app.route('/api/v1/openapi.json', methods=['GET'])
    def api_openapi_json():
        """OpenAPI 3 specification (JSON)."""
        return jsonify(build_openapi(current_app))

    @app.route('/api/v1/openapi.yaml', methods=['GET'])
    def api_openapi_yaml():
        """OpenAPI 3 specification (YAML)."""
        response = make_response(yaml.safe_dump(build_openapi(current_app), sort_keys=False, allow_unicode=True))
        response.mimetype = 'application/yaml'
        return response
