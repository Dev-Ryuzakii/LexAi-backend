#!/bin/bash

# Ollama Setup Script for AI-CBT-Theory

echo "🧠 AI-CBT-Theory Ollama Setup Script"
echo "===================================="

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is not installed."
    echo ""
    echo "Please install Ollama first:"
    echo "📥 Visit: https://ollama.ai/download"
    echo ""
    echo "For macOS: curl https://ollama.ai/install.sh | sh"
    echo "For Linux: curl https://ollama.ai/install.sh | sh"
    echo "For Windows: Download from https://ollama.ai/download"
    echo ""
    exit 1
fi

echo "✅ Ollama is installed!"

# Check if Ollama service is running
if ! curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "🚀 Starting Ollama service..."
    ollama serve &
    sleep 5
else
    echo "✅ Ollama service is running!"
fi

# List available models
echo ""
echo "📋 Available models:"
ollama list

echo ""
echo "🤖 Recommended models for educational scoring:"
echo ""
echo "1. llama2 (Default) - Good balance of performance and accuracy"
echo "2. mistral - Fast and efficient"
echo "3. codellama - Good for technical subjects"
echo "4. llama2:13b - Higher accuracy but requires more resources"

echo ""
read -p "🔽 Which model would you like to install? (default: llama2): " model_choice

if [ -z "$model_choice" ]; then
    model_choice="llama2"
fi

echo "📦 Pulling model: $model_choice"
ollama pull $model_choice

if [ $? -eq 0 ]; then
    echo "✅ Model $model_choice installed successfully!"
    
    # Update the Ollama service configuration
    echo ""
    echo "🔧 Updating Ollama configuration in the project..."
    
    # Create or update config file
    cat > ../src/ollama_config.py << EOF
# Ollama Configuration for AI-CBT-Theory
OLLAMA_MODEL = "$model_choice"
OLLAMA_BASE_URL = "http://localhost:11434"

# You can change these settings:
# - OLLAMA_MODEL: The model to use for scoring
# - OLLAMA_BASE_URL: Ollama server URL (change if running remotely)
EOF
    
    echo "✅ Configuration saved to src/ollama_config.py"
    
else
    echo "❌ Failed to install model $model_choice"
    exit 1
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Make sure Ollama service is running: ollama serve"
echo "2. Run the database migration: python src/migrate_db.py"
echo "3. Install Python dependencies: pip install -r requirements.txt"
echo "4. Start the Flask app: python src/app.py"
echo ""
echo "🔍 To check Ollama status, visit: http://localhost:5000/ollama-status"
echo ""
echo "🚨 Note: Make sure to keep Ollama running in the background!"
echo "   You can start it with: ollama serve"
