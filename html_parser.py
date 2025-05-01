import json
from bs4 import BeautifulSoup, NavigableString
import re
import sys # Import sys to access command-line arguments
import os # Import os for path operations (optional but good practice)
import logging # Import the logging module

# --- Logging Setup ---
# Basic configuration will be done in the main block
# --- End Logging Setup ---

def normalize_hyphens(text):
    """Replaces various Unicode dashes/hyphens with standard hyphen-minus."""
    if not text:
        return text
    # Explicitly list hyphen/dash characters to replace, excluding em-dash (U+2014) etc.
    # Includes: U+2010, U+2011, U+2012, U+2013, U+002D
    return re.sub(r'[\u2010\u2011\u2012\u2013\-]+', '-', text)

def clean_html_for_embedding(html_string):
    """Removes images and extracts clean text from an HTML string."""
    if not html_string:
        return ""
    soup = BeautifulSoup(html_string, 'html.parser')
    
    # Remove all image tags
    for img_tag in soup.find_all('img'):
        img_tag.decompose() # Or img_tag.extract()
        
    # Extract text, using space as separator, and strip whitespace
    text = soup.get_text(separator=' ', strip=True)
    return text

def extract_html_sections(html_content):
    """
    Parses HTML content, identifies legislative structure markers 
    (Chapter, Part, Division, Subdivision, Guide, Section), and returns a 
    dictionary mapping structure IDs to a dictionary containing:
    - html: The full HTML chunk (marker tag + subsequent content tags).
    - char_count: Character count of the HTML chunk.
    - text_for_embedding: Cleaned text content with images and tags removed.
    - heading_text: The descriptive heading associated with the marker.

    Args:
        html_content (str): The HTML string content to parse.
    """
    if not html_content:
        logging.error("No HTML content provided to extract_html_sections.") 
        return {}

    soup = BeautifulSoup(html_content, 'html.parser')
    sections_dict = {}
    ordered_keys = [] # List to store keys in order of appearance

    # Define specific separators
    whitespace_separator = r"[\s\u00A0]+" # Match standard whitespace AND non-breaking space (U+00A0)
    # Separator allowing whitespace OR common dashes (incl em-dash) AFTER an ID
    id_heading_separator_pattern = r"[\s\u2010-\u2015\-]+"
    # Standard hyphen is still needed for splitting IDs later
    standard_hyphen = "-"

    # --- Patterns using refined separators ---
    # Group 1: ID (standard hyphen '-')
    # Group 2: Heading Text
    # Separator after ID is handled by consuming non-alphanumeric/space characters
    # Heading capture stops before optional trailing number
    patterns = {
        'Chapter':     re.compile(r"^\s*Chapter[\s\u00A0]+(\d{1,3}[A-Z]?)(?:[^\w\s]|\s)*(.*?)(?:\s+\d+)?$", re.IGNORECASE),
        'Part':        re.compile(r"^\s*Part[\s\u00A0]+(\d{1,3}[A-Z]?-\d{1,3}[A-Z]?)(?:[^\w\s]|\s)*(.*?)(?:\s+\d+)?$", re.IGNORECASE),
        'Division':    re.compile(r"^\s*Division[\s\u00A0]+(\d{1,3}[A-Z]?)(?:[^\w\s]|\s)*(.*?)(?:\s+\d+)?$", re.IGNORECASE),
        'Subdivision': re.compile(r"^\s*Subdivision[\s\u00A0]+(\d{1,3}[A-Z]?-[A-Z])(?:[^\w\s]|\s)*(.*?)(?:\s+\d+)?$", re.IGNORECASE),
        # Guide pattern uses whitespace separator explicitly before heading
        'Guide':       re.compile(r"^\s*Guide to (Division|Subdivision|Part|Chapter)[\s\u00A0]+(\d{1,3}[A-Z]?(?:-\d{1,3}[A-Z]?|-[A-Z])?)[\s\u00A0]+(.*?)(?:\s+\d+)?$", re.IGNORECASE),
        # Section pattern adjusted
        'Section':     re.compile(r"^\s*(?:<strong>)?(\d{1,3}[A-Z]?-\d{1,3}[A-Z]?)(?:</strong>)?(?:[^\w\s]|\s)*(.*?)(?:\s+\d+)?$", re.IGNORECASE)
    }
    # --- End Patterns ---

    current_key = None
    current_html_snippet_tags = []
    found_first_section = False
    in_table_of_sections = False # State flag

    content_tags = soup.body.find_all(recursive=False) if soup.body else []
    if not content_tags:
        content_tags = list(soup.children)

    for tag in content_tags:
        if not hasattr(tag, 'name'):
            continue

        logging.debug(f"\nProcessing Tag: {str(tag)[:200]}...")

        try:
            raw_text = tag.get_text(" ", strip=True)
            # --- Normalize text FIRST --- 
            text = normalize_hyphens(raw_text)
            logging.debug(f"  Raw Text: '{raw_text}'")
            logging.debug(f"  Normalized Text: '{text}'")
        except AttributeError:
            text = ""
            raw_text = ""

        # --- State Handling for Table of Sections ---
        is_definitive_heading = False
        if hasattr(tag, 'find') and tag.find('a', id=re.compile(r'^_Toc')):
             is_definitive_heading = True
             logging.debug("  Tag contains a TOC anchor, likely a definitive heading.")

        if in_table_of_sections:
            # If we are in a table, check if this tag marks the end of it
            if is_definitive_heading or any(p.match(text) for p_name, p in patterns.items() if p_name != 'Section'): # Check higher-level patterns too
                logging.debug("  >>> Exiting table of sections mode.")
                in_table_of_sections = False
                # Fall through to normal processing for this tag
            else:
                # Still in table, just append the tag to the current section
                if current_key and found_first_section:
                     logging.debug(f"  [In Table Mode] Appending tag to section '{current_key}'")
                     current_html_snippet_tags.append(tag)
                     continue # Skip normal pattern matching for this tag
                else:
                     logging.warning("[In Table Mode] Found table line but no current section active. Skipping.")
                     continue

        # Check if this tag *starts* a table of sections (only if not already in one)
        if not in_table_of_sections and tag.name == 'p' and text.lower() == 'table of sections':
            logging.debug("  >>> Entering table of sections mode.")
            in_table_of_sections = True
            # Append this header tag to the current section and continue
            if current_key and found_first_section:
                logging.debug(f"  Appending 'Table of sections' header to section '{current_key}'")
                current_html_snippet_tags.append(tag)
                continue
            else:
                logging.warning("Found 'Table of sections' header but no current section active. Skipping.")
                continue
        # --- End State Handling ---

        # --- Normal Pattern Matching --- 
        matched_level = None
        match_obj = None
        heading_text = ""
        if text:
            logging.debug("  Checking patterns against NORMALIZED text...")
            for level, pattern in patterns.items():
                match_obj = pattern.match(text)
                match_result = "MATCH" if match_obj else "NO MATCH"
                logging.debug(f"    Pattern '{level}': {match_result}")
                if match_obj:
                    # Check if it's a weak 'Section' match that should be ignored
                    # (Could add more sophisticated checks here if needed)
                    # For now, if it matched, we assume it's a real heading *unless* in_table_of_sections was true (handled above)
                    matched_level = level
                    logging.debug(f"  >>> Matched as '{matched_level}'")
                    try:
                        group_index = 3 if level == 'Guide' else 2
                        heading_text = match_obj.group(group_index).strip() if match_obj.group(group_index) else ""
                        heading_text = re.sub(r'\s+', ' ', heading_text).strip()
                    except IndexError:
                        heading_text = ""
                    break

        if matched_level:
            # Finalize the previous section (if any)
            if current_key and current_html_snippet_tags:
                html_string = "\n".join(str(t) for t in current_html_snippet_tags)
                text_for_embedding = clean_html_for_embedding(html_string)
                if current_key in sections_dict:
                    sections_dict[current_key]["html"] = html_string
                    sections_dict[current_key]["char_count"] = len(text_for_embedding)
                    sections_dict[current_key]["text_for_embedding"] = text_for_embedding
                else:
                    logging.warning(f"Attempted to finalize section '{current_key}' which was not properly initialized.")

            # Start the new section
            identifier = None
            new_key = None
            section_info = {
                "structure_type": matched_level,
                "heading_text": heading_text
            }
            id_group_index = 2 if level == 'Guide' else 1
            identifier = match_obj.group(id_group_index)

            if matched_level == 'Guide':
                guide_type = match_obj.group(1)
                new_key = f"Guide to {guide_type}-{identifier}" 
                section_info["guide_target_type"] = guide_type
            else: # Chapter, Part, Division, Subdivision, Section
                new_key = f"{matched_level}-{identifier}"

            if identifier:
                section_info["full_id"] = identifier 

                id_parts = identifier.split(standard_hyphen)
                if len(id_parts) > 0:
                    section_info["primary_id"] = id_parts[0]
                if len(id_parts) > 1:
                    section_info["secondary_id"] = id_parts[1]

            current_key = new_key
            if current_key:
                logging.debug(f"  >>> Starting new section: Key='{current_key}', Info={section_info}")
                if current_key in sections_dict:
                     logging.warning(f"Duplicate unique key detected: '{current_key}'. Overwriting previous entry.")
                sections_dict[current_key] = section_info
                ordered_keys.append(current_key)
                current_html_snippet_tags = [tag] # Start HTML with the matched tag
                found_first_section = True
            else:
                logging.debug(f"  >>> WARNING: Could not determine key for matched text.")
                logging.warning(f"Could not determine key for matched text: {text[:100]}...") 

        elif current_key and found_first_section:
             # This tag didn't match any pattern, append to current section
             logging.debug(f"  Appending non-matching tag to section '{current_key}'")
             if current_key in sections_dict: # Check necessary?
                 current_html_snippet_tags.append(tag)
             else:
                  logging.warning(f"Attempted to append tag to uninitialized section '{current_key}'. Tag: {str(tag)[:100]}")
        else:
             # Before the first section or error
             logging.debug(f"  Tag did not match and no current section active. Skipping.")

    # Finalize the last section
    if current_key and current_html_snippet_tags:
        logging.debug(f"\nFinalizing last section: Key='{current_key}'")
        html_string = "\n".join(str(t) for t in current_html_snippet_tags)
        text_for_embedding = clean_html_for_embedding(html_string)
        if current_key in sections_dict:
            sections_dict[current_key]["html"] = html_string
            sections_dict[current_key]["char_count"] = len(text_for_embedding)
            sections_dict[current_key]["text_for_embedding"] = text_for_embedding
        else:
             logging.warning(f"Attempted to finalize last section '{current_key}' which was not properly initialized.")

    logging.info(f"Identified {len(sections_dict)} sections/markers.") 
    # Return both the dictionary and the ordered list of keys
    return sections_dict, ordered_keys 

