#!/bin/bash

# Exit on error
set -e

echo "Setting up XML Inspection Tool environment..."

# Function to check Python installation
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo "Python is not installed. Please install Python 3 and try again."
        exit 1
    fi

    # Check Python version
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    REQUIRED_VERSION="3.6"
    
    # Compare versions using Python itself
    if ! $PYTHON_CMD -c "import sys; exit(0 if sys.version_info >= (3, 6) else 1)"; then
        echo "Python 3.6 or higher is required. Found version $PYTHON_VERSION"
        exit 1
    fi
    echo "Using Python $PYTHON_VERSION"
}

# Function to check pip installation
check_pip() {
    if command -v pip3 &> /dev/null; then
        PIP_CMD="pip3"
    elif command -v pip &> /dev/null; then
        PIP_CMD="pip"
    else
        echo "pip is not installed. Please install pip and try again."
        exit 1
    fi
    echo "Using $PIP_CMD"
}

# Check Python and pip installations
check_python
check_pip

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv .venv
fi

# Verify virtual environment was created successfully
if [ ! -f ".venv/bin/python" ]; then
    echo "Error: Virtual environment was not created successfully."
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Verify activation
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Error: Virtual environment activation failed."
    exit 1
fi

# Upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip

# Install dependencies
echo "Installing dependencies from requirements.txt..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "requirements.txt not found. Installing basic dependencies..."
    pip install python-docx mammoth
fi

echo "Setup complete! Virtual environment is ready to use."
echo "To activate the virtual environment, run: source .venv/bin/activate"
echo "To deactivate the virtual environment, run: deactivate"
