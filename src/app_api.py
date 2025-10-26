from flask import Flask, request, jsonify
from flask_restx import Api, Resource, fields
from api_service import register_api_routes
import logging
import os
import requests
import json
from functools import wraps
from flask_cors import CORS

# Create Flask app for API service
app = Flask(__name__)

# Enable CORS for all routes
CORS(app)

# Add security headers
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    # Modified CSP to allow Swagger UI to function properly
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "img-src 'self' data:;"
    )
    return response

app.after_request(add_security_headers)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Create Flask-RESTX API instance
api = Api(
    app,
    version='1.0.0',
    title='LexAi-API-Service',
    description='AI-powered Computer-Based Testing API for educational assessment systems',
    doc='/api/v1/docs/',
    prefix='/api/v1',
    authorizations={
        'apikey': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'X-API-Key'
        }
    },
    security='apikey'
)

# Define API models for documentation
health_model = api.model('Health', {
    'status': fields.String(description='Health status'),
    'service': fields.String(description='Service name'),
    'version': fields.String(description='API version'),
    'services': fields.Raw(description='Service statuses'),
    'timestamp': fields.String(description='Timestamp')
})

error_model = api.model('Error', {
    'error': fields.String(description='Error code'),
    'message': fields.String(description='Error message'),
    'status_code': fields.Integer(description='HTTP status code')
})

# Question models
question_input_model = api.model('QuestionInput', {
    'question_text': fields.String(required=True, description='The question text'),
    'marking_guide': fields.String(required=True, description='The marking guide for the question')
})

question_update_model = api.model('QuestionUpdate', {
    'question_text': fields.String(required=False, description='The question text'),
    'marking_guide': fields.String(required=False, description='The marking guide for the question')
})

question_model = api.model('Question', {
    'id': fields.Integer(description='Question ID'),
    'question_text': fields.String(description='The question text'),
    'marking_guide': fields.String(description='The marking guide for the question'),
    'created_at': fields.String(description='Creation timestamp')
})

questions_list_model = api.model('QuestionsList', {
    'questions': fields.List(fields.Nested(question_model)),
    'total_count': fields.Integer(description='Total number of questions'),
    'timestamp': fields.String(description='Timestamp')
})

# Student models
student_input_model = api.model('StudentInput', {
    'name': fields.String(required=True, description='Student name'),
    'matric_number': fields.String(required=True, description='Student matriculation number')
})

student_update_model = api.model('StudentUpdate', {
    'name': fields.String(required=False, description='Student name'),
    'matric_number': fields.String(required=False, description='Student matriculation number'),
    'score': fields.Integer(required=False, description='Student total score')
})

student_model = api.model('Student', {
    'id': fields.Integer(description='Student ID'),
    'name': fields.String(description='Student name'),
    'matric_number': fields.String(description='Student matriculation number'),
    'score': fields.Integer(description='Student total score'),
    'created_at': fields.String(description='Creation timestamp')
})

students_list_model = api.model('StudentsList', {
    'students': fields.List(fields.Nested(student_model)),
    'total_count': fields.Integer(description='Total number of students'),
    'timestamp': fields.String(description='Timestamp')
})

# Response models
response_input_model = api.model('ResponseInput', {
    'student_id': fields.Integer(required=True, description='ID of the student'),
    'question_id': fields.Integer(required=True, description='ID of the question'),
    'answer': fields.String(required=True, description='Student\'s answer')
})

response_update_model = api.model('ResponseUpdate', {
    'student_id': fields.Integer(required=False, description='ID of the student'),
    'question_id': fields.Integer(required=False, description='ID of the question'),
    'answer': fields.String(required=False, description='Student\'s answer'),
    'score': fields.Float(required=False, description='Response score')
})

response_model = api.model('Response', {
    'id': fields.Integer(description='Response ID'),
    'student_id': fields.Integer(description='ID of the student'),
    'question_id': fields.Integer(description='ID of the question'),
    'answer': fields.String(description='Student\'s answer'),
    'score': fields.Float(description='Response score'),
    'ai_score': fields.Float(description='AI-generated score'),
    'ai_feedback': fields.String(description='AI-generated feedback'),
    'ai_confidence': fields.Float(description='AI confidence level'),
    'created_at': fields.String(description='Creation timestamp')
})

responses_list_model = api.model('ResponsesList', {
    'responses': fields.List(fields.Nested(response_model)),
    'total_count': fields.Integer(description='Total number of responses'),
    'timestamp': fields.String(description='Timestamp')
})

