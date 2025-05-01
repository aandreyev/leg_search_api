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

def post_process_table_of_sections(sections_dict, ordered_keys):
    """
    Searches within each section's HTML for a 'Table of sections' paragraph.
    If found, converts the subsequent section reference paragraphs into a proper
    HTML list structure (ul/li) within that same section's HTML.
    """
    logging.info("Starting post-processing for 'Table of sections'...")
    modified_count = 0

    # Patterns and helper function remain the same
    section_ref_pattern = re.compile(r'^\s*(\d+(?:[-‑]\d+)?[A-Z]?)[\s\u00A0\t]+(.+?)(?:\s+\d+)?$')
    section_heading_pattern = re.compile(r'^\s*(?:<a\s+id="_Toc[^"]+"></a>)?\s*(\d+(?:[-‑]\d+)?[A-Z]?)[\s\u00A0\t]+(.+?)(?:\s+\d+)?$')

    def clean_text_for_matching(text):
        soup = BeautifulSoup(text, 'html.parser')
        return ' '.join(soup.stripped_strings)

    # Iterate through each section identified by the parser
    for key in ordered_keys:
        if key not in sections_dict:
            logging.warning(f"Skipping post-processing for key '{key}': key missing from dictionary.")
            continue

        section = sections_dict[key]

        if 'html' not in section or not section['html']:
            continue

        logging.debug(f"Post-processing key: '{key}'")
        
        # Parse the HTML content of the current section
        soup = BeautifulSoup(section['html'], 'html.parser')
        
        # Find the 'Table of sections' paragraph within this section
        table_header_tag = None
        logging.debug(f"  Searching for 'Table of sections' in <p> tags for key '{key}'...")
        for p_tag in soup.find_all('p'):
            p_text_lower_stripped = p_tag.get_text(strip=True).lower()
            # Log the text being checked for every p tag
            logging.debug(f"    Checking p_tag text: '{p_text_lower_stripped}' (HTML: {str(p_tag)[:100]}...)")
            if p_text_lower_stripped == 'table of sections':
                table_header_tag = p_tag
                # Make this log more prominent
                logging.info(f"  *** FOUND 'Table of sections' paragraph in key '{key}'. ***")
                break # Found the first instance

        if table_header_tag:
            # Start processing subsequent siblings for section references
            section_refs = []
            tags_to_process = [table_header_tag] # Keep track of tags related to the table
            next_tag = table_header_tag.find_next_sibling()
            logging.debug(f"  Sibling after 'Table of sections': {str(next_tag)[:200]}...")

            while next_tag and next_tag.name == 'p':
                # Keep track of the tag we are currently processing
                current_tag_being_checked = next_tag 
                # Move to the next sibling *before* potentially breaking the loop
                next_tag = current_tag_being_checked.find_next_sibling()

                html = str(current_tag_being_checked)
                text = current_tag_being_checked.get_text(strip=True)
                logging.debug(f"  Processing paragraph HTML: {html}")

                # Check 1: Is it an actual section heading with a TOC anchor?
                if section_heading_pattern.search(html) and '<a id="_Toc' in html:
                    logging.debug(f"  Stopping: Found actual section heading marker: {text[:50]}...")
                    break
                
                # Check 2: Does it match the section reference pattern?
                cleaned_text = clean_text_for_matching(html)
                logging.debug(f"  Checking cleaned text for section reference: '{cleaned_text}'")
                match = section_ref_pattern.match(cleaned_text)
                if match:
                    # It's a valid reference, process it
                    section_num = match.group(1)
                    logging.debug(f"    Found section number: {section_num}")
                    section_num_end = html.find(section_num) + len(section_num)
                    title_html = html[section_num_end:].strip()
                    if title_html.startswith('</p>'): title_html = ''
                    title_html = re.sub(r'^[\s\t]+', '', title_html)
                    logging.debug(f"    Found title HTML: {title_html}")
                    section_refs.append((section_num, title_html))
                    # Add the matched tag to the list of tags to remove later
                    tags_to_process.append(current_tag_being_checked) 
                else:
                    # It's not a section reference, and not a heading marker.
                    # Assume the table of sections ends here.
                    logging.debug(f"  Stopping: Paragraph does not match section reference pattern: {text[:50]}...")
                    break 

            # If we found references, replace the original paragraphs with a list
            if section_refs:
                logging.info(f"  Found {len(section_refs)} section references in '{key}'. Creating list.")
                
                # Create a new ul tag
                ul = soup.new_tag('ul')
                for section_num, title_html in section_refs:
                    li = soup.new_tag('li')
                    if title_html:
                        # Attempt to parse the title HTML fragment
                        try:
                            title_soup = BeautifulSoup(title_html, 'html.parser')
                            # Extract the content without the outer <p> tag if it exists
                            inner_content = title_soup.find('p')
                            if inner_content:
                                inner_content = inner_content.decode_contents()
                            else: # No <p> tag, use the whole thing
                                inner_content = title_html
                            
                            # Re-parse combined content to ensure validity
                            li_html = f"{section_num} {inner_content}"
                            li.append(BeautifulSoup(li_html, 'html.parser'))
                        except Exception as e:
                            logging.warning(f"    Error parsing title_html '{title_html}' for section {section_num} in key '{key}': {e}. Using plain text.")
                            li.string = f"{section_num} {BeautifulSoup(title_html, 'html.parser').get_text(strip=True)}"
                    else:
                        li.string = section_num
                    ul.append(li)
                
                # Insert the new list *after* the original table header paragraph
                table_header_tag.insert_after(ul)
                
                # Remove ONLY the subsequent paragraphs that were successfully processed as section references
                # tags_to_process[0] is the header tag, which should be kept.
                # tags_to_process[1:] are the section reference tags that need removing.
                for tag_to_remove in tags_to_process[1:]:
                     if tag_to_remove and tag_to_remove.parent:
                          tag_to_remove.decompose()
                
                # Update the section's HTML, text, and char count
                section['html'] = str(soup)
                section['text_for_embedding'] = clean_html_for_embedding(section['html'])
                section['char_count'] = len(section['text_for_embedding'])

                modified_count += 1
            else:
                 logging.debug(f"  Found 'Table of sections' but no section references followed it in '{key}'.")

    logging.info(f"Finished post-processing. Processed {modified_count} tables of sections.")
    return sections_dict

