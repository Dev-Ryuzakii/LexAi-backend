"""
AI question generation (MCQ, fill-in-the-blank and theory questions with answer keys).

Model output is never trusted, as in scoring.py: a reply only yields questions when it is
JSON, and each question is checked on its own. A question that is incomplete, ambiguous by
construction (e.g. an MCQ whose answer is not one of its options) or a duplicate is dropped;
it is never repaired by inventing an answer.

Questions are requested in batches of at most BATCH_SIZE per model call (small local models
have limited output), with the type/topic/difficulty mix planned across the whole request.
Shortfalls are retried for a bounded number of rounds.
"""
import json
import logging
import os
import re
import time
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

QUESTION_TYPES = ('MCQ', 'FILL_BLANK', 'THEORY')
DIFFICULTIES = ('easy', 'medium', 'hard')
BATCH_SIZE = 5
EXTRA_ROUNDS = 2
MAX_TOKENS = 2500
TEMPERATURE = 0.4
BLANK = '____'
MCQ_OPTIONS = 4
POINTS = {'MCQ': (1, 2), 'FILL_BLANK': (1, 2), 'THEORY': (5, 10)}
MAX_QUESTION_CHARS = 5000
MAX_FILL_ANSWER_WORDS = 6
MAX_ACCEPTED_ANSWERS = 5
MAX_COMMON_MISTAKES = 4
SIMILARITY_THRESHOLD = 0.9
# Prompt budgets: everything is still de-duplicated locally, the prompt just carries a sample.
PROMPT_AVOID_CHARS = 4000
PROMPT_AVOID_ITEM_CHARS = 200
# Mixed difficulty cycles through this pattern (roughly 25% easy, 50% medium, 25% hard).
MIXED_PATTERN = ('easy', 'medium', 'hard', 'medium')


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# No new model call is started after this many seconds, so a request ends well inside the
# HTTP server's timeout; whatever was produced so far is returned with a warning.
TIME_BUDGET_SECONDS = _env_float('GENERATION_TIME_BUDGET_SECONDS', 360)


class GenerationError(Exception):
    """Questions could not be generated (network, model or parse failure)."""


class GenerationUnavailable(GenerationError):
    """No capable provider could be reached."""


class GenerationParseError(GenerationError):
    """The provider answered, but not with usable JSON."""


class GenerationFailed(GenerationError):
    """Providers answered, but no valid question could be produced."""

    def __init__(self, message: str, reasons: List[str]):
        super().__init__(message)
        self.reasons = reasons


class InvalidQuestion(Exception):
    """One generated question failed validation (it is dropped, with this reason)."""


# --- Planning --------------------------------------------------------------------------

def _spread(total: int, names: List[str]) -> Dict[str, int]:
    """Split `total` as evenly as possible across `names` (earlier names get the remainder)."""
    base, extra = divmod(total, len(names))
    return {name: base + (1 if i < extra else 0) for i, name in enumerate(names)}


def plan_slots(needed: Dict[str, int], topics: List[str], topic_counts: Dict[str, int],
               difficulty: str, start_index: int = 0) -> List[Dict[str, str]]:
    """
    One slot (type, topic, difficulty) per question still needed. Types are interleaved so
    every batch mixes them, and each slot goes to the least-covered topic so far.
    """
    remaining = dict(needed)
    order = [t for t in QUESTION_TYPES if remaining.get(t, 0) > 0]
    counts = {t: topic_counts.get(t, 0) for t in topics}
    slots, i = [], start_index
    while any(remaining[t] > 0 for t in order):
        for qtype in order:
            if remaining[qtype] <= 0:
                continue
            topic = min(topics, key=lambda t: (counts[t], topics.index(t)))
            counts[topic] += 1
            level = MIXED_PATTERN[i % len(MIXED_PATTERN)] if difficulty == 'mixed' else difficulty
            slots.append({'type': qtype, 'topic': topic, 'difficulty': level})
            remaining[qtype] -= 1
            i += 1
    return slots


# --- Prompt ------------------------------------------------------------------------------

