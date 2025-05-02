# style_html_content.py
import sys
import os
import json
import logging
import re
from bs4 import BeautifulSoup, Tag

# Basic Logging Setup
log_file = 'style_html.log'
# Ensure the logs directory exists
log_dir = os.path.dirname(log_file)
if log_dir and not os.path.exists(log_dir):
    try:
        os.makedirs(log_dir)
    except OSError as e:
        print(f"Could not create log directory '{log_dir}': {e}", file=sys.stderr)

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(log_file, mode='w'), logging.StreamHandler()])

def style_section_html(html_string: str, heading_text: str) -> str:
    """
    Applies basic styling to the HTML content of a section.
    Currently: Identifies headings by looking for <p> tags containing <a> with id attributes.
    Also adds indentation for numbered and lettered lists.
    """
    if not html_string:
        return html_string # Return original if no content

    try:
        soup = BeautifulSoup(html_string, 'html.parser')
        
        # --- Add CSS for Headings and Indentation ---
        # Create a style tag if it doesn't exist
        style_tag = soup.find('style')
        if not style_tag:
            style_tag = soup.new_tag('style')
            style_tag.string = """
                .legislation-heading { font-weight: bold; }
                p.indent-level-1 { 
                    margin-left: 0 !important; 
                    padding-left: 0 !important;
                    text-indent: 0 !important;
                }
                p.indent-level-2 { 
                    margin-left: 1em !important; 
                    padding-left: 1em !important;
                    text-indent: 0 !important;
                }
                p.indent-level-3 { 
                    margin-left: 2em !important; 
                    padding-left: 2em !important;
                    text-indent: 0 !important;
                }
            """
            # Add to the beginning of the document
            if soup.contents:
                soup.insert(0, style_tag)
            else:
                soup.append(style_tag)
                
        # --- Find Headings by <a> with id ---
        headings_found = 0
        
        # Look for paragraphs containing anchor tags with id attributes
        for p_tag in soup.find_all('p'):
            a_tags_with_id = p_tag.find_all('a', id=True)
            if a_tags_with_id:
                # This is a heading paragraph - add our class
                p_tag['class'] = p_tag.get('class', []) + ['legislation-heading']
                headings_found += 1
                logging.debug(f"Found heading: {p_tag.get_text()[:50]}...")
        
        # --- Process Indentation for Lists ---
        # Patterns for different list types
        number_pattern = re.compile(r'^\s*\(\d+\)')  # (1), (2), ...
        letter_pattern = re.compile(r'^\s*\(([a-z])\)')  # Now matches all letters (a)-(z)
        roman_pattern = re.compile(r'^\s*\((i{1,3}|iv|v|vi{1,3}|ix|x|xi{1,3}|xiv|xv|xvi{1,3}|xix|xx|xxi{1,3})\)', re.IGNORECASE)
        
        # Context analysis for differentiating between letter (i) and Roman numeral (i)
        def is_likely_letter_sequence(p_tags, current_index):
            """Determine if a tag is likely part of a letter sequence by checking surrounding tags"""
            if current_index <= 0 or current_index >= len(p_tags) - 1:
                return False
            
            # Check if previous tag has (h) and next tag has (j)
            prev_text = p_tags[current_index-1].get_text().strip()
            next_text = p_tags[current_index+1].get_text().strip()
            
            prev_is_h = re.match(r'^\s*\(h\)', prev_text)
            next_is_j = re.match(r'^\s*\(j\)', next_text)
            
            # If surrounded by h and j, likely a letter
            if prev_is_h and next_is_j:
                return True
                
            # Also check for other surrounding letter patterns (a)-(z) excluding i,v,x
            prev_letter_match = re.match(r'^\s*\(([a-z])\)', prev_text)
            next_letter_match = re.match(r'^\s*\(([a-z])\)', next_text)
            
            if prev_letter_match and next_letter_match:
                prev_letter = prev_letter_match.group(1)
                next_letter = next_letter_match.group(1)
                # If there's a clear alphabetical sequence
                if ord(next_letter) - ord(prev_letter) == 2:
                    return True
            
            return False
        
        # Process paragraphs for indentation
        p_tags = soup.find_all('p')
        indent_count = {
            'level1': 0,
            'level2': 0,
            'level3': 0
        }
        
        # First pass: process clear items
        for i, p_tag in enumerate(p_tags):
            p_text = p_tag.get_text().strip()
            
            # Skip tags that are already identified as headings
            if p_tag.get('class') and 'legislation-heading' in p_tag.get('class'):
                continue
            
            # Set a special data attribute for (i) items so we can analyze them further
            if re.match(r'^\s*\(i\)', p_text):
                p_tag['data-needs-context'] = 'true'
                
            # Handle all other cases immediately
            elif number_pattern.match(p_text):
                p_tag['class'] = p_tag.get('class', []) + ['indent-level-1']
                indent_count['level1'] += 1
            elif letter_pattern.match(p_text) and not roman_pattern.match(p_text):
                # This will catch all letters except those that could also be Roman numerals
                p_tag['class'] = p_tag.get('class', []) + ['indent-level-2']
                indent_count['level2'] += 1
            elif roman_pattern.match(p_text) and not p_text.strip().startswith('(i)'):
                # This will catch clear Roman numerals like (ii), (iii), etc.
                p_tag['class'] = p_tag.get('class', []) + ['indent-level-3']
                indent_count['level3'] += 1
        
        # Second pass: resolve ambiguous (i) cases
        for i, p_tag in enumerate(p_tags):
            if p_tag.get('data-needs-context'):
                # Use context to determine if it's a letter or roman numeral
                if is_likely_letter_sequence(p_tags, i):
                    p_tag['class'] = p_tag.get('class', []) + ['indent-level-2']  # Letter (i)
                    indent_count['level2'] += 1
                    logging.debug(f"Identified ambiguous (i) as LETTER based on context")
                else:
                    p_tag['class'] = p_tag.get('class', []) + ['indent-level-3']  # Roman (i)
                    indent_count['level3'] += 1
                    logging.debug(f"Identified ambiguous (i) as ROMAN NUMERAL (default)")
                
                # Clean up the temporary attribute
                del p_tag['data-needs-context']

        logging.debug(f"Applied heading styling to {headings_found} tags")
        logging.debug(f"Applied indentation: Level 1: {indent_count['level1']}, Level 2: {indent_count['level2']}, Level 3: {indent_count['level3']}")

        if headings_found == 0 and sum(indent_count.values()) == 0:
            logging.warning(f"No headings or indentable content found in the HTML content")

        return str(soup)

    except Exception as e:
        logging.error(f"Error processing HTML for styling: {e}")
        return html_string # Return original on error

