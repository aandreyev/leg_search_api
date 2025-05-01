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

    current_key = None # Changed variable name for clarity
    current_html_snippet_tags = []
    found_first_section = False

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
            logging.debug(f"  Raw Text: '{raw_text}'") # Log raw text
            logging.debug(f"  Normalized Text: '{text}'") # Log normalized text
            # --- End Normalization ---
        except AttributeError:
            text = ""
            raw_text = ""

        matched_level = None
        match_obj = None
        heading_text = ""
        if text:
            logging.debug("  Checking patterns against NORMALIZED text...")
            for level, pattern in patterns.items():
                match_obj = pattern.match(text) # Match against normalized text
                match_result = "MATCH" if match_obj else "NO MATCH"
                logging.debug(f"    Pattern '{level}': {match_result}")
                if match_obj:
                    matched_level = level
                    logging.debug(f"  >>> Matched as '{matched_level}'")
                    try:
                        group_index = 3 if level == 'Guide' else 2
                        # Extract heading from the normalized text match
                        heading_text = match_obj.group(group_index).strip() if match_obj.group(group_index) else ""
                        heading_text = re.sub(r'\s+', ' ', heading_text).strip()
                    except IndexError:
                        heading_text = ""
                    break

        if matched_level:
            if current_key and current_html_snippet_tags:
                html_string = "\n".join(str(t) for t in current_html_snippet_tags)
                text_for_embedding = clean_html_for_embedding(html_string)
                # Ensure entry exists before updating
                if current_key in sections_dict:
                    sections_dict[current_key]["html"] = html_string
                    sections_dict[current_key]["char_count"] = len(text_for_embedding)
                    sections_dict[current_key]["text_for_embedding"] = text_for_embedding
                else:
                    # This case should ideally not happen if logic is correct
                    logging.warning(f"Attempted to finalize section '{current_key}' which was not properly initialized.")

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
                # Construct unique key for Guides
                new_key = f"Guide to {guide_type}-{identifier}" 
                section_info["guide_target_type"] = guide_type
            else: # Chapter, Part, Division, Subdivision, Section
                # Construct unique key using structure_type and identifier
                new_key = f"{matched_level}-{identifier}"

            if identifier:
                section_info["full_id"] = identifier 

                id_parts = identifier.split(standard_hyphen) # Split normalized ID
                if len(id_parts) > 0:
                    section_info["primary_id"] = id_parts[0]
                if len(id_parts) > 1:
                    section_info["secondary_id"] = id_parts[1]

            current_key = new_key # Use the new unique key
            if current_key:
                logging.debug(f"  >>> Starting new section: Key='{current_key}', Info={section_info}")
                # Add checks to prevent overwriting if key collision (unlikely now)
                if current_key in sections_dict:
                     logging.warning(f"Duplicate unique key detected: '{current_key}'. Overwriting previous entry.")
                sections_dict[current_key] = section_info
                ordered_keys.append(current_key) # Add key to ordered list
                current_html_snippet_tags = [tag] # Start HTML with the original tag
                found_first_section = True
            else:
                logging.debug(f"  >>> WARNING: Could not determine key for matched text.")
                logging.warning(f"Could not determine key for matched text: {text[:100]}...") 

        elif current_key and found_first_section:
             logging.debug(f"  Appending tag to section '{current_key}'")
             # Ensure the list exists before appending (should always exist here)
             if current_key in sections_dict:
                 current_html_snippet_tags.append(tag)
             else:
                  logging.warning(f"Attempted to append tag to uninitialized section '{current_key}'. Tag: {str(tag)[:100]}")
        else:
            logging.debug(f"  Tag did not match and no current section active. Skipping.")

    # Finalize the last section
    if current_key and current_html_snippet_tags:
        logging.debug(f"\nFinalizing last section: Key='{current_key}'")
        html_string = "\n".join(str(t) for t in current_html_snippet_tags)
        text_for_embedding = clean_html_for_embedding(html_string)
        # Ensure entry exists before updating
        if current_key in sections_dict:
            sections_dict[current_key]["html"] = html_string
            sections_dict[current_key]["char_count"] = len(text_for_embedding)
            sections_dict[current_key]["text_for_embedding"] = text_for_embedding
        else:
             logging.warning(f"Attempted to finalize last section '{current_key}' which was not properly initialized.")

    logging.info(f"Identified {len(sections_dict)} sections/markers.") 
    # Return both the dictionary and the ordered list of keys
    return sections_dict, ordered_keys 

