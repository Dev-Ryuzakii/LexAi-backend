# LexAI CBT API reference

The API grades theory answers from 0 to 5. The default grader is LexAI 3.0,
powered by Cencori. For architecture and SDK setup, read the
[integration guide](API_INTEGRATION_GUIDE.md).

Base URL for local development: `http://127.0.0.1:5001/api/v1`.
Hosted base URL: `https://apilexaia.altrisco.tech/api/v1`.

## Authentication

- `GET /health`, `POST /register`, and `POST /login` are public.
- Account management endpoints (`/api-keys` and `/logout`) use a login session:
  `Authorization: Bearer <session-token>`.
- Scoring and assessment endpoints accept either a login session or a LexAI API
  key: `X-API-Key: lexai_...`. The API key belongs on your CBT **server**, not in
  the browser. Keys in query parameters are not accepted.
- Create an account with `POST /register` using `email` and `password`. Log in
  with the same fields at `POST /login`, then create a key with
  `POST /api-keys` and `{"key_name":"CBT server","plan_type":"production"}`.
  The key is returned once in `api_key.api_key`. Plans are `test` and
  `production`; there are no built-in development keys.

## Stateless grading

`POST /score` is the simplest integration when your CBT project already stores
questions and students. JSON body:

```json
{
  "student_answer": "Paris",
  "marking_guide": "Paris is the capital of France.",
  "question_text": "What is the capital of France?"
}
```

Example successful response (other metadata fields omitted):

```json
{
  "success": true,
  "scoring_method": "lexai",
  "model_used": "LexAI 3.0",
  "needs_review": false,
  "data": {
    "score": 5,
    "max_score": 5,
    "confidence": 0.99,
    "feedback": "The answer is correct.",
    "strengths": ["Correct answer"],
    "weaknesses": []
  }
}
```

`question_text` is optional. `student_answer` and `marking_guide` are required.
A result marked `needs_review` is provisional; exclude it from final totals
until a lecturer confirms it. `503 SCORE_001` means no grade was produced.

## Question generation

`POST /generate-questions` creates editable CBT question drafts using LexAI 3.0.
It requires the same authentication as `/score`. Example body:

```json
{
  "subject": "Science",
  "topics": ["Solar system"],
  "count": 7,
  "question_types": ["MCQ", "FILL_BLANK", "THEORY"],
  "difficulty": "mixed"
}
```

The response has `data.questions` and `data.warnings`. Each question includes
its text, type, answer, and marking guide. Teachers should review drafts
before using them in an assessment.

## Stored assessment flow

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/questions` | Create with `question_text`, `marking_guide`; returns `question_id` |
| `GET`, `PUT`, `DELETE` | `/questions/{id}` | Read or manage an owned question |
| `GET` | `/questions` | List owned questions |
| `POST` | `/students` | Create or find with `name`, `matric_number`; returns `student_id` |
| `GET`, `PUT`, `DELETE` | `/students/{id}` | Read or manage an owned student |
| `GET` | `/students` | List owned students |
| `POST` | `/submit-response` | Grade and store `student_id`, `question_id`, `answer` |
| `GET` | `/responses/{id}` | Read a stored response |
| `GET` | `/responses` | List or filter by `student_id`, `question_id`, `grading_status` |
| `POST` | `/responses` | Store an ungraded answer for manual review |
| `PUT`, `DELETE` | `/responses/{id}` | Lecturer score override or deletion |
| `GET` | `/student/{id}/responses` | Read a student's responses |

`POST /submit-response` returns HTTP 201 with `response_id`,
`grading_status`, `scoring` (including `score`, `max_score`, `feedback`,
`model_used`, and `needs_review`), and `student_total_score`. One student can
submit only once per question. A duplicate returns `409 RES_003`.
A failed grading request returns `503 SCORE_001` and saves nothing.

## Account and service endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Database and provider status; provider configuration is listed as `lexai` |
| `POST` | `/register` | Create account |
| `POST` | `/login` | Obtain session token |
| `POST` | `/logout` | Revoke current session token |
| `GET`, `POST` | `/api-keys` | List or create keys; session required |
| `DELETE` | `/api-keys/{id}` | Revoke key; session required |
| `POST` | `/api-keys/{id}/rotate` | Rotate key; session required |

## Errors and limits

Errors return HTTP 4xx or 5xx and a JSON body:

```json
{
  "success": false,
  "error": {"code": "SCORE_001", "message": "The answer could not be graded right now.", "details": {}},
  "message": "The answer could not be graded right now.",
  "request_id": "request-id",
  "timestamp": "2026-10-25T00:00:00"
}
```

Common codes: `AUTH_001` missing credentials, `AUTH_002` invalid credentials,
`AUTH_003` session required, `VAL_001` validation error, `RES_001` not found,
`RES_003` duplicate response, `RATE_001` hourly rate limit, `RATE_002` monthly
quota, `SCORE_001` grading unavailable. Rate headers are
`X-RateLimit-Limit`, `X-RateLimit-Used`, `X-RateLimit-Remaining`, and
`X-RateLimit-Reset`. Record `request_id` when investigating a failed request.
