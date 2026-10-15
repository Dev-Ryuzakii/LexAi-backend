FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN useradd --create-home lexai && mkdir -p data logs && chown -R lexai /app
USER lexai

EXPOSE 5001

# Apply migrations, then serve with gunicorn (never the Flask debug server).
CMD ["sh", "-c", "alembic upgrade head && exec gunicorn --chdir src --bind 0.0.0.0:5001 --workers ${GUNICORN_WORKERS:-2} --timeout 120 app_api:app"]
