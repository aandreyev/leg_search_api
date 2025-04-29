# XML Inspection Tool

A comprehensive toolchain for processing legal documents from RTF to HTML with image conversion capabilities.

## Workflow

1. **RTF to DOCX Conversion**
   - Uses Microsoft Word to convert RTF files to DOCX format
   - This step is performed manually using MS Word

2. **DOCX to HTML Conversion**
   - Uses mammoth to convert DOCX files to HTML format
   - Handles document structure and formatting

3. **HTML Parsing**
   - Parses the HTML output using html_parser.py
   - Extracts and structures legal document sections

4. **Image Processing**
   - Converts EMF images to PNG format using convert_emf_images.py
   - Requires LibreOffice for image conversion
   - Ensures proper display of images in HTML output

## Prerequisites

- Python 3.6 or higher
- LibreOffice (for image conversion)
  - macOS: `brew install --cask libreoffice`
  - Windows: Download from [LibreOffice website](https://www.libreoffice.org/download/download/)
  - Linux: `sudo apt-get install libreoffice` or equivalent for your distribution

## Components

- `docx_parse.py`: Initial DOCX parsing functionality
- `html_parser.py`: HTML parsing and section extraction
- `convert_emf_images.py`: Image format conversion
- `rtf_parse_unrtf.py`: RTF parsing utilities

## Requirements

- python-docx
- mammoth
- beautifulsoup4
- lxml
- requests
- Additional dependencies listed in requirements.txt

## Installation

```bash
# Install LibreOffice (required for image conversion)
# macOS:
brew install --cask libreoffice

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

1. Convert RTF to DOCX using Microsoft Word
2. Run the conversion pipeline:
   ```bash
   # Convert DOCX to HTML
   python -m mammoth input.docx output.html

   # Parse HTML and extract sections
   python html_parser.py output.html

   # Convert EMF images to PNG
   python convert_emf_images.py
   ```

## Output

The toolchain generates:
- HTML files with proper formatting
- JSON files containing structured section data
- PNG images converted from EMF format
- Processed HTML files ready for display

## Notes

- The RTF to DOCX conversion step requires Microsoft Word
- Image conversion requires LibreOffice to be installed and accessible from PATH
- The toolchain is optimized for legal document processing 