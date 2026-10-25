# LexAi Backend

AI-assisted grading API for computer-based tests. Schools' CBT systems (and the
[LexAi frontend](https://github.com/Dev-Ryuzakii/LexAi-frontend), a separate repo) call it
to grade theory answers against a marking guide.

Grading uses Cencori with `gpt-6-luna` by default, shown to API users as **LexAI 3.0**.
PaLM, Cohere or Hugging Face can be used as fallback providers when their keys are set. If none
of them can grade, the API either reports that grading failed or returns a text-similarity
estimate marked for lecturer review. It never presents a failure as a zero, or a guess as a grade.

## Quick start

Requires Python 3.11+. Redis is optional (it shares rate-limit and quota counters across
workers). A Cencori project key is needed for LexAI 3.0 grading.

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                # then edit
# Set CENCORI_API_KEY in .env to a project key from https://console.cencori.com/home
alembic upgrade head                # create/upgrade the database
python src/app_api.py               # http://127.0.0.1:5001/api/v1/
```

Or run `./start.sh` (or `start_platform.bat` on Windows), which does the same.

With Docker, `docker compose up --build` runs migrations and serves with gunicorn on port 5001.
The API port binds to the host's loopback interface for a local reverse proxy.
Set `CENCORI_API_KEY` in `.env` before starting the container.

### VPS with an existing PostgreSQL container

LexAI can use a dedicated database inside an existing PostgreSQL container. Do not
install another PostgreSQL server or reuse another project's database or login.
On the current VPS, `shared-postgres` is attached to the `afribase-shared` Docker
network. After pulling this repo on the VPS, run:

```bash
POSTGRES_DOCKER_NETWORK=afribase-shared bash scripts/setup_existing_postgres.sh
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.postgres.yml ps
curl --fail http://127.0.0.1:5001/api/v1/health
```

The setup script creates the `lexai` database and `lexai_app` login in
`shared-postgres`, generates a random password, and saves its connection URL and
network name in the ignored `.env` file. It stops without changing credentials if
either the database or login already exists. Keep `.env` private; `.env.production`
is not read by this Compose configuration. The API container runs Alembic migrations
before accepting requests. No host `psql` installation is needed because the script
uses the client inside the PostgreSQL container. If your container or network has a
different name, set `POSTGRES_CONTAINER` and `POSTGRES_DOCKER_NETWORK` accordingly.

All settings are environment variables. `.env.example` lists every variable and its default.
Set `CORS_ORIGINS=*` in the VPS `.env` and recreate `lexai-api` to allow browser
requests from any website and origin port. Authentication remains required on
protected endpoints. The API container's host port stays bound to loopback;
Nginx serves public HTTPS traffic on port 443.

To connect an existing CBT project, follow the [integration guide](API_INTEGRATION_GUIDE.md).
It covers server-side API keys, grading with your own records, storing assessments
in LexAI, and the [JavaScript/TypeScript SDK](sdk/javascript/README.md).

## Authentication

| Credential | How to get it | Header | Can call |
|---|---|---|---|
| Session token | `POST /api/v1/login` | `Authorization: Bearer <token>` | Everything |
| API key | Create one in the frontend, or call `POST /api/v1/api-keys` with a session | `X-API-Key: <key>` | Everything except key management and logout |

- The API has no built-in development keys. Any key that isn't in the database is rejected. If the credential lookup itself fails, the request fails with 503 instead of being let through.
- Passwords are hashed with Werkzeug (scrypt/pbkdf2). Old SHA-256 hashes are still accepted and are upgraded the next time the user logs in.
- API keys and session tokens are stored only as SHA-256 digests. A key is shown once, when it is created or rotated. After that, lists show only its prefix.
- A new key belongs to the logged-in user. Any `email` field in the request is ignored.

## Data ownership

Every question, student and response belongs to the user who created it, and every query is
filtered by owner. Other users get `404` for records that aren't theirs. Matric numbers must be
unique within one owner's records, not across all owners.

## Grading rules

- `POST /api/v1/submit-response` grades an answer and stores it. Each student can submit **one response per question**. A second submission returns `409` and does not call the AI.
- If no provider can grade, the response is `503 SCORE_001` and **nothing is stored**, so the client can safely retry.
- A grade is stored as `needs_review` (and left out of the student's total) when the AI's confidence is below `REVIEW_CONFIDENCE_THRESHOLD` or when it came from the text-similarity fallback. A lecturer confirms or overrides it with `PUT /api/v1/responses/{id}` `{"score": n}`.
- A student's `score` is always the sum of their graded responses. It is recalculated in the same transaction whenever a response is created, rescored or deleted, and it can't be set directly.
- Model output becomes a grade only if it is valid JSON with a whole-number score from 0 to 5. Anything else is retried once and then treated as a failure.

## Limits

| Limit | Default | Applies to |
|---|---|---|
| Hourly rate limit | Set per key (test plan max 100, production plan max 1000); 1000 for sessions | Authenticated endpoints |
| Monthly quota | Set per key (test plan max 1000, production plan max 10000) | API-key requests |
| Login attempts | 10 per 15 minutes per IP | `/login` |
| Registrations | 5 per hour per IP | `/register` |

Responses carry `X-RateLimit-Limit`, `-Used`, `-Remaining` and `-Reset` headers. If you run more
than one worker, use Redis. Without it, each process keeps its own counters.

## Endpoints

All paths are under `/api/v1`.

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | No auth. Returns 503 if the database is unreachable |
| POST | `/register`, `/login` | Rate-limited by IP |
| POST | `/logout` | Needs a session |
| POST | `/score` | Stateless grading. Returns `needs_review`, or `503` when no grade could be produced |
| GET/POST | `/questions` | Lists accept `limit` (max 500) and `offset` |
| GET/PUT/DELETE | `/questions/{id}` | Deleting a question also deletes its responses and recalculates totals |
| GET/POST | `/students` | |
| GET/PUT/DELETE | `/students/{id}` | |
| GET/POST | `/responses` | Filter with `student_id`, `question_id` or `grading_status`. POST stores an ungraded answer |
| GET/PUT/DELETE | `/responses/{id}` | PUT `score` is a lecturer override |
| POST | `/submit-response` | Grades and stores an answer |
| GET | `/student/{id}/responses` | |
| GET/POST | `/api-keys` | Needs a session |
| DELETE | `/api-keys/{id}` | Revokes the key |
| POST | `/api-keys/{id}/rotate` | Revokes the old key and returns a new one |

Errors use one shape:

```json
{ "success": false,
  "error": { "code": "VAL_001", "message": "...", "details": { "validation_errors": [] } },
  "message": "...", "request_id": "...", "timestamp": "..." }
```

The main error codes are: `AUTH_001` missing credentials, `AUTH_002` invalid or expired credentials, `AUTH_003` a session is
required, `AUTH_004` wrong email or password, `AUTH_005` authentication is unavailable, `VAL_00x` validation,
`RES_001` not found, `RES_002`/`RES_003` conflicts, `RATE_00x` limits, `SCORE_001` grading unavailable.

## Operator CLI

```bash
python src/generate_api_keys.py create --email user@example.com --name "CBT integration" --plan production
python src/generate_api_keys.py list
python src/generate_api_keys.py revoke --id 3
```

## Upgrading an existing database

`alembic upgrade head` applies `20261015_security_ownership`, which:

- adds `owner_id` to questions, students and responses. Set `LEGACY_OWNER_EMAIL=<email>` while migrating to give existing rows to that user. Without it, those rows have no owner and the API doesn't return them;
- replaces stored API keys with their hashes, so existing keys keep working;
- deletes the stored session tokens, because they were saved in plaintext. Users have to log in again;
- adds the one-response-per-question constraint. The migration stops and lists the conflicting rows if any student already has several responses to the same question.

Back up the database first. This migration can't be reversed.

> **Credentials in git history:** earlier commits included `data/database.db`, which contains
> plaintext API keys and login tokens for test accounts. Those keys are public. Revoke every key
> that was ever created in that database, and don't reuse that file.

## Tests

```bash
pytest
```

The suite runs in-process with a temporary SQLite database and a fake grader, so you don't need a
server, Redis or a Cencori key. It checks authentication, isolation between users, key handling, quotas,
the parser, submission rules and how totals are kept.

## Training scripts

`src/train.py`, `src/model.py` and `src/evaluate.py` belong to the earlier TF-IDF model and the API
doesn't use them. They need `pip install -r requirements-ml.txt`.
