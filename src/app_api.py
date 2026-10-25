"""
LexAi API entry point.

    python src/app_api.py                        # development server
    gunicorn --chdir src app_api:app             # production
"""
import os

from flask import Flask
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from api_service import register_api_routes
from database import init_db


def _flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
    return response


def create_app() -> Flask:
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024  # 1 MB request bodies

    if _flag('TRUST_PROXY'):
        # Behind one reverse proxy: take the client IP from X-Forwarded-For for IP rate limits.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', 'http://localhost:3000,https://lexai.altrisco.tech').split(',') if o.strip()]
    CORS(app, resources={r'/api/*': {'origins': origins}},
         expose_headers=['X-RateLimit-Limit', 'X-RateLimit-Used', 'X-RateLimit-Remaining', 'X-RateLimit-Reset', 'X-Request-ID'])

    app.after_request(add_security_headers)
    register_api_routes(app)

    if _flag('DB_AUTO_CREATE'):
        init_db()
    return app


app = create_app()

if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5001))
    print(f"LexAi API listening on http://{host}:{port}/api/v1/")
    app.run(debug=_flag('FLASK_DEBUG'), host=host, port=port)