def post_process_table_of_sections(sections_dict, ordered_keys):
    """Moves 'Table of sections' paragraphs to the preceding structural element."""
    logging.info("Starting post-processing for 'Table of sections'...")
    keys_to_delete = [] # Keep track of fully emptied sections if any
    modified_count = 0

    for i in range(1, len(ordered_keys)):
        current_key = ordered_keys[i]
        prev_key = ordered_keys[i-1]

        if current_key not in sections_dict or prev_key not in sections_dict:
            logging.warning(f"Skipping post-processing check between '{prev_key}' and '{current_key}': one or both keys missing.")
            continue

        current_section = sections_dict[current_key]
        prev_section = sections_dict[prev_key]

        if 'html' not in current_section or not current_section['html']:
            continue # Skip if current section has no HTML
        
        # Use BeautifulSoup to parse the current section's HTML
        # This is slightly inefficient but safer for manipulating HTML
        soup = BeautifulSoup(current_section['html'], 'html.parser')
        tags_to_move = []
        first_tag = soup.find(True) # Find the very first tag

        if first_tag and first_tag.name == 'p' and first_tag.get_text(strip=True).lower() == 'table of sections':
            logging.debug(f"  Found 'Table of sections' at start of key '{current_key}'. Checking previous key '{prev_key}'.")
            tags_to_move.append(first_tag)
            # Optional: Check for subsequent <ul> or <ol> to move as well (more complex)
            # next_sibling = first_tag.find_next_sibling()
            # while next_sibling and next_sibling.name in ['ul', 'ol']:
            #    tags_to_move.append(next_sibling)
            #    next_sibling = next_sibling.find_next_sibling()
            
            if tags_to_move:
                logging.info(f"  Moving 'Table of sections' tag(s) from '{current_key}' to '{prev_key}'.")
                # Extract tags to move from the current soup
                extracted_html = "\n".join(str(tag.extract()) for tag in tags_to_move)
                
                # Append extracted HTML to previous section's HTML
                prev_html = prev_section.get('html', '')
                prev_section['html'] = prev_html + "\n" + extracted_html
                
                # Update previous section's text and char count
                prev_text = clean_html_for_embedding(prev_section['html'])
                prev_section['text_for_embedding'] = prev_text
                prev_section['char_count'] = len(prev_text)

                # Update current section's HTML (now without the moved tags)
                current_section['html'] = str(soup)
                # Update current section's text and char count
                current_text = clean_html_for_embedding(current_section['html'])
                current_section['text_for_embedding'] = current_text
                current_section['char_count'] = len(current_text)

                modified_count += 1

                # Optional: If current section becomes empty, mark for deletion
                # if not soup.find(True): # Check if any tags remain
                #    logging.info(f"    Section '{current_key}' is now empty after moving tags.")
                #    keys_to_delete.append(current_key)

    # Optional: Remove empty sections
    # if keys_to_delete:
    #     logging.info(f"Removing {len(keys_to_delete)} sections that became empty.")
    #     for key in keys_to_delete:
    #         if key in sections_dict:
    #             del sections_dict[key]

    logging.info(f"Finished post-processing. Moved 'Table of sections' for {modified_count} entries.")
    # The sections_dict is modified in-place, no need to return typically,
    # but returning it makes the flow explicit.
    return sections_dict 

def save_to_json(data, json_filepath):
    """Saves the dictionary to a JSON file."""
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"Successfully saved data to {json_filepath}") 
    except Exception as e:
        logging.error(f"Error saving data to JSON: {e}") 

# Removed helper function as it's not used currently
# def identifier_from_key(key_string):
#      parts = key_string.split(' ', 1)
#      if len(parts) > 1:
#           return parts[1]
#      return ""

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

    # Perform Post-Processing Step
    if sections and ordered_keys: # Ensure we have data to process
        sections = post_process_table_of_sections(sections, ordered_keys)
    else:
        logging.warning("Skipping post-processing as no sections or ordered keys were generated.")

    # Save the results to the specified output JSON path
    if sections is not None: 
      logging.info(f"Saving potentially modified sections to: {output_json_path}") 
      save_to_json(sections, output_json_path)
    else:
      # This case might be less likely now, but kept for safety
      logging.error(f"Error during HTML processing or post-processing. Saving empty/original JSON to '{output_json_path}'.") 
      # Decide whether to save empty or potentially partially processed data
      save_to_json({}, output_json_path) # Saving empty on error
    
    logging.info("HTML Parser script finished.") 