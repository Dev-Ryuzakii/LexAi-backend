"""
Configuration file for AI-CBT Assessment Platform
"""
import os

class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a4cb44f1bd507ee6f856d6977ffacc60'
    
    # AI Service API Keys (set these as environment variables in production)
    OLLAMA_API_KEY = os.environ.get('OLLAMA_API_KEY') or ''
    PALM_API_KEY = os.environ.get('PALM_API_KEY') or ''
    COHERE_API_KEY = os.environ.get('COHERE_API_KEY') or ''
    HUGGINGFACE_API_KEY = os.environ.get('HUGGINGFACE_API_KEY') or ''
    
    # AI Service Models
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL') or 'llama3.2:latest'
    PALM_MODEL = os.environ.get('PALM_MODEL') or 'chat-bison-001'
    COHERE_MODEL = os.environ.get('COHERE_MODEL') or 'command'
    HUGGINGFACE_MODEL = os.environ.get('HUGGINGFACE_MODEL') or 'google/flan-t5-base'
    
    # Database configuration
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'sqlite:///data/database.db'
    
    # Upload configuration
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'xlsx', 'docx'}
    
    # API configuration
    API_RATE_LIMIT = int(os.environ.get('API_RATE_LIMIT', 100))  # requests per minute
    
    @staticmethod
    def init_app(app):
        """Initialize application with configuration"""
        pass

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}