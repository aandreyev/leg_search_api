import re
from docx import Document
import sys # Import sys module
import json # Import json module
import os # Import os module
# from docx.shared import Pt # If checking font size needed
from docx.document import Document as _Document # To allow isinstance checks
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph

# --- Configuration ---
AUSTLII_BASE_URL = "https://classic.austlii.edu.au/au/legis/cth/consol_act/itaa1997240/" # Adjust if needed

def generate_austlii_url(section_id):
    """Converts a section ID like '6-23' to an AustLII URL path like 's6.23.html' and joins with base."""
    if not AUSTLII_BASE_URL:
        return None # Return None if base URL is not set
    try:
        path_part = section_id.replace('-', '.')
        url_path = f"s{path_part}.html"
        return AUSTLII_BASE_URL + url_path
    except Exception:
        return None # Handle potential errors during conversion gracefully

def linearize_table(table):
    """Linearizes a docx table row by row for embedding."""
    linearized_rows = []
    for row in table.rows:
        cell_texts = [cell.text.strip() for cell in row.cells]
        row_text = " | ".join(cell_texts)
        linearized_rows.append(f"Table Row: {row_text}")
    return "\n".join(linearized_rows)

def extract_docx_sections(docx_path):
    """
    Extracts sections from a DOCX file based on bolded 'XX-XXX Title' pattern.
    """
    try:
        document = Document(docx_path)
    except Exception as e:
        print(f"Error opening DOCX file '{docx_path}': {e}")
        return {}

    # Regex for the section start pattern
    section_pattern = re.compile(r"^\s*(\d+-\d+)\s+.*") # Allow optional leading space

    sections = {}
    current_section_id = None
    current_section_content = []

    # Iterate through paragraphs and tables in document order
    # Use iter_inner_content() to get Paragraphs and Tables
    # Note: Need to handle potential low-level elements if using .body iteration directly
    # body_elements = document.element.body # Access body element
    # for child in body_elements:
    #     if isinstance(child, CT_P):
    #         para = Paragraph(child, document) 
    #         # Process paragraph
    #     elif isinstance(child, CT_Tbl):
    #         table = Table(child, document)
    #         # Process table
    
    for element in document.iter_inner_content():
        
        if isinstance(element, Paragraph):
            para = element # Rename for clarity within this block
            # Get text, preserving internal whitespace potentially important for run mapping
            para_text = para.text 
            para_text_stripped = para_text.strip()
            match = section_pattern.match(para_text_stripped)

            # --- Check for Section Start --- (Logic adapted from previous version)
            is_section_start = False
            if match:
                # <<< START DEBUG PRINT >>>
                # print(f"\nDEBUG: Regex matched: '{para_text_stripped[:80]}...'") 
                # print(f"DEBUG: Matched ID: {match.group(1)}")
                # <<< END DEBUG PRINT >>>

                # Check if the runs making up the matched ID are bold
                id_str = match.group(1) # The matched ID like "20-110"
                id_len = len(id_str)
                
                # Find the starting position of the ID in the potentially space-padded text
                id_start_index_in_stripped = para_text_stripped.find(id_str)
                if id_start_index_in_stripped == 0: # Ensure it matches at the start
                    id_start_index_in_original = len(para_text) - len(para_text.lstrip(' \t\n\r'))
                    id_end_index_in_original = id_start_index_in_original + id_len

                    runs_are_bold = True
                    current_pos = 0
                    num_runs_in_id = 0

                    for run in para.runs:
                        run_text = run.text
                        run_len = len(run_text)
                        run_start = current_pos
                        run_end = current_pos + run_len

                        # Check if this run overlaps with the ID's span in the original text
                        if max(run_start, id_start_index_in_original) < min(run_end, id_end_index_in_original):
                            if run_text.strip(): # Only consider runs with actual text content
                                num_runs_in_id += 1
                                # The run.bold property checks direct and inherited style boldness
                                # <<< START DEBUG PRINT >>>
                                # print(f"  DEBUG: Run text: '{run_text}', Direct Bold: {run.bold}, Style: {para.style.name}, Style Bold: {para.style.font.bold}")
                                # <<< END DEBUG PRINT >>>
                                
                                # Determine effective boldness
                                effective_bold = run.bold 
                                if effective_bold is None: # Inherit from style
                                    effective_bold = para.style.font.bold
                                
                                # Treat None from style as not bold for simplicity, adjust if needed
                                if effective_bold is not True: 
                                    runs_are_bold = False
                                    # <<< START DEBUG PRINT >>>
                                    # print(f"  DEBUG: Run marked as effectively NOT bold. Aborting bold check for this paragraph.")
                                    # <<< END DEBUG PRINT >>>
                                    break # Found a non-bold run within the ID

                        current_pos = run_end
                        if current_pos >= id_end_index_in_original:
                             # We've processed all runs covering the ID
                             break

                    # Only count as section start if ID runs were found and all were bold
                    if num_runs_in_id > 0 and runs_are_bold:
                        is_section_start = True
                    # <<< START DEBUG PRINT >>>
                    # else:
                        # print(f"  DEBUG: Failed bold check. num_runs_in_id={num_runs_in_id}, runs_are_bold={runs_are_bold}")
                    # <<< END DEBUG PRINT >>>

            # --- Logic to store previous section and start new one --- (FROM Paragraph)
            if is_section_start:
                # Store the previous section if one was being collected
                if current_section_id:
                    # Clean up trailing blank lines
                    cleaned_content = [line for line in current_section_content if line.strip()]
                    full_text = "\n".join(cleaned_content)
                    char_count = len(full_text)
                    austlii_url = generate_austlii_url(current_section_id)
                    sections[current_section_id] = {
                        "text": full_text,
                        "char_count": char_count,
                        "austlii_url": austlii_url
                    }

                # Start collecting the new section
                current_section_id = match.group(1) # Get the ID like "20-110"
                current_section_content = [para_text_stripped] # Start with the stripped heading line
                # print(f"Found Section Start: {current_section_id}") # Debugging

            elif current_section_id:
                # This paragraph belongs to the current section
                if para_text_stripped: # Add non-empty paragraphs
                    current_section_content.append(para_text_stripped)
                # Don't add multiple blank lines - handled by join/strip later

        elif isinstance(element, Table):
            table = element # Rename for clarity
            # If we are currently inside a section, add the table's content
            if current_section_id:
                linearized_table_text = linearize_table(table)
                if linearized_table_text.strip(): # Only add if table isn't empty
                    current_section_content.append(f"\n--- Table Start ---\n{linearized_table_text}\n--- Table End ---\n")

    # --- Store the very last section ---
    if current_section_id:
         # Clean up trailing blank lines
         cleaned_content = [line for line in current_section_content if line.strip()]
         full_text = "\n".join(cleaned_content)
         char_count = len(full_text)
         austlii_url = generate_austlii_url(current_section_id)
         sections[current_section_id] = {
            "text": full_text,
            "char_count": char_count,
            "austlii_url": austlii_url
         }

    return sections

# --- Example Usage ---
# Check if a filename argument was provided
if len(sys.argv) < 2:
    print("Usage: python docx_parse.py <filename.docx>")
    sys.exit(1) # Exit if no filename is given

docx_file = sys.argv[1] # Get filename from command line

# Optional: Add a check to ensure the file exists
if not os.path.exists(docx_file):
    print(f"Error: File not found at '{docx_file}'")
    sys.exit(1)

print(f"Processing DOCX file: {docx_file}") # Added print statement
extracted_data = extract_docx_sections(docx_file)

if extracted_data:
    print(f"\nSuccessfully extracted {len(extracted_data)} sections.")

    # --- Save to JSON --- 
    base_filename = os.path.splitext(docx_file)[0]
    json_filename = f"{base_filename}.json"
    try:
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, ensure_ascii=False, indent=4)
        print(f"Extracted data saved to: {json_filename}")
    except Exception as e:
        print(f"Error saving data to JSON file '{json_filename}': {e}")

    # --- Ready for Embedding --- 
    # for section_id, content in extracted_data.items():
    #     embedding = your_embedding_function(content)
    #     store_embedding(section_id, embedding, content) 

else:
    print("Could not extract any sections. Check the logic and DOCX structure.")