def post_process_guides(sections_dict, ordered_keys):
    """
    Finds 'Guide to ...' sections and merges their HTML content into the 
    immediately following section. Removes the original guide section entry.
    """
    logging.info("Starting post-processing for 'Guide to ...' sections...")
    keys_to_remove = []
    modified_count = 0

    # Iterate up to the second-to-last key to allow looking ahead
    for i in range(len(ordered_keys) - 1):
        current_key = ordered_keys[i]
        next_key = ordered_keys[i+1]

        # Check if the current key is a Guide
        if current_key.startswith("Guide to "):
            logging.debug(f"  Found potential Guide key: '{current_key}'")
            # Ensure both the guide and the next section exist
            if current_key in sections_dict and next_key in sections_dict:
                guide_section = sections_dict[current_key]
                target_section = sections_dict[next_key]

                # Ensure HTML exists in both
                guide_html = guide_section.get('html', '')
                target_html = target_section.get('html', '')

                if guide_html:
                    # Clean trailing numbers from the guide html string
                    original_guide_html_for_log = guide_html # Keep for logging
                    # Regex: Find whitespace (\s+) followed by digits (\d+) that are immediately
                    # followed by optional whitespace (\s*) and a closing tag (</[^>]+>) at the end of the string.
                    # Use lookahead (?=...) so the tag isn't part of the match.
                    cleaned_guide_html = re.sub(r'\s+\d+\s*(?=</[^>]+>\s*$)', '', guide_html.strip())
                    if cleaned_guide_html != original_guide_html_for_log:
                        logging.debug(f"  Cleaned guide HTML: '{original_guide_html_for_log}' -> '{cleaned_guide_html}'")
                    else:
                        logging.debug(f"  Guide HTML did not require cleaning: '{cleaned_guide_html}'")

                    logging.info(f"  Merging Guide '{current_key}' into '{next_key}'.")
                    # Prepend the *cleaned* guide HTML to the target section's HTML
                    target_section['html'] = cleaned_guide_html + "\n" + target_html
                    
                    # Update target section's text and char count
                    target_text = clean_html_for_embedding(target_section['html'])
                    target_section['text_for_embedding'] = target_text
                    target_section['char_count'] = len(target_text)

                    # Mark the guide key for removal
                    keys_to_remove.append(current_key)
                    modified_count += 1
                else:
                    logging.warning(f"  Guide section '{current_key}' has no HTML content to merge. Skipping.")
                    # Optionally mark for removal even if empty?
                    keys_to_remove.append(current_key) 
            else:
                logging.warning(f"  Found Guide key '{current_key}' but its target '{next_key}' or the guide itself is missing from dict. Cannot merge.")
                # Mark for removal? If the target is missing, the guide is orphaned.
                if current_key in sections_dict: # Only mark if guide exists
                     keys_to_remove.append(current_key)

    # Remove the processed guide keys from the dictionary
    for key in keys_to_remove:
        if key in sections_dict:
            logging.debug(f"  Removing processed Guide key: '{key}'")
            del sections_dict[key]

    logging.info(f"Finished post-processing Guides. Merged {modified_count} guides.")
    # Note: ordered_keys list is not modified, but the dictionary is.
    # Subsequent steps should rely only on the dictionary keys if order matters.
    return sections_dict

