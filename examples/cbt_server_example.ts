// Place this in your CBT server. Call it only after authenticating the student,
// checking the attempt, and loading the marking guide from your own database.
import { LexAIClient, LexAIError } from '@lexical-ai/lexai-cbt-sdk';

type TheoryQuestion = {
  id: string;
  text: string;
  markingGuide: string; // Server-side field: do not send this to the browser.
};

type GradeDecision =
  | { status: 'graded'; score: number; maxScore: number; feedback: string; model: string; requestId: string }
  | { status: 'needs_review'; score: null; provisionalScore: number; feedback: string; requestId: string }
  | { status: 'pending'; score: null; feedback: string };

const apiKey = process.env.LEXAI_API_KEY;
if (!apiKey) throw new Error('LEXAI_API_KEY is required on the CBT server');

const lexai = new LexAIClient({
  apiKey,
  baseUrl: process.env.LEXAI_BASE_URL ?? 'https://apilexaia.altrisco.tech/api/v1',
});

export async function gradeTheoryAnswer(question: TheoryQuestion, studentAnswer: string): Promise<GradeDecision> {
  try {
    const result = await lexai.scoreAnswer({
      questionText: question.text,
      markingGuide: question.markingGuide,
      studentAnswer,
    });

    if (result.needs_review) {
      return {
        status: 'needs_review',
        score: null, // Do not include this in the student's final total yet.
        provisionalScore: result.data.score,
        feedback: result.data.feedback,
        requestId: result.request_id,
      };
    }

    return {
      status: 'graded',
      score: result.data.score,
      maxScore: result.data.max_score,
      feedback: result.data.feedback,
      model: result.model_used,
      requestId: result.request_id,
    };
  } catch (error) {
    if (error instanceof LexAIError && error.code === 'SCORE_001') {
      return { status: 'pending', score: null, feedback: 'AI grading is temporarily unavailable.' };
    }
    throw error;
  }
}
