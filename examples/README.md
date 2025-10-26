# API Usage Examples

This directory contains example code demonstrating how to use the AI-CBT API in different programming languages.

## Python Example

The [python_api_example.py](file:///Users/macbook/Ai-CBT-Theory/examples/python_api_example.py) script demonstrates the complete flow:

1. User registration
2. User login to obtain an authentication token
3. Creation of an API key using the authentication token
4. Using the API key to make requests to the API

To run the Python example:

```bash
cd /Users/macbook/Ai-CBT-Theory
source venv/bin/activate
python examples/python_api_example.py
```

## JavaScript Example

The [javascript_api_example.js](file:///Users/macbook/Ai-CBT-Theory/examples/javascript_api_example.js) script demonstrates the same flow in JavaScript:

1. User registration
2. User login to obtain an authentication token
3. Creation of an API key using the authentication token
4. Using the API key to make requests to the API

To run the JavaScript example:

```bash
cd /Users/macbook/Ai-CBT-Theory
node examples/javascript_api_example.js
```

## Authentication Flow

The authentication flow for the AI-CBT API is as follows:

1. **Registration**: Users register with an email and password
2. **Login**: Users login with their credentials to receive a temporary authentication token
3. **API Key Creation**: Users create long-lived API keys using their authentication token
4. **API Usage**: All subsequent API requests use the API key in the `X-API-Key` header

## API Key Management

API keys can also be generated using the command-line script:

```bash
# Generate test API keys
python src/generate_api_keys.py --test

# Generate production API keys
python src/generate_api_keys.py --prod

# List existing API keys
python src/generate_api_keys.py --list
```

## Security Best Practices

When using the API in production, follow these security best practices:

1. Store API keys securely (environment variables, secure vaults)
2. Use different API keys for different environments (development, testing, production)
3. Rotate API keys regularly
4. Monitor API key usage and revoke unused keys
5. Use HTTPS in production environments
6. Never commit API keys to version control