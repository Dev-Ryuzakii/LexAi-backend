> **Legacy document.** Use [API_INTEGRATION_GUIDE.md](API_INTEGRATION_GUIDE.md) and [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for the current Cencori-backed API and key flow.

# API Usage Examples

This document provides examples of how to use the AI-CBT API in both Python and JavaScript.

## Python Example

```python
import requests
import json

# API base URL
BASE_URL = "http://localhost:5001/api/v1"

class AICBTClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.api_key = None
        self.session = requests.Session()
    
    def register(self, email, password):
        """Register a new user"""
        url = f"{self.base_url}/register"
        payload = {
            "email": email,
            "password": password
        }
        response = self.session.post(url, json=payload)
        return response.json()
    
    def login(self, email, password):
        """Login and get authentication token"""
        url = f"{self.base_url}/login"
        payload = {
            "email": email,
            "password": password
        }
        response = self.session.post(url, json=payload)
        data = response.json()
        
        if response.status_code == 200:
            # Set the auth token for future requests
            self.session.headers.update({
                "Authorization": f"Bearer {data['token']}"
            })
        
        return data
    
    def create_api_key(self, key_name, plan_type="free", rate_limit=1000, monthly_quota=10000):
        """Create an API key for making requests"""
        url = f"{self.base_url}/api-keys"
        payload = {
            "email": self.session.headers.get("Authorization", "").split()[-1] if "Authorization" in self.session.headers else "",
            "key_name": key_name,
            "plan_type": plan_type,
            "rate_limit": rate_limit,
            "monthly_quota": monthly_quota
        }
        response = self.session.post(url, json=payload)
        return response.json()
    
    def list_api_keys(self):
        """List all API keys for the authenticated user"""
        url = f"{self.base_url}/api-keys"
        response = self.session.get(url)
        return response.json()
    
    def set_api_key(self, api_key):
        """Set API key for future requests"""
        self.api_key = api_key
        self.session.headers.update({
            "X-API-Key": api_key
        })
    
    def score_answer(self, student_answer, marking_guide, question_text=""):
        """Score a student answer against a marking guide"""
        url = f"{self.base_url}/score"
        payload = {
            "student_answer": student_answer,
            "marking_guide": marking_guide,
            "question_text": question_text
        }
        response = self.session.post(url, json=payload)
        return response.json()
    
    def create_question(self, question_text, marking_guide):
        """Create a new question"""
        url = f"{self.base_url}/questions"
        payload = {
            "question_text": question_text,
            "marking_guide": marking_guide
        }
        response = self.session.post(url, json=payload)
        return response.json()

# Example usage
if __name__ == "__main__":
    # Initialize client
    client = AICBTClient()
    
    # Register a new user
    print("Registering user...")
    register_result = client.register("user@example.com", "securepassword123")
    print(f"Registration result: {json.dumps(register_result, indent=2)}")
    
    # Login
    print("\nLogging in...")
    login_result = client.login("user@example.com", "securepassword123")
    print(f"Login result: {json.dumps(login_result, indent=2)}")
    
    # Create an API key
    print("\nCreating API key...")
    api_key_result = client.create_api_key("My First API Key", "development", 1000, 10000)
    print(f"API key creation result: {json.dumps(api_key_result, indent=2)}")
    
    # Set the API key for future requests
    if 'api_key' in api_key_result:
        client.set_api_key(api_key_result['api_key']['api_key'])
    
    # Now we can use the API with the API key
    print("\nScoring an answer...")
    score_result = client.score_answer(
        student_answer="Photosynthesis is the process by which plants convert sunlight into energy.",
        marking_guide="Photosynthesis is the process used by plants and other organisms to convert light energy into chemical energy that can later be released to fuel the organisms' activities.",
        question_text="What is photosynthesis?"
    )
    print(f"Scoring result: {json.dumps(score_result, indent=2)}")
    
    # Create a question
    print("\nCreating a question...")
    question_result = client.create_question(
        question_text="What is the capital of France?",
        marking_guide="The capital of France is Paris."
    )
    print(f"Question creation result: {json.dumps(question_result, indent=2)}")
```

## JavaScript Example

```javascript
// API base URL
const BASE_URL = "http://localhost:5001/api/v1";

class AICBTClient {
    constructor(baseUrl = BASE_URL) {
        this.baseUrl = baseUrl;
        this.apiKey = null;
        this.authToken = null;
    }
    
    async register(email, password) {
        /** Register a new user */
        const url = `${this.baseUrl}/register`;
        const payload = {
            email: email,
            password: password
        };
        
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            return await response.json();
        } catch (error) {
            console.error('Registration error:', error);
            throw error;
        }
    }
    
    async login(email, password) {
        /** Login and get authentication token */
        const url = `${this.baseUrl}/login`;
        const payload = {
            email: email,
            password: password
        };
        
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            
            if (response.ok) {
                // Store the auth token for future requests
                this.authToken = data.token;
            }
            
            return data;
        } catch (error) {
            console.error('Login error:', error);
            throw error;
        }
    }
    
    async createApiKey(keyName, planType = "free", rateLimit = 1000, monthlyQuota = 10000) {
        /** Create an API key for making requests */
        const url = `${this.baseUrl}/api-keys`;
        const payload = {
            email: "user@example.com", // In a real app, you'd get this from the auth context
            key_name: keyName,
            plan_type: planType,
            rate_limit: rateLimit,
            monthly_quota: monthlyQuota
        };
        
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.authToken}`
                },
                body: JSON.stringify(payload)
            });
            return await response.json();
        } catch (error) {
            console.error('API key creation error:', error);
            throw error;
        }
    }
    
    async listApiKeys() {
        /** List all API keys for the authenticated user */
        const url = `${this.baseUrl}/api-keys`;
        
        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${this.authToken}`
                }
            });
            return await response.json();
        } catch (error) {
            console.error('List API keys error:', error);
            throw error;
        }
    }
    
    setApiKey(apiKey) {
        /** Set API key for future requests */
        this.apiKey = apiKey;
    }
    
    async scoreAnswer(studentAnswer, markingGuide, questionText = "") {
        /** Score a student answer against a marking guide */
        const url = `${this.baseUrl}/score`;
        const payload = {
            student_answer: studentAnswer,
            marking_guide: markingGuide,
            question_text: questionText
        };
        
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                },
                body: JSON.stringify(payload)
            });
            return await response.json();
        } catch (error) {
            console.error('Scoring error:', error);
            throw error;
        }
    }
    
    async createQuestion(questionText, markingGuide) {
        /** Create a new question */
        const url = `${this.baseUrl}/questions`;
        const payload = {
            question_text: questionText,
            marking_guide: markingGuide
        };
        
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': this.apiKey
                },
                body: JSON.stringify(payload)
            });
            return await response.json();
        } catch (error) {
            console.error('Question creation error:', error);
            throw error;
        }
    }
}

// Example usage
async function example() {
    const client = new AICBTClient();
    
    try {
        // Register a new user
        console.log("Registering user...");
        const registerResult = await client.register("user@example.com", "securepassword123");
        console.log("Registration result:", JSON.stringify(registerResult, null, 2));
        
        // Login
        console.log("\nLogging in...");
        const loginResult = await client.login("user@example.com", "securepassword123");
        console.log("Login result:", JSON.stringify(loginResult, null, 2));
        
        // Create an API key
        console.log("\nCreating API key...");
        const apiKeyResult = await client.createApiKey("My First API Key", "development", 1000, 10000);
        console.log("API key creation result:", JSON.stringify(apiKeyResult, null, 2));
        
        // Set the API key for future requests
        if (apiKeyResult.api_key) {
            client.setApiKey(apiKeyResult.api_key.api_key);
        }
        
        // Now we can use the API with the API key
        console.log("\nScoring an answer...");
        const scoreResult = await client.scoreAnswer(
            "Photosynthesis is the process by which plants convert sunlight into energy.",
            "Photosynthesis is the process used by plants and other organisms to convert light energy into chemical energy that can later be released to fuel the organisms' activities.",
            "What is photosynthesis?"
        );
        console.log("Scoring result:", JSON.stringify(scoreResult, null, 2));
        
        // Create a question
        console.log("\nCreating a question...");
        const questionResult = await client.createQuestion(
            "What is the capital of France?",
            "The capital of France is Paris."
        );
        console.log("Question creation result:", JSON.stringify(questionResult, null, 2));
        
    } catch (error) {
        console.error("Error in example:", error);
    }
}

// Run the example
// example();
```

## API Key Management

Users can also generate API keys directly using the `generate_api_keys.py` script:

```bash
# Generate test API keys
python src/generate_api_keys.py --test

# Generate production API keys
python src/generate_api_keys.py --prod

# List existing API keys
python src/generate_api_keys.py --list

# Generate both test and production API keys
python src/generate_api_keys.py --all
```

## Authentication Flow

1. **Registration**: Users register with email and password
2. **Login**: Users login to receive an authentication token
3. **API Key Creation**: Users create API keys for their applications
4. **API Usage**: Users make API requests using their API keys in the `X-API-Key` header

## Security Best Practices

1. Store API keys securely (environment variables, secure vaults)
2. Use different API keys for different environments (development, testing, production)
3. Rotate API keys regularly
4. Monitor API key usage and revoke unused keys
5. Use HTTPS in production environments

## Error Handling

Both examples include basic error handling. In production code, you should implement more robust error handling including:

- Network timeouts
- Rate limiting responses
- Authentication errors
- Validation errors
- Server errors