import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
import nltk
from nltk.corpus import stopwords

# Download NLTK data (only needs to be done once)
nltk.download('stopwords')

# Sample data for fitting the vectorizer
# Replace this with actual text data if you have a dataset
sample_data = [
    "This is the first sample text.",
    "Here's another example of a text sample.",
    "Text data for fitting the vectorizer and transforming new inputs."
]

# Define the vectorizer, including preprocessing options like stopwords
vectorizer = TfidfVectorizer(stop_words=stopwords.words('english'))

# Fit the vectorizer to the sample data
vectorizer.fit(sample_data)

# Save the vectorizer to a file as 'vectorizer.pkl'
with open('vectorizer.pkl', 'wb') as f:
    pickle.dump(vectorizer, f)

print("Vectorizer has been saved as 'vectorizer.pkl'")
