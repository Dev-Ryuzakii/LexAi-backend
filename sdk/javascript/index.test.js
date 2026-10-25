import assert from 'node:assert/strict';
import test from 'node:test';
import { LexAIClient, LexAIError } from './index.js';

const endpoint = 'https://apilexaia.altrisco.tech/api/v1';

function fakeResponse(body, status = 200) {
  return { ok: status >= 200 && status < 300, status,
    headers: { get: () => 'request-123' }, json: async () => body };
}

test('maps score request and reads LexAI grade', async () => {
  let request;
  const client = new LexAIClient({ apiKey: 'server-secret', baseUrl: endpoint,
    fetchImpl: async (url, options) => {
      request = { url, options };
      return fakeResponse({ success: true, model_used: 'LexAI 3.0', data: { score: 5 } });
    },
  });
  const grade = await client.scoreAnswer({ studentAnswer: 'Paris', markingGuide: 'Paris', questionText: 'Capital?' });
  assert.equal(grade.data.score, 5);
  assert.equal(grade.model_used, 'LexAI 3.0');
  assert.equal(request.url, `${endpoint}/score`);
  assert.equal(request.options.headers['X-API-Key'], 'server-secret');
  assert.deepEqual(JSON.parse(request.options.body), {
    student_answer: 'Paris', marking_guide: 'Paris', question_text: 'Capital?',
  });
});

test('maps stored-assessment calls and filters', async () => {
  const calls = [];
  const client = new LexAIClient({ apiKey: 'server-secret', fetchImpl: async (url, options) => {
    calls.push({ url, options });
    return fakeResponse({ success: true });
  } });
  await client.createQuestion({ questionText: 'Capital?', markingGuide: 'Paris' });
  await client.createStudent({ name: 'Ada', matricNumber: 'M1' });
  await client.submitResponse({ studentId: 2, questionId: 3, answer: 'Paris' });
  await client.listResponses({ studentId: 2, questionId: 3 });
  assert.equal(calls[0].url, `${endpoint}/questions`);
  assert.equal(calls[1].url, `${endpoint}/students`);
  assert.deepEqual(JSON.parse(calls[2].options.body), { student_id: 2, question_id: 3, answer: 'Paris' });
  assert.equal(calls[3].url, `${endpoint}/responses?student_id=2&question_id=3`);
});

test('maps question generation fields', async () => {
  let request;
  const client = new LexAIClient({ apiKey: 'server-secret', fetchImpl: async (url, options) => {
    request = { url, options };
    return fakeResponse({ success: true, data: { questions: [], warnings: [] } });
  } });
  await client.generateQuestions({ subject: 'Science', topics: ['Mars'], count: 2,
    questionTypes: ['MCQ', 'THEORY'], sourceMaterial: 'Planets' });
  assert.equal(request.url, `${endpoint}/generate-questions`);
  assert.deepEqual(JSON.parse(request.options.body), {
    subject: 'Science', topics: ['Mars'], count: 2,
    question_types: ['MCQ', 'THEORY'], difficulty: 'mixed', level: '', instructions: '',
    source_material: 'Planets', avoid_questions: [],
  });
});

test('surfaces API error code and request ID without retrying submission', async () => {
  let attempts = 0;
  const client = new LexAIClient({ apiKey: 'server-secret', fetchImpl: async () => {
    attempts += 1;
    return fakeResponse({ error: { code: 'RES_003', message: 'Already submitted' }, request_id: 'abc' }, 409);
  } });
  await assert.rejects(client.submitResponse({ studentId: 1, questionId: 1, answer: 'x' }), error => {
    assert.ok(error instanceof LexAIError);
    assert.equal(error.status, 409);
    assert.equal(error.code, 'RES_003');
    assert.equal(error.requestId, 'abc');
    return true;
  });
  assert.equal(attempts, 1);
});

test('rejects missing key before any request', () => {
  assert.throws(() => new LexAIClient({ apiKey: '' }), /apiKey is required/);
});
