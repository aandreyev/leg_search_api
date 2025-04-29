# XML Inspection Tool

A Python tool for parsing and analyzing DOCX files, specifically designed for legal document inspection.

## Features

- Extracts sections from DOCX files based on bolded section identifiers
- Generates AustLII URLs for legal references
- Handles tables and paragraphs in document processing
- Outputs structured JSON data

## Requirements

- Python 3.x
- python-docx library

## Installation

```bash
pip install python-docx
```

## Usage

```bash
python docx_parse.py <filename.docx>
```

The script will process the DOCX file and generate a JSON output file with the same name as the input file.

## Output

The script generates a JSON file containing:
- Section text
- Character count
- AustLII URLs for legal references 