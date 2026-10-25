/** Server-side client for the LexAI CBT API. Keep its API key out of browser code. */
export class LexAIError extends Error {
  constructor(message, { status, code, requestId, details } = {}) {
    super(message);
    this.name = 'LexAIError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

export class LexAIClient {
  #apiKey;
  #baseUrl;
  #fetch;
  #timeoutMs;
  #defaultMaxScore;

  constructor({ apiKey, baseUrl = 'https://apilexaia.altrisco.tech/api/v1', fetchImpl = globalThis.fetch,
    timeoutMs = 150_000, defaultMaxScore = 5 } = {}) {
    if (typeof apiKey !== 'string' || !apiKey.trim()) {
      throw new TypeError('apiKey is required');
    }
    if (typeof fetchImpl !== 'function') {
      throw new TypeError('fetch is required (Node.js 18 or newer)');
    }
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
      throw new TypeError('timeoutMs must be a positive number');
    }
    this.#defaultMaxScore = LexAIClient.#validateMaxScore(defaultMaxScore);
    const url = new URL(baseUrl);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new TypeError('baseUrl must be an HTTP(S) URL without credentials, query, or fragment');
    }
    if (!url.pathname.replace(/\/$/, '').endsWith('/api/v1')) {
      throw new TypeError('baseUrl must end in /api/v1');
    }
    this.#apiKey = apiKey;
    this.#baseUrl = url.href.replace(/\/$/, '');
    this.#fetch = fetchImpl;
    this.#timeoutMs = timeoutMs;
  }

  static #validateMaxScore(value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0.01 || value > 1000 ||
        Math.round(value * 100) / 100 !== value) {
      throw new TypeError('maxScore must be between 0.01 and 1000, with at most two decimal places');
    }
    return value;
  }

  async #request(method, path, body, { signal } = {}) {
    const controller = new AbortController();
    const abort = () => controller.abort(signal?.reason);
    if (signal?.aborted) abort();
    else signal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(() => controller.abort(new Error('LexAI request timed out')), this.#timeoutMs);
    try {
      const response = await this.#fetch(`${this.#baseUrl}${path}`, {
        method,
        headers: {
          'X-API-Key': this.#apiKey,
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: controller.signal,
      });
      let payload;
      try {
        payload = await response.json();
      } catch {
        throw new LexAIError('LexAI returned a non-JSON response', {
          status: response.status,
          requestId: response.headers?.get('X-Request-ID'),
        });
      }
      if (!response.ok) {
        throw new LexAIError(payload?.error?.message || payload?.message || `LexAI HTTP ${response.status}`, {
          status: response.status,
          code: payload?.error?.code,
          details: payload?.error?.details,
          requestId: payload?.request_id || response.headers?.get('X-Request-ID'),
        });
      }
      return payload;
    } catch (error) {
      if (error instanceof LexAIError) throw error;
      if (controller.signal.aborted) {
        throw new LexAIError(signal?.aborted ? 'LexAI request cancelled' : 'LexAI request timed out');
      }
      throw new LexAIError('Could not reach LexAI API', { details: { cause: error.message } });
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
    }
  }

  scoreAnswer({ studentAnswer, markingGuide, questionText = '', studentName, matricNumber, metadata, maxScore }, options) {
    return this.#request('POST', '/score', {
      student_answer: studentAnswer,
      marking_guide: markingGuide,
      question_text: questionText,
      max_score: LexAIClient.#validateMaxScore(maxScore ?? this.#defaultMaxScore),
      ...(studentName === undefined ? {} : { student_name: studentName }),
      ...(matricNumber === undefined ? {} : { matric_number: matricNumber }),
      ...(metadata === undefined ? {} : { metadata }),
    }, options);
  }

  generateQuestions({ subject, topics, count, questionTypes, difficulty = 'mixed', level = '',
    instructions = '', sourceMaterial = '', avoidQuestions = [] }, options) {
    return this.#request('POST', '/generate-questions', {
      subject,
      topics,
      count,
      question_types: questionTypes,
      difficulty,
      level,
      instructions,
      source_material: sourceMaterial,
      avoid_questions: avoidQuestions,
    }, options);
  }

  createQuestion({ questionText, markingGuide, maxScore }, options) {
    return this.#request('POST', '/questions', {
      question_text: questionText,
      marking_guide: markingGuide,
      max_score: LexAIClient.#validateMaxScore(maxScore ?? this.#defaultMaxScore),
    }, options);
  }

  createStudent({ name, matricNumber }, options) {
    return this.#request('POST', '/students', { name, matric_number: matricNumber }, options);
  }

  submitResponse({ studentId, questionId, answer }, options) {
    return this.#request('POST', '/submit-response', {
      student_id: studentId,
      question_id: questionId,
      answer,
    }, options);
  }

  getResponse(responseId, options) {
    return this.#request('GET', `/responses/${encodeURIComponent(responseId)}`, undefined, options);
  }

  listResponses({ studentId, questionId, gradingStatus, limit, offset } = {}, options) {
    const query = new URLSearchParams();
    if (studentId !== undefined) query.set('student_id', String(studentId));
    if (questionId !== undefined) query.set('question_id', String(questionId));
    if (gradingStatus !== undefined) query.set('grading_status', gradingStatus);
    if (limit !== undefined) query.set('limit', String(limit));
    if (offset !== undefined) query.set('offset', String(offset));
    const suffix = query.toString() ? `?${query}` : '';
    return this.#request('GET', `/responses${suffix}`, undefined, options);
  }
}
