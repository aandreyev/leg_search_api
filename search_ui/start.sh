#!/bin/bash

# Simple script to start the auth server and the Streamlit UI

# Navigate to the script's directory to ensure relative paths work correctly
cd "$(dirname "$0")"

# Activate the virtual environment (assumes .venv is one level up)
echo "Activating virtual environment..."
source ../.venv/bin/activate

# Check if activation succeeded
if [ $? -ne 0 ]; then
    echo "Error: Failed to activate virtual environment. Ensure '../.venv' exists."
    exit 1
fi
echo "Virtual environment activated."

# Start the FastAPI authentication server in the background
echo "Starting authentication server (auth_server.py) in the background..."
python auth_server.py &
AUTH_SERVER_PID=$!
echo "Auth server started with PID: $AUTH_SERVER_PID"

# Give the server a moment to start up
sleep 2

# Start the Streamlit app in the foreground
echo "Starting Streamlit application (app.py)..."
streamlit run app.py

# --- Cleanup ---
# This part runs after Streamlit exits (e.g., Ctrl+C)
echo "Streamlit app finished."
echo "Attempting to stop the background auth server (PID: $AUTH_SERVER_PID)..."

# Check if the process exists before trying to kill it
if kill -0 $AUTH_SERVER_PID > /dev/null 2>&1; then
    kill $AUTH_SERVER_PID
    echo "Auth server stopped."
else
    echo "Auth server (PID: $AUTH_SERVER_PID) was already stopped."
fi

echo "Script finished."