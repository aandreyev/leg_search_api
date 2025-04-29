#!/bin/bash

echo "Setting up XML Inspection Tool environment..."

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

echo "Setup complete! Virtual environment is ready to use."
echo "To activate the virtual environment, run: source .venv/bin/activate"
echo "To deactivate the virtual environment, run: deactivate"