# Scoring models
scoring_input_model = api.model('ScoringInput', {
    'student_answer': fields.String(required=True, description='The student\'s answer'),
    'marking_guide': fields.String(required=True, description='The marking guide'),
    'question_text': fields.String(required=False, description='The question text (optional)')
})

# Auth models
auth_register_model = api.model('AuthRegister', {
    'email': fields.String(required=True, description='User email'),
    'password': fields.String(required=True, description='User password')
})

auth_login_model = api.model('AuthLogin', {
    'email': fields.String(required=True, description='User email'),
    'password': fields.String(required=True, description='User password')
})

auth_response_model = api.model('AuthResponse', {
    'success': fields.Boolean(description='Whether the operation was successful'),
    'message': fields.String(description='Response message'),
    'token': fields.String(description='Authentication token (for login)'),
    'expires_at': fields.String(description='Token expiration time (for login)'),
    'user': fields.Raw(description='User information'),
    'timestamp': fields.String(description='Timestamp')
})

# API Key models
api_key_input_model = api.model('APIKeyInput', {
    'email': fields.String(required=True, description='User email'),
    'key_name': fields.String(required=True, description='Name for the API key'),
    'plan_type': fields.String(required=False, description='Plan type (testing, development, production)'),
    'rate_limit': fields.Integer(required=False, description='Rate limit (requests per hour)', default=1000),
    'monthly_quota': fields.Integer(required=False, description='Monthly quota (requests per month)', default=10000)
})

api_key_model = api.model('APIKey', {
    'id': fields.Integer(description='API Key ID'),
    'key_name': fields.String(description='Name of the API key'),
    'api_key': fields.String(description='The API key value'),
    'user_id': fields.Integer(description='User ID'),
    'rate_limit': fields.Integer(description='Rate limit (requests per hour)'),
    'monthly_quota': fields.Integer(description='Monthly quota (requests per month)'),
    'is_active': fields.Boolean(description='Whether the API key is active'),
    'created_at': fields.String(description='Creation timestamp')
})

api_key_list_model = api.model('APIKeyList', {
    'api_keys': fields.List(fields.Nested(api_key_model)),
    'total_count': fields.Integer(description='Total number of API keys'),
    'timestamp': fields.String(description='Timestamp')
})

api_key_response_model = api.model('APIKeyResponse', {
    'success': fields.Boolean(description='Whether the operation was successful'),
    'message': fields.String(description='Response message'),
    'api_key': fields.Nested(api_key_model),
    'timestamp': fields.String(description='Timestamp')
})

revoke_api_key_model = api.model('RevokeAPIKey', {
    'success': fields.Boolean(description='Whether the operation was successful'),
    'message': fields.String(description='Response message'),
    'api_key_id': fields.Integer(description='API Key ID that was revoked'),
    'timestamp': fields.String(description='Timestamp')
})

scoring_result_model = api.model('ScoringResult', {
    'timestamp': fields.String(description='Timestamp'),
    'request_id': fields.String(description='Request ID'),
    'success': fields.Boolean(description='Whether the request was successful'),
    'scoring_method': fields.String(description='Method used for scoring'),
    'processing_time': fields.Float(description='Processing time in seconds'),
    'model_used': fields.String(description='Model used for scoring'),
    'cached': fields.Boolean(description='Whether the result was cached'),
    'data': fields.Raw(description='Scoring data')
})

# Student responses model
student_response_model = api.model('StudentResponse', {
    'response_id': fields.Integer(description='Response ID'),
    'question': fields.Nested(question_model),
    'answer': fields.String(description='Student\'s answer'),
    'score': fields.Float(description='Response score'),
    'ai_score': fields.Float(description='AI-generated score'),
    'ai_feedback': fields.String(description='AI-generated feedback'),
    'ai_confidence': fields.Float(description='AI confidence level'),
    'ai_strengths': fields.String(description='AI-identified strengths'),
    'ai_weaknesses': fields.String(description='AI-identified weaknesses'),
    'submitted_at': fields.String(description='Submission timestamp')
})

student_responses_model = api.model('StudentResponses', {
    'student': fields.Nested(student_model),
    'responses': fields.List(fields.Nested(student_response_model)),
    'total_responses': fields.Integer(description='Total number of responses'),
    'timestamp': fields.String(description='Timestamp')
})

# Register API routes
register_api_routes(app)

