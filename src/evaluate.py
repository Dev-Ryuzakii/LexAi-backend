import pandas as pd
import joblib
from sklearn.metrics import mean_squared_error
from preprocessing import preprocess_text
from model import extract_features

# Load the model and vectorizers
model = joblib.load('../models/marking_model.pkl')
vectorizer_student = joblib.load('../models/vectorizer_student.pkl')
vectorizer_guide = joblib.load('../models/vectorizer_guide.pkl')


# Load test data
test_data = pd.read_csv('data/processed/test_data.csv')

# Print column names to verify
print("Columns in test_data:", test_data.columns)

# Check if required columns are present
required_columns = {'answer', 'marking_guide', 'score'}
if not required_columns.issubset(test_data.columns):
    raise ValueError(f"The required columns {required_columns} are not in the test data.")

# Preprocess test answers
test_data['cleaned_answer'] = test_data['answer'].apply(preprocess_text)
test_data['cleaned_marking_guide'] = test_data['marking_guide'].apply(preprocess_text)

# Extract features
X_test_student, _ = extract_features(test_data['cleaned_answer'], vectorizer_student)
X_test_guide, _ = extract_features(test_data['cleaned_marking_guide'], vectorizer_guide)

# Combine features
X_test_combined = pd.concat([pd.DataFrame(X_test_student.toarray()), pd.DataFrame(X_test_guide.toarray())], axis=1)

# Predict the scores
predicted_scores = model.predict(X_test_combined)

# Print types and sample values
print("True labels type:", type(test_data['score']))
print("Predicted scores type:", type(predicted_scores))
print("True labels values:", test_data['score'].head())
print("Predicted scores values:", predicted_scores[:10])

# Ensure true_labels are in the same format
true_labels = test_data['score'].astype(float)  # Ensure true_labels match the model output type

# Calculate metrics
mse = mean_squared_error(true_labels, predicted_scores)
print(f'Mean Squared Error: {mse}')
