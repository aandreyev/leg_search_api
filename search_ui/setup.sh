#!/bin/bash

# FIRST! chmod +x setup.sh
# run with ./setup.sh

# Step 1: Create a virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Step 2: Activate the virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Step 3: Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Step 4: Install dependencies
echo "Installing requirements..."
pip install -r requirements.txt

# Step 5: Done
echo "✅ Virtual environment is ready and requirements are installed."
echo "To activate it later, run: source venv/bin/activate"