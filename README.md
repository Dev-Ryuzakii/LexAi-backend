# AI-CBT API Platform

AI-powered Computer-Based Testing API for educational assessment systems.

## Overview

The AI-CBT Assessment Platform provides a comprehensive RESTful API for integrating AI-powered educational assessment capabilities into your applications. The API supports multiple AI providers including Ollama, Google PaLM, Cohere, and Hugging Face, with automatic fallback mechanisms to ensure maximum uptime.

## Features

- 🤖 **AI-Powered Scoring**: Uses Ollama AI models for intelligent answer evaluation
- 📚 **Question Management**: CRUD operations for assessment questions
- 👥 **Student Management**: Student registration and response tracking
- 🔒 **API Key Authentication**: Secure access control
- 📊 **Detailed Feedback**: Comprehensive scoring with strengths/weaknesses analysis
- 🔄 **Fallback Systems**: Multiple scoring methods for reliability
- 📈 **Rate Limiting**: Redis-based rate limiting for API protection
- 📝 **Structured Logging**: Comprehensive logging for monitoring and debugging
- 🛡️ **Security Headers**: Protection against common web vulnerabilities
- 🌐 **CORS Support**: Cross-origin resource sharing configuration
- 📦 **Database Migrations**: Alembic-based database schema management
- 📊 **Performance Monitoring**: Request/response time tracking
- 📋 **Comprehensive Documentation**: Interactive Swagger UI documentation

## Technology Stack

- **Backend**: Python, Flask, Flask-RESTX (Swagger)
- **Database**: SQLite (with SQLAlchemy ORM)
- **AI Services**: Ollama, Google PaLM, Cohere, Hugging Face Transformers
- **Caching**: Redis for rate limiting
- **Documentation**: Swagger UI for interactive API documentation
- **Logging**: Structured logging with file and console output
- **Security**: CORS, Security Headers
- **Database Management**: Alembic for migrations
- **Containerization**: Docker and Docker Compose support

## Prerequisites

- Python 3.8+
- Redis server
- Ollama (for AI scoring)
- Virtual environment (recommended)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ai-cbt-theory
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start Redis server:
   ```bash
   redis-server
   ```

5. Start Ollama (if using local AI models):
   ```bash
   ollama run llama2
   ```

## Running the Application

Start the API server:
```bash
python src/app_api.py
```

The API will be available at:
- Main Platform: http://localhost:5001/
- API Documentation: http://localhost:5001/api/v1/docs/

## API Endpoints

### Authentication

All API endpoints require authentication via API key. Include your API key in the `X-API-Key` header:

```
X-API-Key: YOUR_API_KEY_HERE
```

For testing purposes, you can use these development keys:
- `dev_key_123` - Development key
- `test_key_789` - Testing key

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

#### Submit and Score Response
```
POST /api/v1/submit-response
```
Submit and automatically score a student response.

#### Get Student Responses
```
GET /api/v1/student/{student_id}/responses
```
Retrieve all responses for a specific student.

## Rate Limiting

The API implements rate limiting using Redis with a sliding window approach:
- Default limit: 1000 requests per hour
- Rate limit is applied per API key
- Exceeding the limit returns a 429 status code

## Error Handling

The API uses standard HTTP status codes:
- 200: Success
- 201: Created
- 400: Bad Request
- 401: Unauthorized
- 404: Not Found
- 429: Rate Limit Exceeded
- 500: Internal Server Error

## Logging

Structured logging is implemented for all API requests:
- Log levels: INFO, WARNING, ERROR
- Log location: logs/api.log
- Console output also available

## Configuration

The API service can be configured through environment variables:
- `REDIS_HOST`: Redis server host (default: localhost)
- `REDIS_PORT`: Redis server port (default: 6379)
- `DATABASE_URL`: Database connection string
- `LOG_LEVEL`: Logging level (default: INFO)

## Testing

Run the API tests:
```bash
python -m pytest tests/
```

Or run the comprehensive test script:
```bash
python tests/test_api.py
```

The test suite includes:
- Health check tests
- Authentication tests
- CRUD operations for questions, students, and responses
- Rate limiting tests
- API documentation accessibility tests

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please open an issue on the repository or contact the development team.# LexAi-backend