TYPE_RULES = {
    'MCQ': (
        'MCQ (multiple choice): exactly 4 options, all distinct, similar in length and style. Exactly ONE option is '
        'correct; the other three are plausible distractors based on real misconceptions, and none of them is '
        'partly correct. Never use "All of the above", "None of the above", "Both A and B" or similar. '
        'Do not prefix options with letters. "correct_answer" must be copied character-for-character from "options". '
        '"accepted_answers" is []. "marking_guide" is one or two sentences on why the answer is right.'
    ),
    'FILL_BLANK': (
        'FILL_BLANK (fill in the blank): "question_text" is one complete statement containing exactly one blank '
        'written as ____ (four underscores). The missing word or short phrase (at most 6 words) must be the only '
        'sensible completion, and must not appear anywhere else in the statement. "correct_answer" is that word or '
        'phrase; "accepted_answers" lists it first, followed by any equally correct alternatives (spellings, '
        'synonyms, symbols), at most 5 in total. "options" is []. "marking_guide" is one or two sentences on why '
        'the answer is right.'
    ),
    'THEORY': (
        'THEORY (written answer): a question that needs a paragraph or more (explain, describe, compare, '
        'calculate with working, evaluate). "options" is [], "correct_answer" is "" and "accepted_answers" is []. '
        '"marking_guide" is the rubric a marker uses: one creditable point per line, each ending with its marks in '
        'brackets, e.g. "- Defines photosynthesis as making food using light energy (2 marks)". The marks must '
        'add up to "suggested_points" (between 5 and 10).'
    ),
}

EXAMPLE = {
    'questions': [{
        'type': 'MCQ',
        'question_text': 'Which part of a plant cell is the site of photosynthesis?',
        'options': ['Chloroplast', 'Nucleus', 'Cell wall', 'Vacuole'],
        'correct_answer': 'Chloroplast',
        'accepted_answers': [],
        'marking_guide': 'Chloroplasts contain chlorophyll, which absorbs the light energy used in photosynthesis.',
        'explanation': 'Photosynthesis happens in the chloroplasts. The nucleus controls the cell, the cell wall gives '
                       'support and the vacuole stores cell sap.',
        'difficulty': 'easy',
        'topic': 'Photosynthesis',
        'learning_objective': 'Identify the organelle where photosynthesis takes place.',
        'common_mistakes': ['Confusing the chloroplast with the nucleus as the "control centre" of all processes'],
        'suggested_points': 1,
    }]
}


def _clip(text: str, limit: int) -> str:
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 3].rstrip() + '...'


def _avoid_block(avoid: List[str]) -> str:
    lines, used = [], 0
    for item in avoid:
        line = f'- {_clip(item, PROMPT_AVOID_ITEM_CHARS)}'
        if used + len(line) > PROMPT_AVOID_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
    return '\n'.join(lines)