@api.route('/health')
class HealthCheck(Resource):
    @api.doc('health_check')
    @api.marshal_with(health_model)
    @api.response(200, 'Success')
    @api.response(500, 'Internal Server Error')
    def get(self):
        """Simple health check for the main service"""
        # Make request to the actual health endpoint
        try:
            response = requests.get('http://localhost:5001/api/v1/health')
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    'status': 'unhealthy',
                    'service': 'AI-CBT API Platform',
                    'version': '1.0.0',
                    'services': {},
                    'timestamp': '2025-01-01T00:00:00Z'
                }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'service': 'AI-CBT API Platform',
                'version': '1.0.0',
                'services': {},
                'timestamp': '2025-01-01T00:00:00Z'
            }

@api.route('/')
class Index(Resource):
    @api.doc('api_info')
    @api.marshal_with(health_model)
    @api.response(200, 'Success')
    def get(self):
        """API Service Information
        
        Returns general information about the AI-CBT API Platform, including version, 
        description, and available services.
        
        Returns:
            dict: Service information including name, version, description and timestamp
        """
        return {
            'service': 'AI-CBT API Platform',
            'version': '1.0.0',
            'description': 'AI-powered Computer-Based Testing API for educational assessment systems',
            'services': {},
            'timestamp': '2025-01-01T00:00:00Z'
        }