def save_to_json(data, json_filepath):
    """Saves the dictionary to a JSON file."""
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"Successfully saved data to {json_filepath}") 
    except Exception as e:
        logging.error(f"Error saving data to JSON: {e}") 

# --- Helper Function for Consolidation ---
def get_structure_level(structure_type):
    """Returns a numerical level for hierarchical sorting/stack management."""
    level_map = {
        'Chapter': 1,
        'Part': 2,
        'Division': 3,
        'Subdivision': 4,
        'Section': 5, # Sections are the base level
        'Guide': 0 # Guides are handled before consolidation
    }
    return level_map.get(structure_type, 99) # Return high number for unknowns

# --- New Consolidation Function ---
def consolidate_to_sections(sections_dict, ordered_keys):
    """
    Consolidates hierarchical structures (Chapter, Part, Division, Subdivision)
    by prepending their HTML content to the Sections that fall under them.
    Assumes Guide and Table of Sections processing has already occurred.
    Returns a new dictionary containing only Section entries.
    """
    logging.info("Starting consolidation into Sections...")
    final_sections = {}
    parent_html_stack = [] # Stores tuples of (level, html_string)
    
    for key in ordered_keys:
        if key not in sections_dict: # Skip keys removed by guide processing
            continue
            
        section = sections_dict[key]
        structure_type = section.get('structure_type')
        current_level = get_structure_level(structure_type)
        current_html = section.get('html', '')

        logging.debug(f"  Processing key '{key}', type: {structure_type}, level: {current_level}")

        # Pop headers from stack that are at the same or lower level
        while parent_html_stack and parent_html_stack[-1][0] >= current_level:
            popped_level, _ = parent_html_stack.pop()
            logging.debug(f"    Popped level {popped_level} from stack.")
            
        # If it's a structural header (not Section), push it onto the stack
        if 1 <= current_level <= 4: # Chapter, Part, Division, Subdivision
            logging.debug(f"    Pushing level {current_level} onto stack.")
            parent_html_stack.append((current_level, current_html))
        
        # If it's a Section, consolidate and add to final output
        elif current_level == 5: # Section
            logging.debug(f"    Consolidating parent HTML for Section '{key}'")
            parent_html_content = "\n".join([html for _, html in parent_html_stack])
            
            # Combine parent HTML with section HTML
            combined_html = parent_html_content + "\n" + current_html if parent_html_content else current_html
            
            # Create the new consolidated section entry
            final_sections[key] = {
                # Copy essential fields from original section
                'structure_type': structure_type,
                'heading_text': section.get('heading_text', ''),
                'full_id': section.get('full_id'),
                'primary_id': section.get('primary_id'),
                'secondary_id': section.get('secondary_id'),
                # Add the consolidated HTML and recalculated text/count
                'html': combined_html,
                'text_for_embedding': clean_html_for_embedding(combined_html),
                'char_count': len(clean_html_for_embedding(combined_html))
                # Note: We lose guide_target_type here, might need adjustment if needed
            }
            logging.debug(f"    Added consolidated section '{key}' to final output.")
        else:
            logging.warning(f"  Skipping key '{key}' with unknown or unhandled structure type '{structure_type}' during consolidation.")
            
    logging.info(f"Finished consolidation. Final dictionary contains {len(final_sections)} Section entries.")
    return final_sections

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
    processed_sections = sections # Start with the initially parsed sections
    if sections and ordered_keys: # Ensure we have data to process
        # Process Tables of Sections first
        processed_sections = post_process_table_of_sections(processed_sections, ordered_keys)
        # Then process Guides, operating on the result of the previous step
        processed_sections = post_process_guides(processed_sections, ordered_keys)
        # Finally, consolidate everything into Section entries
        processed_sections = consolidate_to_sections(processed_sections, ordered_keys)
    else:
        logging.warning("Skipping post-processing as no sections or ordered keys were generated.")

    # Save the final consolidated results to the specified output JSON path
    if processed_sections is not None: 
      logging.info(f"Saving final consolidated sections to: {output_json_path}") 
      save_to_json(processed_sections, output_json_path)
    else:
      # This case might be less likely now, but kept for safety
      logging.error(f"Error during HTML processing or post-processing. Saving empty/original JSON to '{output_json_path}'.") 
      # Decide whether to save empty or potentially partially processed data
      save_to_json({}, output_json_path) # Saving empty on error
    
    logging.info("HTML Parser script finished.") 