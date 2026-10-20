# AI-CBT API Documentation

## Overview

The AI-CBT Assessment Platform provides a comprehensive RESTful API for integrating AI-powered educational assessment capabilities into your applications. The API supports multiple AI providers including Ollama, Google PaLM, Cohere, and Hugging Face, with automatic fallback mechanisms to ensure maximum uptime.

## Features
- 🤖 **AI-Powered Scoring**: Uses Ollama AI models for intelligent answer evaluation
- 📚 **Question Management**: CRUD operations for assessment questions
- 👥 **Student Management**: Student registration and response tracking
- 🔒 **API Key Authentication**: Secure access control
- 📊 **Detailed Feedback**: Comprehensive scoring with strengths/weaknesses analysis
- 🔄 **Fallback Systems**: Multiple scoring methods for reliability

## Base URL
```
http://localhost:5001/api/v1
```

## Authentication

All API endpoints (except `/api/v1/health` and `/api/v1/docs`) require authentication via API key. You can provide the API key in two ways:

1. **Header**: `X-API-Key: your_api_key`
2. **Query Parameter**: `?api_key=your_api_key`

### Available API Keys (Development)

- **Development**: `YOUR_API_KEY`
- **Testing**: `YOUR_API_KEY`

For production use, please generate your own API keys through the admin panel.

### AI Service Configuration

The platform supports multiple AI providers with the following priority order:

1. **Active Service** (configurable)
2. Ollama (default fallback)
3. Google PaLM
4. Cohere
5. Hugging Face
6. Traditional ML model
7. Basic text similarity

To configure cloud-based AI services, set the appropriate API keys in the environment variables or through the admin configuration panel.

## API Endpoints

### 1. Health Check
```http
GET /api/v1/health
```
Check API service status and availability.

**Response:**
```
{
  "status": "healthy",
  "timestamp": "2025-07-21T18:45:00",
  "version": "1.0.0",
  "services": {
    "ollama": true,
    "database": true
  }
}
```

### 2. Score Answer
```http
POST /api/v1/score
```
Score a student answer against a marking guide using AI.

**Headers:**
```
X-API-Key: YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**
``json
{
  "student_answer": "Photosynthesis is the process by which plants make food using sunlight and carbon dioxide.",
  "marking_guide": "Photosynthesis is the process where plants convert light energy into chemical energy using chlorophyll, water, and carbon dioxide to produce glucose and oxygen.",
  "question_text": "Explain the process of photosynthesis."
}
```

**Response:**
```json
{
  "timestamp": "2025-07-21T18:45:00",
  "request_id": "uuid-here",
  "success": true,
  "scoring_method": "ollama",
  "data": {
    "score": 4,
    "confidence": 0.85,
    "feedback": "Good understanding of photosynthesis. Mentioned key components but could include more detail about oxygen production.",
    "strengths": ["Correctly identified sunlight as energy source", "Mentioned carbon dioxide"],
    "weaknesses": ["Did not mention oxygen as byproduct", "Missing role of chlorophyll"]
  }
}
```

### 3. Get Questions
```http
GET /api/v1/questions
```
Retrieve all available assessment questions.

**Headers:**
```
X-API-Key: YOUR_API_KEY
```

**Response:**
```json
{
  "questions": [
    {
      "id": 1,
      "question_text": "Explain the process of photosynthesis.",
      "marking_guide": "Detailed marking rubric...",
      "created_at": "2025-07-21T10:00:00"
    }
  ],
  "total_count": 1,
  "timestamp": "2025-07-21T18:45:00"
}
```

### 4. Create Question
```http
POST /api/v1/questions
```
Create a new assessment question.

**Headers:**
```
X-API-Key: YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**
```json
{
  "question_text": "What is the capital of France?",
  "marking_guide": "The capital of France is Paris. Accept variations like 'Paris, France' or 'Paris is the capital'."
}
```

**Response:**
```json
{
  "success": true,
  "message": "Question created successfully",
  "question_id": 2,
  "timestamp": "2025-07-21T18:45:00"
}
```

### 5. Create/Get Student
```http
POST /api/v1/students
```
Create a new student or retrieve existing student information.

**Headers:**
```
X-API-Key: YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**
```json
{
  "name": "John Doe",
  "matric_number": "A12345678"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Student created successfully",
  "student_id": 1,
  "student": {
    "id": 1,
    "name": "John Doe",
    "matric_number": "A12345678",
    "score": 0
  },
  "timestamp": "2025-07-21T18:45:00"
}
```