def process_json_file(input_filepath, output_filepath):
    """Loads input JSON, applies styling to HTML, saves to output JSON."""
    logging.info(f"--- Starting HTML Styling --- ")
    logging.info(f"Loading data from {input_filepath}...")
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        logging.error(f"Input file not found: {input_filepath}")
        print(f"--- Finished HTML Styling (with error) ---", file=sys.stderr)
        return False
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON: {e}")
        print(f"--- Finished HTML Styling (with error) ---", file=sys.stderr)
        return False
    except Exception as e:
        logging.error(f"Error reading input file: {e}")
        print(f"--- Finished HTML Styling (with error) ---", file=sys.stderr)
        return False

    if not isinstance(data, dict):
         logging.error("Input JSON is not a dictionary.")
         print(f"--- Finished HTML Styling (with error) ---", file=sys.stderr)
         return False

    logging.info(f"Processing {len(data)} sections...")
    processed_data = {} # Create a new dict for results
    processed_count = 0
    styled_count = 0
    for key, section_data in data.items():
        processed_count +=1
        # Create a copy to avoid modifying the original dict if needed elsewhere
        updated_section_data = section_data.copy() 

        if isinstance(section_data, dict) and "html" in section_data:
            original_html = section_data.get("html", "")
            heading = section_data.get("heading_text", "")
            
            if original_html:
                 logging.debug(f"Styling section: {key}")
                 styled_html = style_section_html(original_html, heading)
                 # Only update if styling actually changed the HTML
                 if styled_html != original_html:
                      updated_section_data["html"] = styled_html
                      styled_count += 1
                 # Keep original HTML if styling failed or didn't change anything
                 processed_data[key] = updated_section_data 
            else:
                 logging.warning(f"Skipping styling for section {key}: No 'html' content found.")
                 processed_data[key] = updated_section_data # Keep copy
        else:
            logging.warning(f"Skipping styling for section {key}: Invalid format or missing 'html' key.")
            processed_data[key] = updated_section_data # Keep copy

        if processed_count % 100 == 0:
             logging.info(f"Processed {processed_count}/{len(data)} sections...")

    logging.info(f"Styling applied to {styled_count} sections.")
    logging.info(f"Saving styled data to {output_filepath}...")
    try:
        # Ensure output directory exists
        output_dir = os.path.dirname(output_filepath)
        if output_dir and not os.path.exists(output_dir):
             os.makedirs(output_dir)
             
        with open(output_filepath, 'w', encoding='utf-8') as f:
            json.dump(processed_data, f, indent=4, ensure_ascii=False)
        logging.info("Successfully saved styled data.")
        logging.info(f"--- Finished HTML Styling --- ")
        return True
    except Exception as e:
        logging.error(f"Error saving styled data: {e}")
        logging.info(f"--- Finished HTML Styling (with error) ---")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python {os.path.basename(__file__)} <input_converted_json> <output_styled_json>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    if not os.path.exists(input_path):
        print(f"Error: Input file not found at '{input_path}'", file=sys.stderr)
        sys.exit(1)

    success = process_json_file(input_path, output_path)
    if not success:
        # Add more specific error message?
        print("HTML Styling process failed.", file=sys.stderr)
        sys.exit(1) 