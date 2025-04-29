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
   - Ensures proper display of images in HTML output

## Components

- `docx_parse.py`: Initial DOCX parsing functionality
- `html_parser.py`: HTML parsing and section extraction
- `convert_emf_images.py`: Image format conversion
- `rtf_parse_unrtf.py`: RTF parsing utilities

## Requirements

- Python 3.x
- python-docx
- mammoth
- Additional dependencies listed in requirements.txt

## Installation

```bash
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
- Image conversion requires proper EMF to PNG conversion tools
- The toolchain is optimized for legal document processing 