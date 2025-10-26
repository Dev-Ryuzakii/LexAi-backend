import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer

# Ensure required resources are available
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')

def preprocess_text(text):
    """
    Preprocesses the input text by removing non-alphabetic characters,
    tokenizing, removing stopwords, and lemmatizing the tokens.

    Args:
    text (str): The text to preprocess.

    Returns:
    str: The preprocessed text.
    """
    # Remove non-alphabetic characters (keeping only letters and whitespace)
    text = re.sub(r'[^A-Za-z\s]', '', text)
    
    # Tokenize the text into words
    tokens = word_tokenize(text)
    
    # Remove stopwords (common words with little meaning)
    stop_words = set(stopwords.words('english'))
    tokens = [word for word in tokens if word.lower() not in stop_words]
    
    # Initialize the lemmatizer
    lemmatizer = WordNetLemmatizer()
    
    # Lemmatize each token (reduce to its base form)
    tokens = [lemmatizer.lemmatize(word) for word in tokens]
    
    # Join the tokens back into a single string
    return ' '.join(tokens)

# Example usage
if __name__ == "__main__":
    sample_text = "The quick brown fox jumps over the lazy dog."
    preprocessed_text = preprocess_text(sample_text)
    print("Original Text:", sample_text)
    print("Preprocessed Text:", preprocessed_text)