### 6. Submit Response
```http
POST /api/v1/submit-response
```
Submit and automatically score a student response.

**Headers:**
```
X-API-Key: YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**
```json
{
  "student_id": 1,
  "question_id": 1,
  "answer": "Photosynthesis is how plants make food from sunlight."
}
```

**Response:**
```json
{
  "success": true,
  "message": "Response submitted and scored successfully",
  "response_id": 1,
  "scoring": {
    "score": 3,
    "max_score": 5,
    "feedback": "Basic understanding shown. Consider including more scientific details.",
    "confidence": 0.75,
    "strengths": ["Correct basic concept"],
    "weaknesses": ["Lacks scientific terminology", "Missing key processes"],
    "method": "ollama"
  },
  "student_total_score": 3,
  "timestamp": "2025-07-21T18:45:00"
}
```

### 7. Get Student Responses
```http
GET /api/v1/student/{student_id}/responses
```
Retrieve all responses for a specific student.

**Headers:**
```
X-API-Key: YOUR_API_KEY
```

**Response:**
```json
{
  "student": {
    "id": 1,
    "name": "John Doe",
    "matric_number": "A12345678",
    "total_score": 3
  },
  "responses": [
    {
      "response_id": 1,
      "question": {
        "id": 1,
        "text": "Explain photosynthesis.",
        "marking_guide": "..."
      },
      "answer": "Photosynthesis is how plants make food from sunlight.",
      "score": 3,
      "ai_feedback": "Basic understanding shown...",
      "ai_confidence": 0.75,
      "submitted_at": "2025-07-21T18:45:00"
    }
  ],
  "total_responses": 1,
  "timestamp": "2025-07-21T18:45:00"
}
```

### 8. Generate Questions
```http
POST /api/v1/generate-questions
```
Generate exam questions (multiple choice, fill-in-the-blank and theory) with answer keys, marking guides
and explanations, for a teacher to preview, edit and publish. Nothing is stored.

Only providers that can write long structured output are used: Ollama (default model `llama3.2:latest`)
and Cohere (when `COHERE_API_KEY` is set). There is no non-AI fallback.

**Headers:**
```
X-API-Key: YOUR_API_KEY
Content-Type: application/json
Idempotency-Key: optional-unique-key   (recommended: retries replay the first result)
```

**Request Body:**
| Field | Type | Required | Notes |
|---|---|---|---|
| `subject` | string | yes | at most 200 characters |
| `topics` | string[] | yes | 1-10 items, each at most 200 characters |
| `level` | string | no | at most 100 characters, e.g. `"JSS 2"`, `"SS 3"`, `"100 Level"` |
| `count` | integer | yes | 1-30 |
| `question_types` | string[] | yes | non-empty subset of `MCQ`, `FILL_BLANK`, `THEORY` |
| `difficulty` | string | no | `easy`, `medium`, `hard` or `mixed` (default `mixed`) |
| `instructions` | string | no | teacher's extra guidance, at most 2000 characters |
| `source_material` | string | no | notes to base the questions on, at most 20000 characters |
| `avoid_questions` | string[] | no | existing questions not to duplicate; at most 100 items, each at most 1000 characters |

```json
{
  "subject": "Basic Science",
  "topics": ["Photosynthesis", "Plant cells"],
  "level": "JSS 2",
  "count": 10,
  "question_types": ["MCQ", "FILL_BLANK", "THEORY"],
  "difficulty": "mixed",
  "instructions": "Use everyday Nigerian examples where possible.",
  "avoid_questions": ["What is photosynthesis?"]
}
```

**Response (200):**
```json
{
  "success": true,
  "request_id": "uuid-here",
  "timestamp": "2026-10-20T10:00:00",
  "processing_time": 41.27,
  "model_used": "llama3.2:latest",
  "provider": "ollama",
  "data": {
    "requested": 10,
    "generated": 10,
    "warnings": [],
    "questions": [
      {
        "type": "MCQ",
        "question_text": "Which part of a plant cell contains chlorophyll?",
        "options": ["Chloroplast", "Nucleus", "Cell wall", "Vacuole"],
        "correct_answer": "Chloroplast",
        "accepted_answers": [],
        "marking_guide": "Chloroplasts contain chlorophyll, the pigment that absorbs light.",
        "explanation": "Chlorophyll is found in chloroplasts. The nucleus controls the cell, the cell wall gives support and the vacuole stores cell sap.",
        "difficulty": "easy",
        "topic": "Plant cells",
        "learning_objective": "Identify the organelle that contains chlorophyll.",
        "common_mistakes": ["Thinking the nucleus carries out photosynthesis"],
        "suggested_points": 1
      },
      {
        "type": "FILL_BLANK",
        "question_text": "The gas released by plants during photosynthesis is ____.",
        "options": [],
        "correct_answer": "oxygen",
        "accepted_answers": ["oxygen", "O2"],
        "marking_guide": "Photosynthesis splits water and releases oxygen.",
        "explanation": "Plants take in carbon dioxide and give out oxygen during photosynthesis.",
        "difficulty": "medium",
        "topic": "Photosynthesis",
        "learning_objective": "State the products of photosynthesis.",
        "common_mistakes": ["Answering carbon dioxide, which plants take in"],
        "suggested_points": 1
      },
      {
        "type": "THEORY",
        "question_text": "Explain three ways a leaf is adapted for photosynthesis.",
        "options": [],
        "correct_answer": "",
        "accepted_answers": [],
        "marking_guide": "- Broad, flat surface to absorb more light (2 marks)\n- Thin, so gases diffuse a short distance (2 marks)\n- Stomata allow carbon dioxide in and oxygen out (2 marks)",
        "explanation": "A leaf is broad to trap light, thin for fast diffusion and has stomata for gas exchange.",
        "difficulty": "hard",
        "topic": "Photosynthesis",
        "learning_objective": "Explain how leaf structure supports photosynthesis.",
        "common_mistakes": ["Listing features without explaining how they help"],
        "suggested_points": 6
      }
    ]
  }
}
```

**Guarantees for every returned question:**
- `MCQ`: exactly 4 distinct, non-empty options; `correct_answer` is exactly one of them; no "all/none of the above" options; `accepted_answers` is `[]`.
- `FILL_BLANK`: `question_text` contains exactly one blank written as `____` (four underscores); `correct_answer` is the primary answer and `accepted_answers` lists it first plus up to 4 alternatives; `options` is `[]`.
- `THEORY`: `correct_answer` is `""`, `options` and `accepted_answers` are `[]`; `marking_guide` lists at least two creditable points, one per line, with their marks.
- `suggested_points` is 1-2 for MCQ and FILL_BLANK and 5-10 for THEORY; `difficulty` is `easy`, `medium` or `hard`; `topic` is one of the requested topics; `common_mistakes` has at most 4 items.
- Questions that fail these checks, or that duplicate `avoid_questions` or another generated question, are dropped, never repaired. Questions are still AI-written: a teacher should review them before publishing.

**How it works:** questions are requested from the model in batches of at most 5, with question types,
topics and difficulty spread evenly across the request. Shortfalls are retried up to two more rounds.
If fewer than `count` questions pass the checks, the response is still 200, with `generated < requested`
and an explanation in `warnings`. Questions are returned grouped by type (MCQ, then FILL_BLANK, then THEORY).

**Latency:** each batch is one model call. With Ollama on a GPU expect roughly 10-30 seconds per batch of
5; on a CPU it can be 1-3 minutes per batch. Set client timeouts accordingly (at least 10 minutes for 30
questions). No new model call starts after `GENERATION_TIME_BUDGET_SECONDS` (default 360); questions made
by then are returned with a warning.

**Usage:** the request counts as one unit per generated question (at least one) for usage analytics and
the monthly quota.

**Errors:**
| Status | Code | When |
|---|---|---|
| 400 | `VAL_001` / `VAL_002` | invalid body; `details.validation_errors` lists the fields |
| 401 | `AUTH_001` / `AUTH_002` | missing or invalid credentials |
| 422 | `GEN_002` | the provider answered but no valid questions could be produced; `details.reasons` lists why questions were rejected |
| 429 | `RATE_001` / `RATE_002` | rate limit or monthly quota exceeded |
| 503 | `GEN_001` | "Question generation is unavailable right now": no capable provider could be reached (see `Retry-After`) |

**Configuration (environment variables):**
| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.2:latest` | model used for grading and generation |
| `OLLAMA_GENERATION_TIMEOUT` | `180` | seconds to wait for one generation call |
| `OLLAMA_GENERATION_NUM_CTX` | `8192` | context window requested from Ollama for generation |
| `GENERATION_TIME_BUDGET_SECONDS` | `360` | no new model call starts after this long |
| `GUNICORN_TIMEOUT` (Docker) | `600` | worker timeout; must exceed the generation budget plus one call |

