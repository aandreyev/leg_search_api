#!/bin/bash

# Step 1: Activate the virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Step 2: Start FastAPI auth server in the background
echo "Starting FastAPI auth server..."
nohup uvicorn auth_server:app --host 0.0.0.0 --port 8000 > auth_server.log 2>&1 &

# Step 3: Save the process ID so you can kill it later if needed
echo $! > fastapi_pid.txt

# Step 4: Start Streamlit app
echo "Starting Streamlit app..."
streamlit run app.py

# Step 5: (Optional) After Streamlit app stops, kill FastAPI server
echo "Shutting down FastAPI auth server..."
kill $(cat fastapi_pid.txt)
rm fastapi_pid.txt