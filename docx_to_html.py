import mammoth
import sys
import os
import json
from bs4 import BeautifulSoup

def convert_docx_to_html(docx_path, output_path=None):
    """
    Converts a DOCX file to HTML using mammoth.
    
    Args:
        docx_path (str): Path to the input DOCX file
        output_path (str, optional): Path to save the HTML output. If None, uses the same name as input with .html extension
    
    Returns:
        str: Path to the generated HTML file
    """
    if not os.path.exists(docx_path):
        print(f"Error: Input file not found at {docx_path}", file=sys.stderr)
        return None

    if output_path is None:
        output_path = os.path.splitext(docx_path)[0] + '.html'

    try:
        # Convert DOCX to HTML
        with open(docx_path, 'rb') as docx_file:
            result = mammoth.convert_to_html(docx_file)
            html = result.value
            messages = result.messages

        # Save the HTML output
        with open(output_path, 'w', encoding='utf-8') as html_file:
            html_file.write(html)

        # Print any conversion messages
        if messages:
            print("Conversion messages:")
            for message in messages:
                print(f"  - {message}")

        print(f"Successfully converted {docx_path} to {output_path}")
        return output_path

    except Exception as e:
        print(f"Error converting DOCX to HTML: {e}", file=sys.stderr)
        return None

def process_html_for_images(html_path):
    """
    Processes the HTML file to prepare it for image conversion.
    This function can be used to modify the HTML structure if needed.
    """
    if not os.path.exists(html_path):
        print(f"Error: HTML file not found at {html_path}", file=sys.stderr)
        return None

    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Add any necessary HTML processing here
        # For example, you might want to add classes or modify image tags
        
        processed_html = str(soup)
        
        # Save the processed HTML
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(processed_html)
            
        return html_path

    except Exception as e:
        print(f"Error processing HTML: {e}", file=sys.stderr)
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python docx_to_html.py itaa1997.docx [output.html]")
        sys.exit(1)

    input_docx = sys.argv[1]
    output_html = sys.argv[2] if len(sys.argv) > 2 else None

    html_path = convert_docx_to_html(input_docx, output_html)
    if html_path:
        process_html_for_images(html_path) 