def build_prompt(spec: Dict[str, Any], slots: List[Dict[str, str]], avoid: List[str]) -> str:
    level = spec.get('level') or 'not specified (pitch it at a typical secondary-school level for the subject)'
    types = [t for t in QUESTION_TYPES if any(s['type'] == t for s in slots)]
    plan = '\n'.join(f"{i}. type {s['type']}, topic \"{s['topic']}\", difficulty {s['difficulty']}"
                     for i, s in enumerate(slots, 1))
    parts = [
        'You are an experienced examiner writing questions for a school computer-based test. '
        'Teachers will publish these questions to students, so every question must be factually correct, '
        'unambiguous and have a complete answer key.',
        '',
        f"Subject: {spec['subject']}",
        f"Class/level: {level}",
        f"Topics: {', '.join(spec['topics'])}",
        '',
        f'Write exactly {len(slots)} questions, one for each line of this plan, in this order:',
        plan,
        '',
        'Rules for every question:',
        '- Match the curriculum, vocabulary and reading level of the class/level above.',
        '- Test exactly one clear idea. There must be one defensible correct answer; avoid vague words such as '
        '"usually", "best" or "most" unless the answer is unambiguous.',
        '- The question must not give away its own answer, and must not depend on another question, a diagram or '
        'an image.',
        '- Vary the thinking required across the set: recall, understanding, application and analysis. '
        'easy = recall or recognition; medium = understanding or application; hard = multi-step reasoning, '
        'analysis or evaluation.',
        '- "topic" must be copied exactly from the plan line. "difficulty" is easy, medium or hard.',
        '- "explanation" is written for the student: why the correct answer is right (and, for MCQ, why the '
        'others are wrong).',
        '- "learning_objective" is one sentence starting with a verb (Identify, Explain, Calculate, ...).',
        '- "common_mistakes" lists up to 4 typical misconceptions or weak points this question exposes.',
        '- "suggested_points": 1 or 2 for MCQ and FILL_BLANK, 5 to 10 for THEORY.',
        '',
        'Rules by question type:',
        *[f'- {TYPE_RULES[t]}' for t in types],
    ]
    if spec.get('source_material'):
        parts += ['', 'Base every question on the source material below. Do not ask about anything it does not cover.',
                  '<source_material>', spec['source_material'], '</source_material>']
    if spec.get('instructions'):
        parts += ['', "The teacher's additional instructions (follow them unless they conflict with the rules above):",
                  '<teacher_instructions>', spec['instructions'], '</teacher_instructions>']
    if avoid:
        parts += ['', 'These questions already exist. Do not repeat or rephrase them; test different facts or skills:',
                  _avoid_block(avoid)]
    parts += [
        '',
        'Reply with only a JSON object of this shape (this example shows the format, not the content):',
        json.dumps(EXAMPLE, indent=2),
        '',
        f'Your "questions" array must contain exactly {len(slots)} questions. Respond only with the JSON object.',
    ]
    return '\n'.join(parts)


# --- Parsing and validation ------------------------------------------------------------------

def parse_generation_response(text: str) -> List[Any]:
    """The list of raw question objects in a model reply, or GenerationParseError."""
    if not isinstance(text, str) or not text.strip():
        raise GenerationParseError('Empty response from model')
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find('{'), stripped.rfind('}')
        if start == -1 or end <= start:
            raise GenerationParseError('No JSON object in model response')
        try:
            parsed = json.loads(stripped[start:end + 1])
        except json.JSONDecodeError as e:
            raise GenerationParseError(f'Invalid JSON in model response: {e}') from e

    if isinstance(parsed, dict):
        if isinstance(parsed.get('questions'), list):
            return parsed['questions']
        if 'question_text' in parsed:  # a single question instead of a list
            return [parsed]
        raise GenerationParseError('Model response has no "questions" list')
    if isinstance(parsed, list):
        return parsed
    raise GenerationParseError('Model response is not a JSON object')


TYPE_ALIASES = {
    'MCQ': 'MCQ', 'MULTIPLE_CHOICE': 'MCQ', 'MULTIPLECHOICE': 'MCQ', 'MULTIPLE_CHOICE_QUESTION': 'MCQ',
    'FILL_BLANK': 'FILL_BLANK', 'FILL_IN_THE_BLANK': 'FILL_BLANK', 'FILL_IN_BLANK': 'FILL_BLANK',
    'FILLBLANK': 'FILL_BLANK', 'FILL_IN_THE_BLANKS': 'FILL_BLANK', 'FILL_THE_BLANK': 'FILL_BLANK',
    'THEORY': 'THEORY', 'ESSAY': 'THEORY',
}
BANNED_OPTION = re.compile(r'\b(all|none|both|neither)\b.*\b(above|of these|options?|answers?)\b|\bboth\s+[a-d]\s+and\s+[a-d]\b',
                           re.IGNORECASE)
OPTION_LABEL = re.compile(r'^\(?([A-Da-d])[\).:]\s+')
MARKS = re.compile(r'(\d+)\s*(?:marks?|pts?|points?)\b', re.IGNORECASE)


