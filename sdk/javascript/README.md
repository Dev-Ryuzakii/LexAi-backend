# LexAI CBT JavaScript SDK

A small, dependency-free **server-side** client for the LexAI API. Node.js 18+;
JavaScript and TypeScript are supported. Install from npm:

```bash
npm install @lexical-ai/lexai-cbt-sdk
```

```js
import { LexAIClient, allocateQuestionScores } from '@lexical-ai/lexai-cbt-sdk';

const client = new LexAIClient({
  apiKey: process.env.LEXAI_API_KEY,
  defaultMaxScore: 20, // default for this course, exam, or test
});

const result = await client.scoreAnswer({
  studentAnswer: 'Paris',
  markingGuide: 'Paris is the capital of France.',
  questionText: 'What is the capital of France?',
  maxScore: 10, // optional override for this question
});
console.log(result.model_used, result.data.score, result.needs_review);
```

`LEXAI_API_KEY` is a key created by your LexAI account for the CBT server. It is
**not** the Cencori project key. Both keys must stay out of browser bundles.
The default base URL is `https://apilexaia.altrisco.tech/api/v1`. Pass
`baseUrl` to the constructor to use a local or other LexAI deployment.

Set `defaultMaxScore` on a client used for one course, exam, or test when every
question should start with the same maximum. It applies
to `scoreAnswer` and `createQuestion`. Pass `maxScore` on either call to override
it for one question. Stored questions keep their maximum, which `submitResponse`
uses when grading. Updating a question's maximum affects future submissions;
previously stored response grades keep their original maximum. Scores can be
0.01–1000 points, with up to two decimal places. The default is 5.

For **one total across the whole exam**, pass every question to
`scoreAssessment`. Set `maxScore` on selected questions; the remaining marks
are split evenly, to the cent, among questions without it. The sum always
equals `totalMaxScore`. This method makes one stateless API call per question
and returns each grade plus the aggregate. If `needsReview` is true, treat the
aggregate as provisional.

```js
const exam = await client.scoreAssessment({
  totalMaxScore: 100,
  questions: [
    { studentAnswer: 'A1', markingGuide: 'Guide 1', maxScore: 40 },
    { studentAnswer: 'A2', markingGuide: 'Guide 2' }, // 30 marks
    { studentAnswer: 'A3', markingGuide: 'Guide 3' }, // 30 marks
  ],
});
console.log(exam.score, exam.maxScore, exam.needsReview);

// For a stored-question flow, use the same allocation before createQuestion:
const marks = allocateQuestionScores({ totalMaxScore: 100, questions: drafts });
await Promise.all(drafts.map((draft, index) =>
  client.createQuestion({ ...draft, maxScore: marks[index] })));
```

## Methods

| Method | Purpose |
|---|---|
| `scoreAnswer({ studentAnswer, markingGuide, questionText?, maxScore? })` | Grade without storing a LexAI response |
| `scoreAssessment({ totalMaxScore, questions })` | Grade all answers and sum one exam/course/test total |
| `allocateQuestionScores({ totalMaxScore, questions })` | Split a total for stored questions without grading |
| `generateQuestions({ subject, topics, count, questionTypes, ... })` | Generate draft MCQ, fill-blank, or theory questions |
| `createQuestion({ questionText, markingGuide, maxScore? })` | Save a question and return `question_id` |
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