## Error Responses

### Authentication Error (401)
```json
{
  "error": "Invalid or missing API key",
  "message": "Please provide a valid API key in X-API-Key header or api_key parameter"
}
```

### Validation Error (400)
```json
{
  "error": "Missing required fields",
  "message": "Both student_answer and marking_guide are required"
}
```

### Not Found Error (404)
```json
{
  "error": "Student not found"
}
```

### Server Error (500)
```json
{
  "error": "Internal server error",
  "message": "Detailed error description"
}
```

## Integration Examples

### Python Example
```python
import requests
import json

# Configuration
API_BASE = "http://localhost:5001/api/v1"
API_KEY = "YOUR_API_KEY"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# 1. Create a student
student_data = {
    "name": "Alice Smith",
    "matric_number": "B98765432"
}

response = requests.post(f"{API_BASE}/students", 
                        headers=headers, 
                        json=student_data)
student = response.json()
student_id = student['student_id']

# 2. Create a question
question_data = {
    "question_text": "What is machine learning?",
    "marking_guide": "Machine learning is a subset of AI that enables computers to learn without explicit programming."
}

response = requests.post(f"{API_BASE}/questions", 
                        headers=headers, 
                        json=question_data)
question = response.json()
question_id = question['question_id']

# 3. Submit and score a response
submission_data = {
    "student_id": student_id,
    "question_id": question_id,
    "answer": "Machine learning helps computers learn from data automatically."
}

response = requests.post(f"{API_BASE}/submit-response", 
                        headers=headers, 
                        json=submission_data)
result = response.json()
print(f"Score: {result['scoring']['score']}/5")
print(f"Feedback: {result['scoring']['feedback']}")
```

