import json
from bs4 import BeautifulSoup, NavigableString
import re

def normalize_hyphens(text):
    """Replaces various Unicode dashes/hyphens with standard hyphen-minus."""
    if not text:
        return text
    # Replace various dashes (U+2010 to U+2015) and standard hyphen with hyphen-minus
    return re.sub(r'[\u2010-\u2015\-]+', '-', text)

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

def extract_html_sections(html_filepath):
    """
    Reads an HTML file, parses it, identifies legislative structure markers 
    (Chapter, Part, Division, Subdivision, Guide, Section), and returns a 
    dictionary mapping structure IDs to a dictionary containing:
    - html: The full HTML chunk (marker tag + subsequent content tags).
    - char_count: Character count of the HTML chunk.
    - text_for_embedding: Cleaned text content with images and tags removed.
    - heading_text: The descriptive heading associated with the marker.
    """
    try:
        with open(html_filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except FileNotFoundError:
        print(f"Error: HTML file not found at {html_filepath}")
        return {}
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        return {}

    soup = BeautifulSoup(html_content, 'html.parser')
    sections_dict = {}

    # Define pattern to match various hyphens/dashes or just space as separator
    separator_pattern = r"[\s\u2010-\u2015\-]+" # Match one or more separator characters
    # Define pattern to specifically match the *standard* hyphen for splitting IDs
    standard_hyphen = "-"

    # --- Corrected Patterns ---
    # Group 1: ID
    # Group 2: Heading Text (Captures the rest of the line, trimmed later)
    patterns = {
        # Use {1,3} for digit counts, not {{1,3}}
        'Chapter': re.compile(rf"^\s*Chapter\s+(\d{{1,3}}[A-Z]?){separator_pattern}(.*?)(?:$|\s+\d+$)", re.IGNORECASE),
        'Part': re.compile(rf"^\s*Part\s+(\d{{1,3}}[A-Z]?-\d{{1,3}}[A-Z]?){separator_pattern}(.*?)(?:$|\s+\d+$)", re.IGNORECASE),
        'Division': re.compile(rf"^\s*Division\s+(\d{{1,3}}[A-Z]?){separator_pattern}(.*?)(?:$|\s+\d+$)", re.IGNORECASE),
        'Subdivision': re.compile(rf"^\s*Subdivision\s+(\d{{1,3}}[A-Z]?-[A-Z]){separator_pattern}(.*?)(?:$|\s+\d+$)", re.IGNORECASE),
        # Group 1: Guide Type (e.g., Division)
        # Group 2: Guide Target ID (e.g., 40-B)
        # Group 3: Heading Text (rest of line)
        'Guide': re.compile(r"^\s*Guide to (Division|Subdivision|Part|Chapter)\s+(\d{{1,3}}[A-Z]?(?:-\d{{1,3}}[A-Z]?|-[A-Z])?)\s*(.*?)(?:$|\s+\d+$)", re.IGNORECASE),
        # Group 1: ID (e.g., 40-25)
        # Group 2: Heading Text (rest of line)
        # Allowing optional space after ID before heading text
        'Section': re.compile(rf"^\s*(?:<strong>)?(\d{{1,3}}[A-Z]?{separator_pattern}\d{{1,3}}[A-Z]?)(?:</strong>)?\s*(.*?)(?:$|\s+\d+$)", re.IGNORECASE)
    }
    # --- End Pattern Correction ---

    current_key_normalized = None
    current_html_snippet_tags = []
    found_first_section = False

    content_tags = soup.body.find_all(recursive=False) if soup.body else []
    if not content_tags:
        content_tags = list(soup.children)

    for tag in content_tags:
        if not hasattr(tag, 'name'):
            continue

        try:
            text = tag.get_text(" ", strip=True)
        except AttributeError:
            text = ""

        matched_level = None
        match_obj = None
        heading_text = ""
        if text:
            for level, pattern in patterns.items():
                match_obj = pattern.match(text)
                if match_obj:
                    matched_level = level
                    try:
                        group_index = 3 if level == 'Guide' else 2
                        heading_text = match_obj.group(group_index).strip() if match_obj.group(group_index) else ""
                        # Clean up potential extra spaces within heading from separator matching
                        heading_text = re.sub(r'\s+', ' ', heading_text).strip()
                    except IndexError:
                        heading_text = ""
                    break

        if matched_level:
            if current_key_normalized and current_html_snippet_tags:
                html_string = "\n".join(str(t) for t in current_html_snippet_tags)
                text_for_embedding = clean_html_for_embedding(html_string)
                sections_dict[current_key_normalized]["html"] = html_string
                sections_dict[current_key_normalized]["char_count"] = len(text_for_embedding)
                sections_dict[current_key_normalized]["text_for_embedding"] = text_for_embedding

            raw_identifier = None
            new_key_normalized = None
            section_info = {
                "structure_type": matched_level,
                "heading_text": heading_text # Store potentially empty heading
            }

            id_group_index = 2 if level == 'Guide' else 1
            raw_identifier = match_obj.group(id_group_index)

            if matched_level == 'Guide':
                guide_type = match_obj.group(1)
                # raw_identifier already set to guide_id (group 2)
                raw_key = f"Guide to {guide_type} {raw_identifier}"
                new_key_normalized = normalize_hyphens(raw_key)
                section_info["guide_target_type"] = guide_type
            else: # Chapter, Part, Division, Subdivision, Section
                # raw_identifier already set to ID (group 1)
                 new_key_normalized = normalize_hyphens(raw_identifier)


            if raw_identifier:
                normalized_identifier = normalize_hyphens(raw_identifier)
                section_info["full_id"] = normalized_identifier

                id_parts = normalized_identifier.split(standard_hyphen)
                if len(id_parts) > 0:
                    section_info["primary_id"] = id_parts[0]
                if len(id_parts) > 1:
                    section_info["secondary_id"] = id_parts[1]

            current_key_normalized = new_key_normalized
            if current_key_normalized: # Ensure we have a valid key
                sections_dict[current_key_normalized] = section_info
                current_html_snippet_tags = [tag]
                found_first_section = True
            else:
                print(f"Warning: Could not determine normalized key for matched text: {text[:100]}...")


        elif current_key_normalized and found_first_section:
             current_html_snippet_tags.append(tag)

    if current_key_normalized and current_html_snippet_tags:
        html_string = "\n".join(str(t) for t in current_html_snippet_tags)
        text_for_embedding = clean_html_for_embedding(html_string)
        sections_dict[current_key_normalized]["html"] = html_string
        sections_dict[current_key_normalized]["char_count"] = len(text_for_embedding)
        sections_dict[current_key_normalized]["text_for_embedding"] = text_for_embedding

    print(f"Identified {len(sections_dict)} sections/markers.")
    return sections_dict

def save_to_json(data, json_filepath):
    """Saves the dictionary to a JSON file."""
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved data to {json_filepath}")
    except Exception as e:
        print(f"Error saving data to JSON: {e}")

# Removed helper function as it's not used currently
# def identifier_from_key(key_string):
#      parts = key_string.split(' ', 1)
#      if len(parts) > 1:
#           return parts[1]
#      return ""

if __name__ == "__main__":
    input_html_file = 'itaa1997.html'
    output_json_file = 'sections_mammoth_html.json'
    
    sections = extract_html_sections(input_html_file)
    
    if sections:
      save_to_json(sections, output_json_file)
    else:
      # Save an empty JSON if no sections found or error occurred
      save_to_json({}, output_json_file)
      print("No sections extracted, saving empty JSON.") 