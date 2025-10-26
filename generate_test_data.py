import pandas as pd
import os

# Sample data creation
test_data = {
    'answer': [
        'The capital of France is Paris.',
        'Water boils at 100 degrees Celsius.',
        'The Earth orbits around the Sun.'
    ],
    'score': [1, 1, 1]  # Sample scores (you might need to adjust this based on your requirements)
}

df = pd.DataFrame(test_data)

# Ensure the processed directory exists
os.makedirs('data/processed', exist_ok=True)

# Save the test data
df.to_csv('data/processed/test_data.csv', index=False)
