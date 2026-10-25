// Run this inside your CBT server, never in the browser.
// Install the local SDK first: npm install /absolute/path/to/LexAi-backend/sdk/javascript
import { LexAIClient, LexAIError } from '@lexical-ai/lexai-cbt-sdk';

const lexai = new LexAIClient({
  apiKey: process.env.LEXAI_API_KEY,
  baseUrl: process.env.LEXAI_BASE_URL ?? 'https://apilexaia.altrisco.tech/api/v1',
});

/** Call after your CBT server authenticates the student and loads the trusted guide. */
export async function gradeTheoryAnswer({ questionText, markingGuide, studentAnswer }) {
  try {
    const result = await lexai.scoreAnswer({ questionText, markingGuide, studentAnswer });
    return {
      status: result.needs_review ? 'needs_review' : 'graded',
      score: result.data.score,
      maxScore: result.data.max_score,
      feedback: result.data.feedback,
      model: result.model_used,
      requestId: result.request_id,
    };
  } catch (error) {
    if (error instanceof LexAIError && error.code === 'SCORE_001') {
      return { status: 'pending', score: null, feedback: 'Grading is temporarily unavailable.' };
    }
    throw error;
  }
}
