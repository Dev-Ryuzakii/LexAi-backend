# Ollama Integration Guide for AI-CBT Platform

## Overview

This guide provides detailed instructions for setting up and using Ollama with the AI-CBT Assessment Platform. Ollama enables local AI processing without requiring internet connectivity, making it ideal for educational environments with limited network access.

## Prerequisites

- Python 3.8+
- Ollama (latest version)
- Virtual environment (recommended)

## Installation

### 1. Install Ollama

Visit [https://ollama.ai](https://ollama.ai) and download the appropriate version for your operating system.

### 2. Pull Required Models

The AI-CBT platform works with several Ollama models. Pull at least one of these models:

```bash
# For general assessment scoring (recommended)
ollama pull llama2

# For more advanced reasoning
ollama pull mistral

# For lightweight processing
ollama pull gemma:2b
```

### 3. Clone and Set Up the AI-CBT Platform

```bash
git clone <repository-url>
cd ai-cbt-theory
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Initialize the Database

```bash
python src/initialize_db.py
```

### 5. Configure Ollama Settings

Edit `src/config.py` to set your preferred Ollama model:

```python
OLLAMA_MODEL = "llama2"  # or "mistral", "gemma:2b", etc.
OLLAMA_BASE_URL = "http://localhost:11434"  # Default Ollama endpoint
```

### 6. Start the API Service

```bash
python src/app_api.py
```

The service will be available at `http://localhost:5001`

## Testing Ollama Integration

### Using the API

Once the service is running, you can test the Ollama integration through the API:

```bash
curl -X POST http://localhost:5001/api/v1/responses/score \
  -H "X-API-Key: dev_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "student_answer": "Gravity is the force that pulls objects toward the Earth.",
    "marking_guide": "Gravity is a natural phenomenon by which all things with mass or energy are brought toward one another. On Earth, gravity gives weight to physical objects and causes the ocean tides.",
    "question_text": "Explain what gravity is."
  }'
```

### Using the Test Script

The platform includes a test script specifically for Ollama:

```bash
python src/test_ollama.py
```

This script will:
1. Verify Ollama is running
2. Test the connection to your configured model
3. Run sample assessments
4. Display scoring results and feedback

## Model Selection Guide

### Llama2
- **Best for**: General purpose assessment scoring
- **Strengths**: Balanced reasoning and language understanding
- **Requirements**: 4GB+ RAM

### Mistral
- **Best for**: Complex reasoning and detailed feedback
- **Strengths**: Advanced logical thinking
- **Requirements**: 8GB+ RAM

### Gemma (2B)
- **Best for**: Lightweight installations
- **Strengths**: Fast processing with minimal resources
- **Requirements**: 2GB+ RAM

## Troubleshooting

### Common Issues

1. **Ollama Not Found**
   ```
   Error: Cannot connect to Ollama service
   ```
   Solution: Ensure Ollama is installed and running. Check that the service is accessible at `http://localhost:11434`.

2. **Model Not Found**
   ```
   Error: Model 'llama2' not found
   ```
   Solution: Pull the required model using `ollama pull llama2`.

3. **Insufficient Memory**
   ```
   Error: CUDA out of memory
   ```
   Solution: Use a lighter model like Gemma, or ensure your system has adequate RAM.

4. **API Key Error**
   ```
   {"error": "Missing API key"}
   ```
   Solution: Include a valid API key in your requests using the `X-API-Key` header.

### Verifying Ollama Installation

```bash
# Check if Ollama is running
ollama --version

# List available models
ollama list

# Test a model directly
ollama run llama2 "Explain photosynthesis in simple terms"
```

## Performance Optimization

### For Better Scoring Accuracy

1. Use more capable models like Llama2 or Mistral
2. Provide detailed marking guides
3. Include specific question context

### For Faster Processing

1. Use lightweight models like Gemma
2. Ensure adequate system resources
3. Close unnecessary applications

## Security Considerations

- Ollama runs locally, ensuring data privacy
- All API requests require authentication
- No data is sent to external servers when using Ollama

## Advanced Configuration

### Custom Ollama Prompts

The platform uses customizable prompts for scoring. These can be modified in `src/ollama_service.py` to fine-tune the assessment behavior.

### Model Parameters

Adjust model parameters in `src/config.py`:

```python
OLLAMA_MODEL_PARAMS = {
    "temperature": 0.7,
    "top_p": 0.9,
    "repeat_penalty": 1.2
}
```

## Integration with Educational Platforms

The AI-CBT API can be easily integrated with existing educational platforms through its RESTful interface. See `API_DOCUMENTATION.md` for complete API details.

## Support

For issues with Ollama integration, please:
1. Verify your Ollama installation
2. Check the model is properly pulled
3. Review the platform logs for detailed error messages
4. Open an issue on the GitHub repository if problems persist

## Contributing

Contributions to improve Ollama integration are welcome:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request