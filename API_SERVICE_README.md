# AI-CBT Assessment API Service

## Overview

The AI-CBT Assessment API is a comprehensive RESTful service that enables developers to integrate intelligent educational assessment capabilities into their applications. Built with cutting-edge AI technology, this API provides automated scoring, detailed feedback, and seamless integration options.

## Features

- **AI-Powered Scoring**: Automatic assessment of student responses using advanced AI models
- **Multi-Provider Support**: Integration with Ollama, Google PaLM, Cohere, and Hugging Face
- **Fallback Mechanisms**: Automatic switching between AI providers for maximum reliability
- **RESTful API**: Standards-compliant API design for easy integration
- **Database Integration**: SQLite backend for storing questions, students, and responses
- **Security**: API key authentication and rate limiting
- **Scalability**: Designed for educational institutions of all sizes

## Quick Start

### Prerequisites

- Python 3.8+
- Virtual environment (recommended)
- Ollama (for local AI processing)
- API keys for external services (optional)

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ai-cbt-theory
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Initialize the database:
   ```bash
   python src/initialize_db.py
   ```

5. Start the API service:
   ```bash
   python src/app_api.py
   ```

6. Access the API at `http://localhost:5001`

## API Endpoints

### Authentication

All API endpoints require authentication via API key. Include your API key in the `X-API-Key` header:

```
X-API-Key: YOUR_API_KEY_HERE
```

For testing purposes, you can use these development keys:
- `YOUR_API_KEY` - Development key
- `YOUR_API_KEY` - Testing key

### Core Endpoints

#### Health Check
```
GET /api/v1/health
```
Check the health status of the API service.

#### Questions Management
```
GET /api/v1/questions
```
Retrieve all questions.

```
GET /api/v1/questions/{id}
```
Retrieve a specific question by ID.

```
POST /api/v1/questions
```
Create a new question.

```
PUT /api/v1/questions/{id}
```
Update an existing question.

```
DELETE /api/v1/questions/{id}
```
Delete a question.

#### Students Management
```
GET /api/v1/students
```
Retrieve all students.

```
GET /api/v1/students/{id}
```
Retrieve a specific student by ID.

```
POST /api/v1/students
```
Create a new student.

```
PUT /api/v1/students/{id}
```
Update an existing student.

```
DELETE /api/v1/students/{id}
```
Delete a student.

#### Response Scoring
```
POST /api/v1/responses/score
```
Score a student response using AI.

```
GET /api/v1/responses
```
Retrieve all responses.

```
GET /api/v1/responses/{id}
```
Retrieve a specific response by ID.

```
POST /api/v1/responses
```
Create a new response.

```
PUT /api/v1/responses/{id}
```
Update an existing response.

```
DELETE /api/v1/responses/{id}
```
Delete a response.

```
GET /api/v1/student/{student_id}/responses
```
Retrieve all responses for a specific student.

## API Response Format

All API responses follow a consistent JSON format:

```json
{
  "success": true,
  "data": {},
  "message": "Optional message"
}
```

Error responses follow this format:

```json
{
  "success": false,
  "error": "Error code",
  "message": "Detailed error message"
}
```

## Configuration

The API service can be configured through `src/config.py`. Key configuration options include:

- Database settings
- AI service API keys
- Model selection
- Rate limiting parameters

## Integration Examples

### Python Example

```python
import requests

# Set up the API client
base_url = "http://localhost:5001/api/v1"
headers = {
    "X-API-Key": "YOUR_API_KEY",
    "Content-Type": "application/json"
}

# Create a student
student_data = {
    "name": "John Doe",
    "matric_number": "MAT123456"
}

response = requests.post(
    f"{base_url}/students",
    headers=headers,
    json=student_data
)

if response.status_code == 200:
    student = response.json()
    print(f"Created student: {student['data']['name']}")
```

### JavaScript Example

```javascript
const axios = require('axios');

const api = axios.create({
  baseURL: 'http://localhost:5001/api/v1',
  headers: {
    'X-API-Key': 'YOUR_API_KEY',
    'Content-Type': 'application/json'
  }
});

// Score a student response
async function scoreResponse() {
  try {
    const response = await api.post('/responses/score', {
      student_answer: "Gravity is a force that pulls objects toward each other.",
      marking_guide: "Gravity is a fundamental force that attracts two bodies with mass toward each other. On Earth, it gives weight to physical objects and causes the ocean tides.",
      question_text: "What is gravity?"
    });
    
    console.log('Score:', response.data.data.score);
    console.log('Feedback:', response.data.data.feedback);
  } catch (error) {
    console.error('Error scoring response:', error.response.data);
  }
}
```

## Error Handling

The API uses standard HTTP status codes:

- `200` - Success
- `400` - Bad Request
- `401` - Unauthorized
- `404` - Not Found
- `500` - Internal Server Error

All errors include a JSON response with details about the error.

## Rate Limiting

The API implements rate limiting to ensure fair usage. The default limits are:

- 1000 requests per hour for development keys
- 10000 requests per hour for production keys

Exceeding these limits will result in a 429 (Too Many Requests) response.

## Security

- All API requests must be authenticated with a valid API key
- API keys should be kept secure and not shared publicly
- For production use, always use HTTPS to encrypt data in transit
- Regularly rotate API keys for enhanced security

## Troubleshooting

### Common Issues

1. **API Key Errors**: Ensure you're using a valid API key in the `X-API-Key` header
2. **Connection Refused**: Verify the API service is running on the correct port
3. **500 Errors**: Check the server logs for detailed error information

### Logging

The API service logs all requests and errors to help with debugging. Check the console output or log files for detailed information.

## Support

For support, please open an issue on the GitHub repository or contact the development team.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License.