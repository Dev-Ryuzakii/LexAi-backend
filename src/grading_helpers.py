"""Provider-neutral grading prompt, cache, and review-only fallback."""
import hashlib
import logging
import time

from scoring import MAX_SCORE

logger = logging.getLogger(__name__)

class ResponseCache:
    """Simple in-process cache of successful gradings, keyed by the exact inputs"""
    def __init__(self, max_size=1000, ttl=3600):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl  # Time to live in seconds

    def _generate_key(self, student_answer, marking_guide, question, max_score=MAX_SCORE):
        combined = f"{student_answer.strip().lower()}|{marking_guide.strip().lower()}|{(question or '').strip().lower()}|{max_score}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def get(self, student_answer, marking_guide, question, max_score=MAX_SCORE):
        """Get a copy of the cached response if available and not expired"""
        key = self._generate_key(student_answer, marking_guide, question, max_score)
        if key in self.cache:
            timestamp, response = self.cache[key]
            if time.time() - timestamp <= self.ttl:
                logger.info("Cache hit for scoring request")
                return dict(response)
            del self.cache[key]
        return None

    def set(self, student_answer, marking_guide, question, response, max_score=MAX_SCORE):
        key = self._generate_key(student_answer, marking_guide, question, max_score)
        self.cache[key] = (time.time(), dict(response))

        if len(self.cache) > self.max_size:
            # Remove oldest 20%
            sorted_keys = sorted(self.cache.items(), key=lambda x: x[1][0])
            for k, _ in sorted_keys[:int(self.max_size * 0.2)]:
                del self.cache[k]


def create_scoring_prompt(student_answer: str, marking_guide: str, question: str = "", max_score: float = MAX_SCORE) -> str:
    return f"""
You are an expert educator tasked with scoring student answers based on MEANING and UNDERSTANDING, not exact word matching.

Question: {question if question else "Not provided"}

Marking Guide/Expected Answer:
{marking_guide}

Student's Answer:
{student_answer}

Your task:
- Compare the MEANING of the student's answer with the marking guide
- The student's answer does NOT need to be word-for-word identical
- Focus on whether the student demonstrates understanding of the concept
- Award points based on how well the meaning aligns with the marking guide

Scoring Scale (0 to {max_score} points):
- Full credit: Excellent understanding, meaning perfectly aligns with marking guide
- About 80%: Good understanding, meaning mostly aligns with minor gaps
- About 60%: Adequate understanding, meaning somewhat aligns but missing some key points
- About 40%: Basic understanding, meaning partially aligns but significant gaps
- About 20%: Poor understanding, meaning barely aligns with marking guide
- Zero: No understanding, meaning does not align or is completely incorrect

Please provide your response in the following JSON format:
{{
    "score": {round(max_score * 0.8, 2)},
    "confidence": 0.9,
    "feedback": "The student demonstrates good understanding of the concept. The meaning aligns well with the marking guide despite different wording.",
    "strengths": ["Correct core concept", "Good explanation"],
    "weaknesses": ["Could be more detailed", "Missing one key point"]
}}

Important:
- Score must be a number between 0 and {max_score}, with at most two decimal places
- Confidence must be a number between 0 and 1
- Focus on MEANING and UNDERSTANDING, not exact words
- Consider different ways of expressing the same concept as correct

Respond only with the JSON object, no additional text.
"""

def fallback_similarity_score(student_answer: str, marking_guide: str) -> int:
    """
    Text-similarity estimate on the 0-5 scale. This is not an AI grade: callers
    must flag results from it for lecturer review.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words='english', lowercase=True)
        tfidf_matrix = vectorizer.fit_transform([student_answer.lower(), marking_guide.lower()])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return max(0, min(MAX_SCORE, int(similarity * MAX_SCORE)))
    except Exception:
        student_words = set(student_answer.lower().split())
        guide_words = set(marking_guide.lower().split())
        if not guide_words:
            return 0
        similarity = len(student_words & guide_words) / len(guide_words)
        return max(0, min(MAX_SCORE, int(similarity * MAX_SCORE)))
