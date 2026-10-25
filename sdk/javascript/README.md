# LexAI CBT JavaScript SDK

A small, dependency-free **server-side** client for the LexAI API. Node.js 18+;
JavaScript and TypeScript are supported. Install from npm:

```bash
npm install @lexical-ai/lexai-cbt-sdk
```

```js
import { LexAIClient } from '@lexical-ai/lexai-cbt-sdk';

const client = new LexAIClient({
  apiKey: process.env.LEXAI_API_KEY,
});

const result = await client.scoreAnswer({
  studentAnswer: 'Paris',
  markingGuide: 'Paris is the capital of France.',
  questionText: 'What is the capital of France?',
});
console.log(result.model_used, result.data.score, result.needs_review);
```

`LEXAI_API_KEY` is a key created by your LexAI account for the CBT server. It is
**not** the Cencori project key. Both keys must stay out of browser bundles.
The default base URL is `https://apilexaia.altrisco.tech/api/v1`. Pass
`baseUrl` to the constructor to use a local or other LexAI deployment.

## Methods

| Method | Purpose |
|---|---|
| `scoreAnswer({ studentAnswer, markingGuide, questionText? })` | Grade without storing a LexAI response |
| `generateQuestions({ subject, topics, count, questionTypes, ... })` | Generate draft MCQ, fill-blank, or theory questions |
| `createQuestion({ questionText, markingGuide })` | Save a question and return `question_id` |
| `createStudent({ name, matricNumber })` | Save or find a student and return `student_id` |
| `submitResponse({ studentId, questionId, answer })` | Grade and store one response |
| `getResponse(responseId)` | Read a stored response |
| `listResponses({ studentId?, questionId?, gradingStatus?, limit?, offset? })` | Filter stored responses |

Each method accepts an optional second argument `{ signal }` for cancellation.
Constructor options include `timeoutMs` (default 150,000) and `fetchImpl` for a
custom HTTP transport. Return values mirror the API's JSON fields. The SDK
throws `LexAIError` on non-2xx HTTP responses and non-JSON responses.

No submission is retried automatically. A timed-out `submitResponse` may have
already been saved; use `listResponses({ studentId, questionId })` before trying
again. For stateless `scoreAnswer`, a `503` means no grade was produced.

See the [integration guide](../../API_INTEGRATION_GUIDE.md) for key setup,
review handling, and a full CBT flow.