# --- Table of Sections Processing Function ---
def post_process_table_of_sections(sections_dict, ordered_keys):
    # ... (Existing function code) ...
    return sections_dict

# --- Build Final Content Function ---
def build_final_content(sections_dict, ordered_keys):
    """
    Builds the final dictionary structure:
    1. Copies original non-Section elements.
    2. Creates new Section entries with prepended context HTML gathered from 
       preceding non-Section elements.
    Assumes table processing has already happened in sections_dict.
    Returns the final dictionary with all elements.
    """
    logging.info("Starting build of final content structure...")
    final_dict = {}
    current_context_html = "" # Accumulates HTML from preceding non-Sections
    
    for key in ordered_keys:
        if key not in sections_dict: 
             logging.warning(f"  Key '{key}' from ordered_keys not found in sections_dict during build. Skipping.")
             continue
             
        current_section = sections_dict[key]
        structure_type = current_section.get('structure_type')
        # Get HTML which might have been modified by table processing
        current_html = current_section.get('html', '') 

        logging.debug(f"  Building: Processing key '{key}', type: {structure_type}")

        # Process based on type
        if structure_type != 'Section':
            # --- Non-Section Element --- 
            logging.debug(f"    Keeping original non-Section: '{key}'")
            # 1. Copy original element to the final dictionary
            final_dict[key] = current_section.copy() # Use copy to be safe
            
            # 2. Clean its HTML and add it to the context for subsequent sections
            if current_html:
                 cleaned_html = re.sub(r'\s+\d+\s*(?=</[^>]+>\s*$)', '', current_html.strip())
                 current_context_html += cleaned_html + "\n"
                 logging.debug(f"    Added HTML from '{key}' to context.")
            
        else: # structure_type == 'Section'
            # --- Section Element --- 
            logging.debug(f"    Building consolidated Section: '{key}'")
            # 1. Combine accumulated context with this section's HTML
            # Use original current_html (not cleaned) for the section itself
            combined_html = current_context_html + current_html if current_context_html else current_html
            
            # 2. Create the new consolidated section entry in final_dict
            final_dict[key] = {
                'structure_type': structure_type,
                'heading_text': current_section.get('heading_text', ''),
                'full_id': current_section.get('full_id'),
                'primary_id': current_section.get('primary_id'),
                'secondary_id': current_section.get('secondary_id'),
                'html': combined_html,
                'text_for_embedding': clean_html_for_embedding(combined_html),
                'char_count': len(clean_html_for_embedding(combined_html))
            }
            
            # 3. Reset the context for the next block
            logging.debug(f"    Resetting context after Section '{key}'.")
            current_context_html = "" 
            
    logging.info(f"Finished building final content. Final dictionary has {len(final_dict)} entries.")
    return final_dict

