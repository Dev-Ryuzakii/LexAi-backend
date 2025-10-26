from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LinearRegression
import joblib

Base = declarative_base()

class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    matric_number = Column(String, unique=True, index=True)
    score = Column(Float, default=0.0)

class Question(Base):
    __tablename__ = 'questions'
    id = Column(Integer, primary_key=True, index=True)
    question_text = Column(String)
    marking_guide = Column(String)

class Response(Base):
    __tablename__ = 'responses'
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False)
    question_id = Column(Integer, nullable=False)
    answer = Column(String, nullable=False)
    score = Column(Float, default=0.0)  # Default value for score
    ai_score = Column(Float, nullable=True)  # Optional field
    lecturer_score = Column(Float, nullable=True)  # Optional field

DATABASE_URL = 'sqlite:///data/database.db'
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Add a sample student if the table is empty
    with SessionLocal() as db:
        if not db.query(Student).first():
            sample_student = Student(name="John Doe", matric_number="123456")
            db.add(sample_student)
            db.commit()

def extract_features(corpus, vectorizer=None):
    if vectorizer is None:
        vectorizer = TfidfVectorizer()
        X = vectorizer.fit_transform(corpus)
    else:
        X = vectorizer.transform(corpus)
    return X, vectorizer

def train_model(X, y):
    model = LinearRegression()
    model.fit(X, y)
    return model

def save_model(model, vectorizer, model_path, vectorizer_path):
    joblib.dump(model, model_path)
    joblib.dump(vectorizer, vectorizer_path)

if __name__ == "__main__":
    init_db()
