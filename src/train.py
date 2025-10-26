import pandas as pd
import nltk
import os
import joblib
from model import extract_features, train_model, save_model
from preprocessing import preprocess_text

# Download the necessary NLTK resources
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')
nltk.download('averaged_perceptron_tagger')

# Create the models directory if it doesn't exist
os.makedirs('models', exist_ok=True)

# File path for the data
file_path = '../data/raw/student_answers.csv'

# Check if the file exists
if not os.path.isfile(file_path):
    raise FileNotFoundError(f"The file {file_path} does not exist.")

# Load data
data = pd.read_csv(file_path)

# Preprocess text data
data['cleaned_answer'] = data['student_answer'].apply(preprocess_text)
data['cleaned_marking_guide'] = data['marking_guide'].apply(preprocess_text)

# Extract features
X_student, vectorizer_student = extract_features(data['cleaned_answer'])
X_guide, vectorizer_guide = extract_features(data['cleaned_marking_guide'])

# Combine features
X_combined = pd.concat([pd.DataFrame(X_student.toarray()), pd.DataFrame(X_guide.toarray())], axis=1)

# Train model
y = data['score']
model = train_model(X_combined, y)

# Save model and vectorizers
save_model(model, vectorizer_student, '../models/marking_model.pkl', '../models/vectorizer_student.pkl')
joblib.dump(vectorizer_guide, '../models/vectorizer_guide.pkl')
