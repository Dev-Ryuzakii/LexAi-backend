# Integrate LexAI 3.0 into a CBT application

LexAI grades theory answers against a chosen maximum (5 by default). Your CBT backend calls the LexAI API;
your browser or mobile app calls your CBT backend. Keep both the Cencori project key
and the LexAI integration key on servers only.

```text
CBT browser/mobile app -> your CBT backend -> LexAI API -> Cencori
```

## 1. Start LexAI and create an integration key

1. Configure `CENCORI_API_KEY` in the LexAI backend's ignored `.env` and start the
   backend. This is the **provider key**, used only by LexAI to call Cencori.
2. Register or log in as a LexAI account owner. The login endpoint returns a
   session token. Use that token to create an API key in the LexAI frontend or via
   `POST /api/v1/api-keys` with `{"key_name":"CBT server","plan_type":"production"}`.
   The response shows the key once. The key starts with `lexai_`.
3. Save that **LexAI API key** as `LEXAI_API_KEY` in your CBT backend's environment.
   It is different from `CENCORI_API_KEY`. Do not place it in frontend code or a
   public environment variable.

You can also create an integration key for an existing account with:

```bash
python src/generate_api_keys.py create --email you@example.com --name "CBT server" --plan production
```

The default production key limit is 1,000 requests per hour and 10,000 per month.
Use a separate key for each CBT environment. All records created through a key
belong to its LexAI account owner.

## 2. Choose the grading flow

### A. Your CBT project already stores questions and students

Use `POST /api/v1/score`. Pass the student answer, the marking guide from your
**server database**, and the question text. LexAI returns a grade and feedback;
your CBT application stores the result. No LexAI student or question records are
needed.

```json
{
  "student_answer": "Plants use sunlight to make glucose.",
  "marking_guide": "Photosynthesis converts light energy, water and carbon dioxide into glucose and oxygen.",
  "question_text": "Explain photosynthesis.",
  "max_score": 20
}
```

A successful response includes `data.score`, `data.max_score`,
`data.feedback`, `needs_review`, and `model_used: "LexAI 3.0"`. Store a score in
final totals only when `needs_review` is false. If the API returns `503 SCORE_001`,
no grade was produced; leave the answer pending and retry or send it for manual
review. Never turn a failed request into a zero.

### B. LexAI should also store the assessment records

1. `POST /api/v1/questions` with `question_text`, `marking_guide`, and optional
   `max_score`; save the
   returned `question_id` beside your CBT question ID.
2. `POST /api/v1/students` with `name` and `matric_number`; save the returned
   `student_id` beside your CBT student ID. Repeating the same matric number for
   one account returns the existing student.
3. `POST /api/v1/submit-response` with `student_id`, `question_id`, and `answer`.
   The response contains `response_id`, `grading_status`, `scoring`, and
   `student_total_score`. It stores a successfully graded answer.
4. Read `GET /api/v1/responses/{id}` or filter
   `GET /api/v1/responses?student_id=...&question_id=...` to reconcile results.

One student may submit once per LexAI question. A duplicate returns `409 RES_003`.
Do not automatically retry a submission after a network timeout: the first
request may already have committed. Query the responses endpoint using the
student and question IDs first. A `503 SCORE_001` explicitly means nothing was
saved and can be retried.

## JavaScript/TypeScript SDK (server side)

The dependency-free SDK is in [`sdk/javascript`](sdk/javascript). Use Node.js
18 or newer. Install it into your CBT server project:

```bash
npm install @lexical-ai/lexai-cbt-sdk
```

```js
import { LexAIClient, LexAIError } from '@lexical-ai/lexai-cbt-sdk';

const lexai = new LexAIClient({
  apiKey: process.env.LEXAI_API_KEY,
  baseUrl: process.env.LEXAI_BASE_URL ?? 'https://apilexaia.altrisco.tech/api/v1',
  defaultMaxScore: 20, // default for this course, exam, or test
});

// In your authenticated CBT backend handler, fetch question and marking guide
// from your own database. Check that the student owns this attempt first.
const result = await lexai.scoreAnswer({
  studentAnswer: answerFromStudent,
  markingGuide: questionFromDatabase.markingGuide,
  questionText: questionFromDatabase.text,
  maxScore: questionFromDatabase.points, // overrides the default for this question
});

if (result.needs_review) {
  // Keep pending for a lecturer; do not add to the final score yet.
} else {
  // Persist result.data.score (out of result.data.max_score) and feedback.
}
```

The SDK also has `generateQuestions`, `createQuestion`, `createStudent`, `submitResponse`,
`getResponse`, and `listResponses`. It throws `LexAIError` with `status`, `code`,
and `requestId` for API failures. It does **not** retry a POST automatically.
For one total across an entire course, exam, or test, use `scoreAssessment`
with `totalMaxScore` and all question answers. Explicit per-question `maxScore`
values are respected and the remainder is distributed evenly. Use
`allocateQuestionScores` to distribute the same total before storing questions.
See [`sdk/javascript/README.md`](sdk/javascript/README.md) for method details.
For a typed CBT server handler, see
[`examples/cbt_server_example.ts`](examples/cbt_server_example.ts).

## Generate question drafts

Call `generateQuestions` from a teacher-authorized server route. It accepts a
subject, topics, question count, types (`MCQ`, `FILL_BLANK`, `THEORY`), and a
difficulty. The response contains editable drafts with marking guides. Review
the content before publishing an assessment.

```js
const result = await lexai.generateQuestions({
  subject: 'Science',
  topics: ['Solar system'],
  count: 7,
  questionTypes: ['MCQ', 'FILL_BLANK', 'THEORY'],
  difficulty: 'mixed',
});
console.log(result.data.questions, result.data.warnings);
```

The HTTP equivalent is `POST /api/v1/generate-questions` with `X-API-Key`.
The LexLearn CBT backend exposes this through its own teacher-only
`POST /api/assessments/generate-questions` route.

## Direct HTTP request

If your CBT backend uses another language, no SDK is required:

```bash
curl "$LEXAI_BASE_URL/score" \
  -H "X-API-Key: $LEXAI_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"student_answer":"Paris","marking_guide":"Paris is the capital of France.","question_text":"What is the capital of France?"}'
```

Set `LEXAI_BASE_URL` to the full API URL ending in `/api/v1`. Use HTTPS when
calling a deployed backend. The API key belongs in the `X-API-Key` header; query
string keys are not supported.

## Grades and errors

- `max_score` may be 0.01–1000 with up to two decimal places. The AI grades
  directly against that maximum; `score` may also have two decimal places.
  SDK `defaultMaxScore` applies to `scoreAnswer` and `createQuestion`, and their
  `maxScore` argument overrides it for one question.
- `needs_review: true` means the grade is provisional. Stored responses with
  `grading_status: "needs_review"` are excluded from the LexAI student total.
- `401 AUTH_001` or `AUTH_002`: missing, invalid, or revoked integration key.
- `429 RATE_001` or `RATE_002`: rate or monthly quota exceeded. Inspect the
  `X-RateLimit-*` headers and queue work for later.
- `503 SCORE_001`: grading unavailable; never record zero for this case.
- All errors have `error.code`, `error.message`, `request_id`, and `timestamp`.
  Keep `request_id` in your logs to trace a failed integration call.