def _text(value: Any, field: str, required: bool = True, limit: int = MAX_QUESTION_CHARS) -> str:
    if value is None:
        value = ''
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        raise InvalidQuestion(f'{field} is not text')
    value = value.strip()
    if required and not value:
        raise InvalidQuestion(f'{field} is missing')
    if len(value) > limit:
        raise InvalidQuestion(f'{field} is too long')
    return value


def _texts(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise InvalidQuestion(f'{field} is not a list')
    out = []
    for item in value:
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            item = str(item)
        if not isinstance(item, str):
            raise InvalidQuestion(f'{field} contains a non-text item')
        if item.strip():
            out.append(item.strip())
    return out


def normalize_text(text: str) -> str:
    """Comparison key for duplicate detection."""
    text = re.sub(r'_{3,}', ' blank ', text.lower())
    text = re.sub(r'[^\w\s]', ' ', text)
    return ' '.join(text.split())


def _fold(text: str) -> str:
    return ' '.join(text.lower().split())


def _contains_phrase(haystack: str, needle: str) -> bool:
    needle = normalize_text(needle)
    return bool(needle) and re.search(rf'(?<!\w){re.escape(needle)}(?!\w)', normalize_text(haystack)) is not None


def _points(raw: Any, qtype: str, marking_guide: str) -> int:
    low, high = POINTS[qtype]
    if qtype == 'THEORY':
        marks = sum(int(m) for m in MARKS.findall(marking_guide))
        if low <= marks <= high:
            return marks  # keep the points consistent with the marking guide's split
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        try:
            raw = int(str(raw).strip())
        except (TypeError, ValueError):
            return low
    return max(low, min(high, int(raw)))


def _match_topic(raw: Any, topics: List[str]) -> str:
    value = raw.strip() if isinstance(raw, str) else ''
    folded = _fold(value)
    for topic in topics:
        if _fold(topic) == folded:
            return topic
    if folded:
        partial = [t for t in topics if _fold(t) in folded or folded in _fold(t)]
        if len(partial) == 1:
            return partial[0]
    if len(topics) == 1:
        return topics[0]
    raise InvalidQuestion(f'topic {value!r} is not one of the requested topics')


def _mcq_answer(raw_answer: str, options: List[str]) -> str:
    if raw_answer in options:
        return raw_answer
    stripped = OPTION_LABEL.sub('', raw_answer).strip()
    matches = [o for o in options if _fold(o) == _fold(stripped)]
    if len(matches) == 1:
        return matches[0]
    # A bare letter refers to a position; only read it that way when no option is that letter.
    letter = raw_answer.strip().rstrip(').:').lstrip('(')
    if len(letter) == 1 and letter.upper() in 'ABCD' and not any(_fold(o) == letter.lower() for o in options):
        return options['ABCD'.index(letter.upper())]
    raise InvalidQuestion('correct_answer is not one of the options')


def validate_question(raw: Any, spec: Dict[str, Any]) -> Dict[str, Any]:
    """A clean question in the response shape, or InvalidQuestion with the reason."""
    if not isinstance(raw, dict):
        raise InvalidQuestion('question is not an object')

    raw_type = raw.get('type')
    qtype = TYPE_ALIASES.get(re.sub(r'[\s\-]+', '_', raw_type.strip()).upper()) if isinstance(raw_type, str) else None
    if qtype is None:
        raise InvalidQuestion(f'unknown question type {raw_type!r}')
    if qtype not in spec['question_types']:
        raise InvalidQuestion(f'question type {qtype} was not requested')

    question_text = _text(raw.get('question_text'), 'question_text')
    if len(question_text) < 10:
        raise InvalidQuestion('question_text is too short')
    explanation = _text(raw.get('explanation'), 'explanation')
    marking_guide_raw = raw.get('marking_guide')
    if isinstance(marking_guide_raw, list):
        marking_guide_raw = '\n'.join(_texts(marking_guide_raw, 'marking_guide'))
    marking_guide = _text(marking_guide_raw, 'marking_guide', required=(qtype == 'THEORY'), limit=10000)

    options: List[str] = []
    correct_answer = ''
    accepted: List[str] = []

    if qtype == 'MCQ':
        options = _texts(raw.get('options'), 'options')
        if len(options) != MCQ_OPTIONS:
            raise InvalidQuestion(f'MCQ must have exactly {MCQ_OPTIONS} options, got {len(options)}')
        labels = [OPTION_LABEL.match(o) for o in options]
        had_labels = all(labels) and [m.group(1).upper() for m in labels] == list('ABCD')
        if had_labels:
            options = [OPTION_LABEL.sub('', o).strip() for o in options]
        if any(not o for o in options):
            raise InvalidQuestion('MCQ has an empty option')
        if any(len(o) > 1000 for o in options):
            raise InvalidQuestion('MCQ option is too long')
        if len({_fold(o) for o in options}) != MCQ_OPTIONS:
            raise InvalidQuestion('MCQ options are not distinct')
        if any(BANNED_OPTION.search(o) for o in options):
            raise InvalidQuestion('MCQ uses an "all/none of the above" style option')
        correct_answer = _mcq_answer(_text(raw.get('correct_answer'), 'correct_answer', limit=1000), options)
        if len(normalize_text(correct_answer)) >= 6 and _contains_phrase(question_text, correct_answer) and \
                not any(_contains_phrase(question_text, o) for o in options if o != correct_answer):
            raise InvalidQuestion('question_text gives away the correct answer')

    elif qtype == 'FILL_BLANK':
        question_text = re.sub(r'_{3,}', BLANK, question_text)
        if question_text.count(BLANK) != 1:
            raise InvalidQuestion(f'FILL_BLANK must contain exactly one blank ({BLANK}), '
                                  f'found {question_text.count(BLANK)}')
        correct_answer = _text(raw.get('correct_answer'), 'correct_answer', limit=200)
        if '_' * 3 in correct_answer:
            raise InvalidQuestion('correct_answer is a blank')
        if len(correct_answer.split()) > MAX_FILL_ANSWER_WORDS:
            raise InvalidQuestion('FILL_BLANK answer is too long to fill a blank')
        if _contains_phrase(question_text.replace(BLANK, ' '), correct_answer):
            raise InvalidQuestion('question_text gives away the correct answer')
        accepted = [correct_answer]
        for alt in _texts(raw.get('accepted_answers'), 'accepted_answers'):
            if len(alt) <= 200 and _fold(alt) not in {_fold(a) for a in accepted}:
                accepted.append(alt)
        accepted = accepted[:MAX_ACCEPTED_ANSWERS]

    if not marking_guide:
        marking_guide = explanation
    if qtype == 'THEORY':
        points = [line.strip() for line in marking_guide.splitlines() if line.strip()]
        if len(points) < 2:
            raise InvalidQuestion('THEORY marking_guide must list at least two creditable points, one per line')
        marking_guide = '\n'.join(points)

    difficulty = raw.get('difficulty')
    difficulty = difficulty.strip().lower() if isinstance(difficulty, str) else ''
    if spec['difficulty'] != 'mixed':
        difficulty = spec['difficulty']
    elif difficulty not in DIFFICULTIES:
        difficulty = 'medium'

    return {
        'type': qtype,
        'question_text': question_text,
        'options': options,
        'correct_answer': correct_answer,
        'accepted_answers': accepted,
        'marking_guide': marking_guide,
        'explanation': explanation,
        'difficulty': difficulty,
        'topic': _match_topic(raw.get('topic'), spec['topics']),
        'learning_objective': _text(raw.get('learning_objective'), 'learning_objective', required=False, limit=1000),
        'common_mistakes': [m for m in _texts(raw.get('common_mistakes'), 'common_mistakes') if len(m) <= 1000][:MAX_COMMON_MISTAKES],
        'suggested_points': _points(raw.get('suggested_points'), qtype, marking_guide),
    }


class Deduplicator:
    """Rejects questions whose text matches (or nearly matches) one already seen."""

    def __init__(self, existing: List[str]):
        self.keys: List[str] = []
        self.exact = set()
        for text in existing:
            self.add(text)

    def add(self, text: str) -> None:
        key = normalize_text(text)
        if key and key not in self.exact:
            self.exact.add(key)
            self.keys.append(key)

    def is_duplicate(self, text: str) -> bool:
        key = normalize_text(text)
        if key in self.exact:
            return True
        return any(SequenceMatcher(None, key, other).ratio() >= SIMILARITY_THRESHOLD for other in self.keys)


# --- Orchestration -------------------------------------------------------------------------

def generate(spec: Dict[str, Any], call: Callable[[str], str],
             clock: Callable[[], float] = time.monotonic) -> Dict[str, Any]:
    """
    Produce up to spec['count'] validated questions using `call(prompt) -> text`.
    `call` raises GenerationUnavailable when no provider can be reached.

    Returns {questions, warnings, requested}; raises GenerationUnavailable when no model ever
    answered, and GenerationFailed when models answered but nothing valid came back.
    """
    count = spec['count']
    targets = _spread(count, [t for t in QUESTION_TYPES if t in spec['question_types']])
    avoid = list(spec.get('avoid_questions') or [])
    # The prompt's format example is included so a model that copies it verbatim gains nothing.
    dedupe = Deduplicator(avoid + [EXAMPLE['questions'][0]['question_text']])
    accepted: List[Dict[str, Any]] = []
    reasons: List[str] = []
    warnings: List[str] = []
    answered = False
    unavailable: Optional[GenerationUnavailable] = None
    started = clock()
    slot_index = 0

    def note(reason: str) -> None:
        if reason not in reasons and len(reasons) < 50:
            reasons.append(reason)

    for round_number in range(EXTRA_ROUNDS + 1):
        have = {t: sum(1 for q in accepted if q['type'] == t) for t in targets}
        needed = {t: targets[t] - have[t] for t in targets}
        if sum(needed.values()) <= 0:
            break
        topic_counts = {t: sum(1 for q in accepted if q['topic'] == t) for t in spec['topics']}
        slots = plan_slots(needed, spec['topics'], topic_counts, spec['difficulty'], slot_index)
        slot_index += len(slots)

        for start in range(0, len(slots), BATCH_SIZE):
            if clock() - started > TIME_BUDGET_SECONDS:
                warnings.append('Stopped early because generation reached its time limit.')
                break
            batch = slots[start:start + BATCH_SIZE]
            # Questions made earlier in this request go first so the model sees them in the prompt.
            prompt = build_prompt(spec, batch, [q['question_text'] for q in accepted] + avoid)
            try:
                text = call(prompt)
            except GenerationUnavailable as e:
                unavailable = e
                break
            answered = True
            try:
                raw_questions = parse_generation_response(text)
            except GenerationParseError as e:
                logger.warning(f'Question generation: unusable model output in round {round_number + 1}: {e}')
                note(f'unusable model output: {e}')
                continue

            for raw in raw_questions:
                try:
                    question = validate_question(raw, spec)
                except InvalidQuestion as e:
                    note(str(e))
                    continue
                if have[question['type']] >= targets[question['type']]:
                    continue  # more of this type than requested
                if dedupe.is_duplicate(question['question_text']):
                    note('duplicate of an existing or already generated question')
                    continue
                dedupe.add(question['question_text'])
                accepted.append(question)
                have[question['type']] += 1
        else:
            continue
        break  # the batch loop stopped early (time limit or providers down)

    if not accepted:
        if not answered or unavailable is not None:
            raise unavailable or GenerationUnavailable('No provider could generate questions')
        raise GenerationFailed('The AI provider did not produce any valid questions', reasons)

    if len(accepted) < count:
        if unavailable is not None:
            warnings.append('The AI provider became unavailable before all questions were generated.')
        warnings.append(f'Only {len(accepted)} of {count} requested questions passed quality checks. '
                        'Generate again to get more.')
    # Present the questions grouped by type in the order MCQ, FILL_BLANK, THEORY.
    accepted.sort(key=lambda q: QUESTION_TYPES.index(q['type']))
    return {'questions': accepted, 'warnings': warnings, 'requested': count, 'rejected_reasons': reasons}