# Questions endpoints
@api.route('/questions')
class QuestionsList(Resource):
    @api.doc('list_questions')
    @api.marshal_with(questions_list_model)
    @api.response(200, 'Success')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def get(self):
        """Get all available questions
        
        Retrieves a list of all questions in the system. Requires authentication with a valid API key.
        
        Returns:
            dict: A dictionary containing a list of questions, total count, and timestamp
            
        Example Response:
            {
                "questions": [
                    {
                        "id": 1,
                        "question_text": "What is photosynthesis?",
                        "marking_guide": "Detailed explanation of photosynthesis process",
                        "created_at": "2025-01-01T10:00:00"
                    }
                ],
                "total_count": 1,
                "timestamp": "2025-01-01T10:00:00"
            }
        """
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.get('http://localhost:5001/api/v1/questions', 
                                  headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500
    
    @api.doc('create_question')
    @api.expect(question_input_model)
    @api.marshal_with(question_model)
    @api.response(201, 'Created')
    @api.response(400, 'Bad Request')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def post(self):
        """Create a new question
        
        Creates a new assessment question with the provided question text and marking guide.
        Requires authentication with a valid API key.
        
        Request Body:
            {
                "question_text": "What is the capital of France?",
                "marking_guide": "The capital of France is Paris."
            }
        
        Returns:
            dict: A dictionary containing success status, message, question ID, and timestamp
            
        Example Response:
            {
                "success": true,
                "message": "Question created successfully",
                "question_id": 1,
                "timestamp": "2025-01-01T10:00:00"
            }
        """
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.post('http://localhost:5001/api/v1/questions', 
                                   headers={'X-API-Key': api_key},
                                   json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

@api.route('/questions/<int:question_id>')
@api.param('question_id', 'The question identifier')
class Question(Resource):
    @api.doc('get_question')
    @api.marshal_with(question_model)
    @api.response(200, 'Success')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def get(self, question_id):
        """Get a specific question by ID
        
        Retrieves a specific question by its ID. Requires authentication with a valid API key.
        
        Args:
            question_id (int): The unique identifier of the question to retrieve
            
        Returns:
            dict: A dictionary containing the question details and timestamp
            
        Example Response:
            {
                "question": {
                    "id": 1,
                    "question_text": "What is photosynthesis?",
                    "marking_guide": "Detailed explanation of photosynthesis process",
                    "created_at": "2025-01-01T10:00:00"
                },
                "timestamp": "2025-01-01T10:00:00"
            }
        """
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.get(f'http://localhost:5001/api/v1/questions/{question_id}', 
                                  headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500
    
    @api.doc('update_question')
    @api.expect(question_update_model)
    @api.marshal_with(question_model)
    @api.response(200, 'Success')
    @api.response(400, 'Bad Request')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def put(self, question_id):
        """Update a specific question by ID
        
        Updates a specific question by its ID with the provided fields.
        Requires authentication with a valid API key.
        
        Args:
            question_id (int): The unique identifier of the question to update
            
        Request Body (any of the following fields are optional):
            {
                "question_text": "Updated question text",
                "marking_guide": "Updated marking guide"
            }
        
        Returns:
            dict: A dictionary containing success status, message, question ID, and timestamp
            
        Example Response:
            {
                "success": true,
                "message": "Question updated successfully",
                "question_id": 1,
                "timestamp": "2025-01-01T10:00:00"
            }
        """
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.put(f'http://localhost:5001/api/v1/questions/{question_id}', 
                                  headers={'X-API-Key': api_key},
                                  json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500
    
    @api.doc('delete_question')
    @api.response(204, 'Deleted')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def delete(self, question_id):
        """Delete a specific question by ID
        
        Deletes a specific question by its ID. This will also delete all associated responses.
        Requires authentication with a valid API key.
        
        Args:
            question_id (int): The unique identifier of the question to delete
            
        Returns:
            dict: A dictionary containing success status, message, question ID, and timestamp
            
        Example Response:
            {
                "success": true,
                "message": "Question deleted successfully",
                "question_id": 1,
                "timestamp": "2025-01-01T10:00:00"
            }
        """
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.delete(f'http://localhost:5001/api/v1/questions/{question_id}', 
                                     headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

# Students endpoints
@api.route('/students')
class StudentsList(Resource):
    @api.doc('list_students')
    @api.marshal_with(students_list_model)
    @api.response(200, 'Success')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def get(self):
        """Get all students"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.get('http://localhost:5001/api/v1/students', 
                                  headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500
    
    @api.doc('create_student')
    @api.expect(student_input_model)
    @api.marshal_with(student_model)
    @api.response(201, 'Created')
    @api.response(400, 'Bad Request')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def post(self):
        """Create or get a student"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.post('http://localhost:5001/api/v1/students', 
                                   headers={'X-API-Key': api_key},
                                   json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

@api.route('/students/<int:student_id>')
@api.param('student_id', 'The student identifier')
class Student(Resource):
    @api.doc('get_student')
    @api.marshal_with(student_model)
    @api.response(200, 'Success')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def get(self, student_id):
        """Get a specific student by ID"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.get(f'http://localhost:5001/api/v1/students/{student_id}', 
                                  headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500
    
    @api.doc('update_student')
    @api.expect(student_update_model)
    @api.marshal_with(student_model)
    @api.response(200, 'Success')
    @api.response(400, 'Bad Request')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def put(self, student_id):
        """Update a specific student by ID"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.put(f'http://localhost:5001/api/v1/students/{student_id}', 
                                  headers={'X-API-Key': api_key},
                                  json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500
    
    @api.doc('delete_student')
    @api.response(204, 'Deleted')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def delete(self, student_id):
        """Delete a specific student by ID"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.delete(f'http://localhost:5001/api/v1/students/{student_id}', 
                                     headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

# Responses endpoints
@api.route('/responses')
class ResponsesList(Resource):
    @api.doc('list_responses')
    @api.marshal_with(responses_list_model)
    @api.response(200, 'Success')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def get(self):
        """Get all responses"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.get('http://localhost:5001/api/v1/responses', 
                                  headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500
    
    @api.doc('create_response')
    @api.expect(response_input_model)
    @api.marshal_with(response_model)
    @api.response(201, 'Created')
    @api.response(400, 'Bad Request')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def post(self):
        """Create a new response"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.post('http://localhost:5001/api/v1/responses', 
                                   headers={'X-API-Key': api_key},
                                   json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

@api.route('/responses/<int:response_id>')
@api.param('response_id', 'The response identifier')
class Response(Resource):
    @api.doc('get_response')
    @api.marshal_with(response_model)
    @api.response(200, 'Success')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def get(self, response_id):
        """Get a specific response by ID"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.get(f'http://localhost:5001/api/v1/responses/{response_id}', 
                                  headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500
    
    @api.doc('update_response')
    @api.expect(response_update_model)
    @api.marshal_with(response_model)
    @api.response(200, 'Success')
    @api.response(400, 'Bad Request')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def put(self, response_id):
        """Update a specific response by ID"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.put(f'http://localhost:5001/api/v1/responses/{response_id}', 
                                  headers={'X-API-Key': api_key},
                                  json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500
    
    @api.doc('delete_response')
    @api.response(204, 'Deleted')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def delete(self, response_id):
        """Delete a specific response by ID"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.delete(f'http://localhost:5001/api/v1/responses/{response_id}', 
                                     headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

# Scoring endpoint
@api.route('/score')
class ScoreAnswer(Resource):
    @api.doc('score_answer')
    @api.expect(scoring_input_model)
    @api.marshal_with(scoring_result_model)
    @api.response(200, 'Success')
    @api.response(400, 'Bad Request')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def post(self):
        """Score a student answer against a marking guide"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.post('http://localhost:5001/api/v1/score', 
                                   headers={'X-API-Key': api_key},
                                   json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

# Submit response endpoint
@api.route('/submit-response')
class SubmitResponse(Resource):
    @api.doc('submit_response')
    @api.expect(response_input_model)
    @api.marshal_with(scoring_result_model)
    @api.response(201, 'Created')
    @api.response(400, 'Bad Request')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def post(self):
        """Submit and score a student response"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.post('http://localhost:5001/api/v1/submit-response', 
                                   headers={'X-API-Key': api_key},
                                   json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

# Student responses endpoint
@api.route('/student/<int:student_id>/responses')
@api.param('student_id', 'The student identifier')
class StudentResponses(Resource):
    @api.doc('get_student_responses')
    @api.marshal_with(student_responses_model)
    @api.response(200, 'Success')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def get(self, student_id):
        """Get all responses for a specific student"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.get(f'http://localhost:5001/api/v1/student/{student_id}/responses', 
                                  headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

# Auth endpoints
@api.route('/register')
class AuthRegister(Resource):
    @api.doc('register_user')
    @api.expect(auth_register_model)
    @api.marshal_with(auth_response_model)
    @api.response(201, 'Created')
    @api.response(400, 'Bad Request')
    @api.response(409, 'Conflict')
    @api.response(500, 'Internal Server Error')
    def post(self):
        """Register a new user"""
        # Make request to the actual endpoint
        try:
            response = requests.post('http://localhost:5001/api/v1/register', 
                                   json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

@api.route('/login')
class AuthLogin(Resource):
    @api.doc('login_user')
    @api.expect(auth_login_model)
    @api.marshal_with(auth_response_model)
    @api.response(200, 'Success')
    @api.response(400, 'Bad Request')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def post(self):
        """Login a user and generate an authentication token"""
        # Make request to the actual endpoint
        try:
            response = requests.post('http://localhost:5001/api/v1/login', 
                                   json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

@api.route('/logout')
class AuthLogout(Resource):
    @api.doc('logout_user')
    @api.marshal_with(auth_response_model)
    @api.response(200, 'Success')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def post(self):
        """Logout a user by revoking their authentication token"""
        # Make request to the actual endpoint
        try:
            # Get the Authorization header from the request
            auth_header = request.headers.get('Authorization', '')
            response = requests.post('http://localhost:5001/api/v1/logout', 
                                   headers={'Authorization': auth_header})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

# API Key Management endpoints
@api.route('/api-keys')
class APIKeyList(Resource):
    @api.doc('list_api_keys')
    @api.marshal_with(api_key_list_model)
    @api.response(200, 'Success')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def get(self):
        """Get all API keys for the authenticated user"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.get('http://localhost:5001/api/v1/api-keys', 
                                  headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500
    
    @api.doc('create_api_key')
    @api.expect(api_key_input_model)
    @api.marshal_with(api_key_response_model)
    @api.response(201, 'Created')
    @api.response(400, 'Bad Request')
    @api.response(401, 'Unauthorized')
    @api.response(500, 'Internal Server Error')
    def post(self):
        """Create a new API key"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.post('http://localhost:5001/api/v1/api-keys', 
                                   headers={'X-API-Key': api_key},
                                   json=request.json)
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

@api.route('/api-keys/<int:key_id>')
@api.param('key_id', 'The API key identifier')
class APIKeyResource(Resource):
    @api.doc('revoke_api_key')
    @api.marshal_with(revoke_api_key_model)
    @api.response(200, 'Success')
    @api.response(401, 'Unauthorized')
    @api.response(404, 'Not Found')
    @api.response(500, 'Internal Server Error')
    def delete(self, key_id):
        """Revoke an API key"""
        # Make request to the actual endpoint
        try:
            api_key = request.headers.get('X-API-Key', 'dev_key_123')
            response = requests.delete(f'http://localhost:5001/api/v1/api-keys/{key_id}', 
                                     headers={'X-API-Key': api_key})
            return response.json(), response.status_code
        except Exception as e:
            return {'error': 'Internal server error'}, 500

# Remove the error handlers as they conflict with Flask-RESTX
# The default error handling of Flask-RESTX will be used instead

if __name__ == '__main__':
    print("🚀 AI-CBT API Platform Starting...")
    print("=" * 50)
    print("🌐 Main Platform: http://localhost:5001/")
    print("📖 API Documentation: http://localhost:5001/api/v1/docs/")
    print("=" * 50)
    print("✅ Ready to serve intelligent assessment APIs!")
    
    app.run(debug=True, host='0.0.0.0', port=5001)