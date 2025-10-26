from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, ForeignKey, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import IntegrityError
from datetime import datetime
import hashlib
import secrets

Base = declarative_base()

class Question(Base):
    __tablename__ = 'questions'
    id = Column(Integer, primary_key=True, index=True)
    question_text = Column(Text, nullable=False)
    marking_guide = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    matric_number = Column(String(50), unique=True, nullable=False)
    score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    responses = relationship("Response", back_populates="student")

class Response(Base):
    __tablename__ = 'responses'
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey('students.id'))
    question_id = Column(Integer, ForeignKey('questions.id'))
    answer = Column(Text, nullable=False)
    score = Column(Float, default=0.0)
    corrected_answer = Column(Text, nullable=True)
    is_correct = Column(Boolean, default=False)
    ai_score = Column(Float, default=0.0)
    lecturer_score = Column(Float, default=0.0)
    ai_feedback = Column(Text, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    ai_strengths = Column(Text, nullable=True)
    ai_weaknesses = Column(Text, nullable=True)
    admin_approved = Column(Boolean, default=False)
    final_score = Column(Float, nullable=True)
    admin_comments = Column(Text, nullable=True)
    is_processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    student = relationship("Student", back_populates="responses")
    question = relationship("Question")

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, nullable=False)
    # Added password field for authentication
    password_hash = Column(String(128), nullable=False)
    plan_type = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    api_keys = relationship("APIKey", back_populates="user")
    # Relationship to auth tokens
    auth_tokens = relationship("AuthToken", back_populates="user")

class APIKey(Base):
    __tablename__ = 'api_keys'
    id = Column(Integer, primary_key=True, index=True)
    key_name = Column(String(100), nullable=False)
    api_key = Column(String(100), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'))
    rate_limit = Column(Integer, default=1000)  # requests per hour
    monthly_quota = Column(Integer, default=10000)  # requests per month
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="api_keys")

# New model for authentication tokens
class AuthToken(Base):
    __tablename__ = 'auth_tokens'
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(128), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'))
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    user = relationship("User", back_populates="auth_tokens")

# Utility functions for password hashing
def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with a salt"""
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{password_hash}:{salt}"

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    if ':' not in hashed:
        return False
    password_hash, salt = hashed.split(':')
    return hashlib.sha256((password + salt).encode()).hexdigest() == password_hash

    
DATABASE_URL = 'sqlite:///data/database.db'
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    if not db.query(Question).first():
        sample_question = Question(question_text="What is a computer?", marking_guide="A computer is an electronic device...")
        db.add(sample_question)
        db.commit()
    db.close()