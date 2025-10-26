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

- **Development**: `dev_key_123`
- **Testing**: `test_key_789`

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
X-API-Key: dev_key_123
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
X-API-Key: dev_key_123
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
X-API-Key: dev_key_123
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
X-API-Key: dev_key_123
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
X-API-Key: dev_key_123
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
X-API-Key: dev_key_123
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
API_KEY = "dev_key_123"

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
const API_KEY = 'dev_key_123';

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
  -H "X-API-Key: dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "student_answer": "Gravity is a force that pulls objects toward Earth.",
    "marking_guide": "Gravity is the force of attraction between masses, particularly noticeable as objects being pulled toward Earth.",
    "question_text": "What is gravity?"
  }'

# Get all questions
curl -X GET "http://localhost:5001/api/v1/questions" \
  -H "X-API-Key: dev_key_123"
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
