export interface ClientOptions {
  /** Backend-only API key; never expose this value in a browser bundle. */
  apiKey: string;
  /** Full API base URL, ending in /api/v1. Defaults to https://apilexaia.altrisco.tech/api/v1. */
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

export interface RequestOptions { signal?: AbortSignal }

export interface ScoreData {
  score: number;
  max_score: number;
  confidence: number;
  feedback: string;
  strengths: string[];
  weaknesses: string[];
}

export interface ScoreResult {
  success: true;
  scoring_method: string;
  model_used: string;
  needs_review: boolean;
  cached: boolean;
  processing_time: number;
  data: ScoreData;
  request_id: string;
  timestamp: string;
}

export interface GeneratedQuestion {
  type: 'MCQ' | 'FILL_BLANK' | 'THEORY';
  question_text: string;
  options: string[];
  correct_answer: string;
  accepted_answers: string[];
  marking_guide: string;
  suggested_points: number;
  explanation: string;
  common_mistakes: string[];
  learning_objective: string;
  topic: string;
  difficulty: string;
}

export interface GenerationResult {
  success: true;
  data: { questions: GeneratedQuestion[]; warnings: string[] };
  model_used: string;
  request_id: string;
  timestamp: string;
}

export interface SubmitResult {
  success: true;
  response_id: number;
  grading_status: 'graded' | 'needs_review';
  scoring: {
    score: number;
    max_score: number;
    feedback: string;
    confidence: number;
    strengths: string;
    weaknesses: string;
    method: string;
    model_used: string;
    needs_review: boolean;
  };
  student_total_score: number;
  timestamp: string;
}

export interface ResponseRecord {
  id: number;
  student_id: number;
  question_id: number;
  answer: string;
  score: number;
  max_score: number;
  grading_status: 'graded' | 'needs_review';
  scoring_method: string | null;
  model_used: string | null;
  ai_score: number | null;
  lecturer_score: number | null;
  ai_feedback: string | null;
  ai_confidence: number | null;
  created_at: string;
}

export class LexAIError extends Error {
  status?: number;
  code?: string;
  requestId?: string | null;
  details?: unknown;
}

export class LexAIClient {
  constructor(options: ClientOptions);
  scoreAnswer(input: { studentAnswer: string; markingGuide: string; questionText?: string; studentName?: string; matricNumber?: string; metadata?: Record<string, unknown> }, options?: RequestOptions): Promise<ScoreResult>;
  generateQuestions(input: { subject: string; topics: string[]; count: number; questionTypes: Array<'MCQ' | 'FILL_BLANK' | 'THEORY'>; difficulty?: 'easy' | 'medium' | 'hard' | 'mixed'; level?: string; instructions?: string; sourceMaterial?: string; avoidQuestions?: string[] }, options?: RequestOptions): Promise<GenerationResult>;
  createQuestion(input: { questionText: string; markingGuide: string }, options?: RequestOptions): Promise<{ success: true; question_id: number }>;
  createStudent(input: { name: string; matricNumber: string }, options?: RequestOptions): Promise<{ success: true; student_id: number }>;
  submitResponse(input: { studentId: number; questionId: number; answer: string }, options?: RequestOptions): Promise<SubmitResult>;
  getResponse(responseId: number, options?: RequestOptions): Promise<{ response: ResponseRecord }>;
  listResponses(filters?: { studentId?: number; questionId?: number; gradingStatus?: 'graded' | 'needs_review'; limit?: number; offset?: number }, options?: RequestOptions): Promise<{ responses: ResponseRecord[]; total_count: number }>;
}
