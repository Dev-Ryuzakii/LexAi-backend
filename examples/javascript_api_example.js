/**
 * Example script demonstrating how to use the AI-CBT API in JavaScript
 */

const BASE_URL = "http://localhost:5001/api/v1";

class AICBTApiClient {
    constructor(baseUrl = BASE_URL) {
        this.baseUrl = baseUrl;
        this.authToken = null;
        this.apiKey = null;
    }

    async registerUser(email, password) {
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

    async loginUser(email, password) {
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

    async createApiKey(email, keyName, planType = "free", rateLimit = 1000, monthlyQuota = 10000) {
        /** Create an API key using the auth token */
        const url = `${this.baseUrl}/api-keys`;
        const payload = {
            email: email,
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

    setApiKey(apiKey) {
        /** Set API key for future requests */
        this.apiKey = apiKey;
    }

    async scoreAnswer(studentAnswer, markingGuide, questionText = "") {
        /** Use the API with an API key */
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
}

// Example usage
async function main() {
    console.log("🚀 AI-CBT API Usage Example");
    console.log("=".repeat(50));

    const client = new AICBTApiClient();
    
    try {
        // User credentials
        const email = "js_example_user@test.com";
        const password = "secure_password_123";
        
        // Step 1: Register user
        console.log("1. Registering user...");
        const registerResult = await client.registerUser(email, password);
        console.log("   ✅ User registered successfully");
        
        // Step 2: Login user
        console.log("2. Logging in...");
        const loginResult = await client.loginUser(email, password);
        console.log("   ✅ Login successful");
        console.log(`   Auth token: ${loginResult.token.substring(0, 20)}...`);
        
        // Step 3: Create API key
        console.log("3. Creating API key...");
        const apiKeyResult = await client.createApiKey(email, "My JavaScript App Key", "development", 1000, 10000);
        const apiKey = apiKeyResult.api_key.api_key;
        console.log("   ✅ API key created successfully");
        console.log(`   API key: ${apiKey}`);
        
        // Set the API key for future requests
        client.setApiKey(apiKey);
        
        // Step 4: Use API with the key
        console.log("4. Using API with the key...");
        const scoreResult = await client.scoreAnswer(
            "Photosynthesis is the process by which plants convert sunlight into energy.",
            "Photosynthesis is the process used by plants and other organisms to convert light energy into chemical energy that can later be released to fuel the organisms' activities.",
            "What is photosynthesis?"
        );
        
        console.log("   ✅ API request successful");
        console.log(`   Score: ${scoreResult.data.score}`);
        console.log(`   Confidence: ${scoreResult.data.confidence}`);
        
        console.log("\n🎉 Complete flow demonstrated successfully!");
        console.log(`Your API key is: ${apiKey}`);
        console.log("Use this key in the X-API-Key header for all API requests.");
        
    } catch (error) {
        console.error("Error in example:", error);
    }
}

// Run the example if this script is executed directly
if (typeof require !== 'undefined' && require.main === module) {
    main();
}

// Export the class for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AICBTApiClient;
}