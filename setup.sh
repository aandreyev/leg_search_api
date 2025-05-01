#!/bin/bash

echo "Setting up XML Inspection Tool environment..."

# --- Check for Homebrew and LibreOffice --- 
echo "Checking for dependencies (Homebrew, LibreOffice)..."

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "Error: Homebrew is not installed. Please install it first: https://brew.sh/" 
    exit 1
fi
echo "Homebrew found."

# Check for LibreOffice via Homebrew Cask
if ! brew list --cask libreoffice &> /dev/null; then
    echo "LibreOffice not found via Homebrew Cask. Attempting to install..."
    brew install --cask libreoffice
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install LibreOffice via Homebrew." 
        exit 1
    fi
    echo "LibreOffice installed successfully."
else
    echo "LibreOffice already installed via Homebrew Cask."
fi
# --- End Dependency Check ---

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

echo "Setup complete! Virtual environment is ready to use."
echo "To activate the virtual environment, run: source .venv/bin/activate"
echo "To deactivate the virtual environment, run: deactivate"
