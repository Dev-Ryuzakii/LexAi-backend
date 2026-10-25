import hashlib
import hmac
import os
from datetime import datetime

from sqlalchemy import (
    create_engine, event, func, Column, Integer, String, Text, Boolean, ForeignKey, Float, DateTime,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from werkzeug.security import generate_password_hash, check_password_hash

Base = declarative_base()

# Grading states for a stored response. Only GRADED responses count towards a student's total.
GRADED = 'graded'
NEEDS_REVIEW = 'needs_review'
GRADING_STATUSES = (GRADED, NEEDS_REVIEW)


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, nullable=False)
    # Nullable only for legacy rows created without a password; such users cannot log in.
    password_hash = Column(String(255), nullable=True)
    plan_type = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    api_keys = relationship("APIKey", back_populates="user")
    auth_tokens = relationship("AuthToken", back_populates="user")


class Question(Base):
    __tablename__ = 'questions'
    id = Column(Integer, primary_key=True, index=True)
    # Every query filters on owner_id. Legacy rows without an owner are not visible to anyone.
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    question_text = Column(Text, nullable=False)
    marking_guide = Column(Text, nullable=False)
    max_score = Column(Float, nullable=False, default=5.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Student(Base):
    __tablename__ = 'students'
    __table_args__ = (UniqueConstraint('owner_id', 'matric_number', name='uq_students_owner_matric'),)
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    matric_number = Column(String(50), nullable=False)
    # Derived from graded responses by recalculate_student_score(); never incremented in place.
    score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    responses = relationship("Response", back_populates="student")


class Response(Base):
    __tablename__ = 'responses'
    __table_args__ = (UniqueConstraint('student_id', 'question_id', name='uq_responses_student_question'),)
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    student_id = Column(Integer, ForeignKey('students.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    answer = Column(Text, nullable=False)
    score = Column(Float, default=0.0)
    max_score = Column(Float, default=5.0)
    grading_status = Column(String(20), default=GRADED, nullable=False)
    scoring_method = Column(String(50), nullable=True)
    corrected_answer = Column(Text, nullable=True)
    is_correct = Column(Boolean, default=False)
    ai_score = Column(Float, nullable=True)
    lecturer_score = Column(Float, nullable=True)
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


class APIKey(Base):
    __tablename__ = 'api_keys'
    id = Column(Integer, primary_key=True, index=True)
    key_name = Column(String(100), nullable=False)
    # Only a SHA-256 digest is stored; the plaintext key is shown once, at creation.
    key_hash = Column(String(64), unique=True, nullable=False)
    key_prefix = Column(String(20), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    plan_type = Column(String(20), nullable=True)
    rate_limit = Column(Integer, default=1000)  # requests per hour
    monthly_quota = Column(Integer, default=10000)  # requests per month
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="api_keys")


class AuthToken(Base):
    __tablename__ = 'auth_tokens'
    id = Column(Integer, primary_key=True, index=True)
    # SHA-256 digest of the bearer token.
    token = Column(String(128), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    user = relationship("User", back_populates="auth_tokens")


# --- Credentials -----------------------------------------------------------------

def hash_password(password: str) -> str:
    return generate_password_hash(password)


def _is_legacy_password_hash(hashed: str) -> bool:
    # Old format: "<sha256 hex>:<salt hex>"
    return '$' not in hashed and hashed.count(':') == 1


def verify_password(password: str, hashed) -> bool:
    if not hashed:
        return False
    if _is_legacy_password_hash(hashed):
        digest, salt = hashed.split(':')
        return hmac.compare_digest(hashlib.sha256((password + salt).encode()).hexdigest(), digest)
    return check_password_hash(hashed, password)


def password_needs_rehash(hashed: str) -> bool:
    return bool(hashed) and _is_legacy_password_hash(hashed)


def hash_secret(value: str) -> str:
    """Digest for high-entropy secrets (API keys, bearer tokens). Lookup is by digest."""
    return hashlib.sha256(value.encode()).hexdigest()


# --- Grading -----------------------------------------------------------------------

def effective_score(response: Response) -> float:
    if response.final_score is not None:
        return response.final_score
    return response.score or 0.0


def recalculate_student_score(db, student_id: int) -> float:
    """Recompute a student's total from their graded responses. Caller commits."""
    total = db.query(func.coalesce(func.sum(func.coalesce(Response.final_score, Response.score)), 0.0)).filter(
        Response.student_id == student_id,
        Response.grading_status == GRADED,
    ).scalar()
    db.query(Student).filter(Student.id == student_id).update({Student.score: float(total)})
    return float(total)


# --- Engine ------------------------------------------------------------------------

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///data/database.db')


def _make_engine(url: str):
    connect_args = {}
    if url.startswith('sqlite'):
        path = url.split('///', 1)[-1]
        if path and path != ':memory:':
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        connect_args['check_same_thread'] = False
    eng = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    if url.startswith('sqlite'):
        @event.listens_for(eng, 'connect')
        def _enable_foreign_keys(dbapi_connection, _):
            dbapi_connection.execute('PRAGMA foreign_keys=ON')
    return eng


engine = _make_engine(DATABASE_URL)
# expire_on_commit=False: objects stay readable after commit, so building the HTTP
# response never triggers a lazy reload on a closed session.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


def init_db():
    """Create tables directly from the models. For local development and tests; use Alembic elsewhere."""
    Base.metadata.create_all(bind=engine)