### JavaScript/Node.js Example
```javascript
const axios = require('axios');

const API_BASE = 'http://localhost:5001/api/v1';
const API_KEY = 'YOUR_API_KEY';

const headers = {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json'
};

async function scoreAnswer(studentAnswer, markingGuide, questionText = '') {
    try {
        const response = await axios.post(`${API_BASE}/score`, {
            student_answer: studentAnswer,
            marking_guide: markingGuide,
            question_text: questionText
        }, { headers });
        
        return response.data;
    } catch (error) {
        console.error('Error scoring answer:', error.response.data);
        throw error;
    }
}

// Usage
scoreAnswer(
    "The water cycle involves evaporation, condensation, and precipitation.",
    "The water cycle is the continuous movement of water through evaporation, condensation, precipitation, and collection.",
    "Describe the water cycle."
).then(result => {
    console.log('Scoring Result:', result);
});
```

### cURL Examples
```bash
# Health check
curl -X GET "http://localhost:5001/api/v1/health"

# Score an answer
curl -X POST "http://localhost:5001/api/v1/score" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "student_answer": "Gravity is a force that pulls objects toward Earth.",
    "marking_guide": "Gravity is the force of attraction between masses, particularly noticeable as objects being pulled toward Earth.",
    "question_text": "What is gravity?"
  }'

# Get all questions
curl -X GET "http://localhost:5001/api/v1/questions" \
  -H "X-API-Key: YOUR_API_KEY"
```

## Use Cases

### 1. Learning Management Systems (LMS)
Integrate AI-powered assessment into existing LMS platforms for automatic grading and detailed feedback.

### 2. Educational Apps
Add intelligent tutoring capabilities to mobile or web applications.

### 3. Online Course Platforms
Provide instant feedback and scoring for course assessments.

### 4. Corporate Training Systems
Assess employee knowledge and provide personalized feedback.

### 5. Research Applications
Analyze learning patterns and assessment effectiveness.

## Best Practices

1. **Rate Limiting**: Implement rate limiting on your client side to avoid overwhelming the API
2. **Error Handling**: Always handle potential API errors gracefully
3. **Caching**: Cache frequently accessed data like questions to reduce API calls
4. **Monitoring**: Monitor API usage and response times
5. **Security**: Store API keys securely and rotate them regularly

## Support and Documentation

- **API Documentation**: `GET /api/v1/docs`
- **Health Status**: `GET /api/v1/health`
- **GitHub Repository**: [Your repo URL]
- **Support Email**: [Your support email]

## Changelog

### Version 1.0.0
- Initial API release
- Basic CRUD operations for questions and students
- AI-powered scoring with Ollama integration
- Comprehensive error handling and documentation
