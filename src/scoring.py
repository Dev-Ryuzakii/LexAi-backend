"""
Shared scoring primitives for every AI provider.

Model output is never trusted: a response only becomes a grade when it is a
JSON object with an integer score inside the scale. Anything else raises, so
"could not grade" can never be stored as "the student earned N".
"""
import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MAX_SCORE = 5


class ScoringError(Exception):
    """The provider could not produce a grade (network, model or parse failure)."""


class ScoringParseError(ScoringError):
    """The provider answered, but not with a valid grade."""


def _string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    raise ScoringParseError(f"Expected a list of strings, got {type(value).__name__}")


def parse_scoring_response(text: str, max_score: int = MAX_SCORE) -> Dict[str, Any]:
    """Parse a model reply into a grade, or raise ScoringParseError."""
    if not isinstance(text, str) or not text.strip():
        raise ScoringParseError("Empty response from model")

    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end <= start:
        raise ScoringParseError("No JSON object in model response")

    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise ScoringParseError(f"Invalid JSON in model response: {e}") from e

    if not isinstance(parsed, dict) or 'score' not in parsed:
        raise ScoringParseError("Model response has no score")

    raw_score = parsed['score']
    # bool is a subclass of int; "true" is not a grade.
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raise ScoringParseError(f"Score is not a number: {raw_score!r}")
    if raw_score != int(raw_score):
        raise ScoringParseError(f"Score is not a whole number: {raw_score!r}")
    score = int(raw_score)
    if not 0 <= score <= max_score:
        raise ScoringParseError(f"Score {score} is outside 0-{max_score}")

    raw_confidence = parsed.get('confidence', 0.5)
    if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, (int, float)):
        raise ScoringParseError(f"Confidence is not a number: {raw_confidence!r}")
    confidence = float(raw_confidence)
    if confidence > 1:  # some models answer in percent
        confidence = confidence / 100
    confidence = max(0.0, min(1.0, confidence))

    feedback = parsed.get('feedback') or "No feedback provided"
    if not isinstance(feedback, str):
        feedback = str(feedback)

    return {
        "score": score,
        "confidence": confidence,
        "feedback": feedback,
        "strengths": _string_list(parsed.get('strengths')),
        "weaknesses": _string_list(parsed.get('weaknesses')),
    }


class StrictScoringMixin:
    """
    score_answer() for providers that expose `_create_scoring_prompt(answer, guide, question)`
    and `_generate(prompt) -> str`. Raises ScoringError instead of inventing a score.
    """

    provider_name = "unknown"
    parse_attempts = 2

    def score_answer(self, student_answer: str, marking_guide: str, question: str = "") -> Dict[str, Any]:
        if not student_answer or not marking_guide:
            raise ScoringError("Missing student answer or marking guide")

        cached = self.response_cache.get(student_answer, marking_guide, question)
        if cached:
            return {**cached, "cached": True}

        prompt = self._create_scoring_prompt(student_answer, marking_guide, question)
        last_error: Exception = ScoringError("No attempts made")
        for attempt in range(1, self.parse_attempts + 1):
            try:
                text = self._generate(prompt)
            except Exception as e:
                raise ScoringError(f"{self.provider_name} request failed: {e}") from e
            try:
                result = parse_scoring_response(text)
            except ScoringParseError as e:
                last_error = e
                logger.warning(f"{self.provider_name}: unusable output on attempt {attempt}/{self.parse_attempts}: {e}")
                continue

            result["model_used"] = self.model
            result["scoring_method"] = self.provider_name
            self.response_cache.set(student_answer, marking_guide, question, result)
            return {**result, "cached": False}

        raise last_error
