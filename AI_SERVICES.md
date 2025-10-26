# AI Services Integration Guide

This document explains how to configure and use the multiple AI services integrated into the AI-CBT Assessment Platform.

## Supported AI Providers

The platform currently supports the following AI providers:

1. **Ollama** (default) - Local AI inference engine
2. **Google PaLM/Bard** - Google's large language models
3. **Cohere** - Advanced language models for NLP tasks
4. **Hugging Face** - Access to thousands of pre-trained models

## Configuration

To use the AI services, you need to set API keys for the cloud-based providers. This can be done in two ways:

### Method 1: Environment Variables (Recommended for Production)

Set the following environment variables:

```bash
# Google PaLM API Key
export PALM_API_KEY="your_google_palm_api_key"

# Cohere API Key
export COHERE_API_KEY="your_cohere_api_key"

# Hugging Face API Key
export HUGGINGFACE_API_KEY="your_huggingface_api_key"
```

### Method 2: Direct Configuration in Code

You can also set the API keys directly in your code before starting the application:

```python
from ai_service_manager import ai_service_manager

# Set API keys
ai_service_manager.set_api_keys({
    'palm': 'your_google_palm_api_key',
    'cohere': 'your_cohere_api_key',
    'huggingface': 'your_huggingface_api_key'
})

# Optionally set specific models
ai_service_manager.set_models({
    'palm': 'chat-bison-001',
    'cohere': 'command',
    'huggingface': 'google/flan-t5-base'
})
```

## Service Selection

The platform automatically uses a fallback chain when one service is unavailable:

1. **Active Service** (configurable)
2. Ollama (default fallback)
3. Google PaLM
4. Cohere
5. Hugging Face
6. Traditional ML model
7. Basic text similarity

You can set the active service:

```python
# Set Google PaLM as the active service
ai_service_manager.set_active_service('palm')
```

## Service Health Check

You can check the status of all AI services:

```python
# Get status of all services
status = ai_service_manager.get_service_status()
print(status)
```

## Default Models

Each service uses the following default models:

- **Ollama**: `llama3.2:latest`
- **Google PaLM**: `chat-bison-001`
- **Cohere**: `command`
- **Hugging Face**: `google/flan-t5-base`

## Usage Priority

The platform follows this priority for scoring student answers:

1. Active service (if configured and available)
2. Fallback chain through other services
3. Traditional ML model (if available)
4. Basic text similarity (as last resort)

This ensures maximum uptime and reliability for scoring student assessments.