def save_to_json(data, json_filepath):
    """Saves the dictionary to a JSON file."""
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"Successfully saved data to {json_filepath}") 
    except Exception as e:
        logging.error(f"Error saving data to JSON: {e}") 

if __name__ == "__main__":
    # --- Configure Logging --- 
    log_filename = 'html_parser.log'
    logging.basicConfig(
        level=logging.DEBUG, # Log DEBUG level and above
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=log_filename,
        filemode='w' # Overwrite log file each time
    )
    # Add a handler to also print INFO and above to console (optional)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)
    # --- End Logging Configuration ---

    # Read input and output paths from command-line arguments
    if len(sys.argv) != 3:
        # Use logging for critical errors before exiting
        logging.critical(f"Usage: python {os.path.basename(__file__)} <input_mammoth_json> <output_parsed_json>") 
        sys.exit(1)

    input_json_path = sys.argv[1]
    output_json_path = sys.argv[2]

    # Load the HTML content from the input JSON file
    html_to_parse = None
    try:
        logging.info(f"Loading HTML from: {input_json_path}") # Log info
        with open(input_json_path, 'r', encoding='utf-8') as f_in:
            data = json.load(f_in)
            if "html_content" in data:
                html_to_parse = data["html_content"]
            else:
                # Use logging for critical errors
                logging.critical(f"Input JSON '{input_json_path}' does not contain 'html_content' key.") 
                sys.exit(1)
    except FileNotFoundError:
        logging.critical(f"Input JSON file not found at '{input_json_path}'") 
        sys.exit(1)
    except json.JSONDecodeError:
        logging.critical(f"Could not decode JSON from '{input_json_path}'") 
        sys.exit(1)
    except Exception as e:
        logging.critical(f"Error reading input JSON file '{input_json_path}': {e}") 
        sys.exit(1)

    # Process the loaded HTML
    logging.info("Starting HTML section extraction...")
    sections, ordered_keys = extract_html_sections(html_to_parse) # Get both dict and ordered keys

    # Perform Post-Processing Steps
    if sections and ordered_keys: # Ensure we have data to process
        # 1. Process Tables of Sections first (modifies sections dict in-place)
        processed_sections = post_process_table_of_sections(sections, ordered_keys)
        # 2. Build the final content structure (copies originals, builds new sections)
        final_content = build_final_content(processed_sections, ordered_keys)
    else:
        logging.warning("Skipping post-processing as no sections or ordered keys were generated.")
        final_content = sections # Assign original if no processing happened

    # Save the final results to the specified output JSON path
    if final_content is not None: 
      logging.info(f"Saving final processed sections to: {output_json_path}") 
      save_to_json(final_content, output_json_path)
    else:
      # This case might be less likely now, but kept for safety
      logging.error(f"Error during HTML processing or post-processing. Saving empty/original JSON to '{output_json_path}'.") 
      # Decide whether to save empty or potentially partially processed data
      save_to_json({}, output_json_path) # Saving empty on error
    
    logging.info("HTML Parser script finished.") 