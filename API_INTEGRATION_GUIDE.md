# AI-CBT API Integration Guide

This guide explains how to integrate the AI-CBT API into your applications.

## Authentication

The AI-CBT API supports two authentication methods:

1. **API Keys** (Recommended for production use)
2. **JWT-like Tokens** (For user authentication)

### API Key Authentication

API keys are the primary method for authenticating API requests. They are long-lived and can be generated through the user authentication flow or using the command-line tool.

To use an API key, include it in the `X-API-Key` header of your requests:

```http
X-API-Key: lexai_your_api_key_here
```

### Token Authentication

For user authentication, you can obtain a temporary JWT-like token through the login endpoint.

To use a token, include it in the `Authorization` header with the `Bearer` prefix:

```http
Authorization: Bearer auth_your_token_here
```

## Getting Started

### 1. Obtain an API Key

You can obtain an API key in two ways:

#### Option A: Through User Authentication (Recommended)

1. Register a new user account
2. Login to obtain an authentication token
3. Create an API key using the authentication token

See the [API Usage Examples](file:///Users/macbook/Ai-CBT-Theory/examples/README.md) for detailed code examples.

#### Option B: Using the Command-Line Tool

```bash
# Generate test API keys
python src/generate_api_keys.py --test

# Generate production API keys
python src/generate_api_keys.py --prod
```

### 2. Make API Requests

Once you have an API key, you can make requests to the API endpoints.

## API Endpoints

All API endpoints are available under the `/api/v1/` prefix.

### Core Endpoints

- `POST /api/v1/score` - Score a student answer
- `GET /api/v1/questions` - Get all questions
- `POST /api/v1/questions` - Create a new question
- `GET /api/v1/questions/{id}` - Get a specific question
- `PUT /api/v1/questions/{id}` - Update a specific question
- `DELETE /api/v1/questions/{id}` - Delete a specific question
- `GET /api/v1/students` - Get all students
- `POST /api/v1/students` - Create or get a student
- `GET /api/v1/students/{id}` - Get a specific student
- `PUT /api/v1/students/{id}` - Update a specific student
- `DELETE /api/v1/students/{id}` - Delete a specific student
- `GET /api/v1/responses` - Get all responses
- `POST /api/v1/responses` - Create a new response
- `GET /api/v1/responses/{id}` - Get a specific response
- `PUT /api/v1/responses/{id}` - Update a specific response
- `DELETE /api/v1/responses/{id}` - Delete a specific response
- `POST /api/v1/submit-response` - Submit and score a student response
- `GET /api/v1/student/{id}/responses` - Get all responses for a specific student

### Authentication Endpoints

- `POST /api/v1/register` - Register a new user
- `POST /api/v1/login` - Login to obtain an authentication token
- `POST /api/v1/logout` - Logout (invalidate authentication token)
- `GET /api/v1/api-keys` - List API keys for the authenticated user
- `POST /api/v1/api-keys` - Create a new API key
- `DELETE /api/v1/api-keys/{id}` - Revoke an API key

## Example Requests

### Score a Student Answer

```python
import requests

api_key = "lexai_your_api_key_here"
url = "http://localhost:5001/api/v1/score"

payload = {
    "student_answer": "Photosynthesis is the process by which plants convert sunlight into energy.",
    "marking_guide": "Photosynthesis is the process used by plants and other organisms to convert light energy into chemical energy that can later be released to fuel the organisms' activities.",
    "question_text": "What is photosynthesis?"
}

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)
result = response.json()
print(result)
```

### Create a Question

```python
import requests

api_key = "lexai_your_api_key_here"
url = "http://localhost:5001/api/v1/questions"

payload = {
    "question_text": "What is the capital of France?",
    "marking_guide": "The capital of France is Paris."
}

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)
result = response.json()
print(result)
```

### JavaScript Example

```javascript
const API_KEY = "lexai_your_api_key_here";
const BASE_URL = "http://localhost:5001/api/v1";

async function scoreAnswer(studentAnswer, markingGuide, questionText = "") {
    const url = `${BASE_URL}/score`;
    const payload = {
        student_answer: studentAnswer,
        marking_guide: markingGuide,
        question_text: questionText
    };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': API_KEY
            },
            body: JSON.stringify(payload)
        });
        return await response.json();
    } catch (error) {
        console.error('Error:', error);
        throw error;
    }
}

// Usage
scoreAnswer(
    "Photosynthesis is the process by which plants convert sunlight into energy.",
    "Photosynthesis is the process used by plants and other organisms to convert light energy into chemical energy that can later be released to fuel the organisms' activities.",
    "What is photosynthesis?"
).then(result => {
    console.log(result);
});
```

## Rate Limiting

The API implements rate limiting to ensure fair usage:

- **Development/Testing Keys**: 1,000 requests per hour
- **Production Keys**: Configurable based on your plan (default 10,000 requests per hour)

If you exceed your rate limit, you'll receive a 429 (Too Many Requests) response.

## Error Handling

The API returns standard HTTP status codes:

- `200` - Success
- `201` - Created
- `400` - Bad Request (validation errors)
- `401` - Unauthorized (missing or invalid authentication)
- `404` - Not Found
- `429` - Too Many Requests (rate limiting)
- `500` - Internal Server Error

Error responses include a JSON body with details:

```json
{
  "error": "Invalid API key",
  "message": "The provided API key is invalid or inactive"
}
```

## Best Practices

1. **Store API Keys Securely**: Never hardcode API keys in your source code. Use environment variables or secure vaults.

2. **Use Different Keys for Different Environments**: Create separate API keys for development, testing, and production.

3. **Monitor Your Usage**: Keep track of your API usage to avoid hitting rate limits.

4. **Handle Errors Gracefully**: Implement proper error handling in your applications.

5. **Use HTTPS in Production**: Always use HTTPS when connecting to the API in production environments.

6. **Rotate Keys Regularly**: Regularly rotate your API keys to maintain security.

## Support

For support, please refer to the API documentation at `/api/v1/docs/` when the service is running, or contact the AI-CBT team.