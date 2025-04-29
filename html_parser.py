import json
from bs4 import BeautifulSoup, NavigableString
import re

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

    separator_pattern = r"[\s\u2010-\u2015\-]" # Handles various dashes

    patterns = {
        # Using refined patterns
        'Chapter': re.compile(rf"^\s*Chapter\s+(\d{{1,3}}[A-Z]?){separator_pattern}+(.*?)(?:\s+\d+)?$", re.IGNORECASE),
        'Part': re.compile(rf"^\s*Part\s+(\d{{1,3}}[A-Z]?-\d{{1,3}}[A-Z]?){separator_pattern}+(.*?)(?:\s+\d+)?$", re.IGNORECASE),
        'Division': re.compile(rf"^\s*Division\s+(\d{{1,3}}[A-Z]?){separator_pattern}+(.*?)(?:\s+\d+)?$", re.IGNORECASE),
        'Subdivision': re.compile(rf"^\s*Subdivision\s+(\d{{1,3}}[A-Z]?-[A-Z]){separator_pattern}+(.*?)(?:\s+\d+)?$", re.IGNORECASE),
        'Guide': re.compile(r"^\s*Guide to (Division|Subdivision|Part|Chapter)\s+(\d{1,3}[A-Z]?(?:-\d{1,3}[A-Z]?|-[A-Z])?)\s*(.*?)(?:\s+\d+)?$", re.IGNORECASE),
        'Section': re.compile(rf"^\s*(?:<strong>)?(\d{{1,3}}[A-Z]?{separator_pattern}\d{{1,3}}[A-Z]?)(?:</strong>)?\s+(.*?)(?:\s+\d+)?$", re.IGNORECASE)
    }
    
    current_section_key = None
    current_html_snippet_tags = []
    found_first_section = False # Preamble skip flag

    # Find potential content tags: Iterate through direct children of body
    # This is more robust than guessing specific tags like p, h1-h6, table
    content_tags = soup.body.find_all(recursive=False) if soup.body else []
    # Fallback if body has no direct children or body doesn't exist
    if not content_tags:
        content_tags = list(soup.children)

    for tag in content_tags:
        # Skip non-tag elements like NavigableString at the top level
        if not hasattr(tag, 'name'):
            continue
            
        try:
            # Get text primarily for pattern matching, ignore if error
            text = tag.get_text(" ", strip=True) 
        except AttributeError:
            text = "" 
        
        matched_level = None
        match_obj = None
        if text:
            for level, pattern in patterns.items():
                match_obj = pattern.match(text)
                if match_obj:
                    matched_level = level
                    # Use break here: We only want the *first* match to signify a new section start
                    break 

        if matched_level:
            # If we were already collecting tags, save the previous section
            if current_section_key and current_html_snippet_tags:
                html_string = "\\n".join(current_html_snippet_tags)
                text_for_embedding = clean_html_for_embedding(html_string)
                sections_dict[current_section_key] = {
                    "html": html_string,
                    "char_count": len(text_for_embedding),
                    "text_for_embedding": text_for_embedding
                }
            
            # Determine the new key based on the matched level
            new_key = None
            if matched_level == 'Guide':
                guide_type = match_obj.group(1)
                guide_id = match_obj.group(2)
                new_key = f"Guide to {guide_type} {guide_id}"
            elif matched_level == 'Section':
                identifier = match_obj.group(1)
                new_key = identifier # Use only the number as the key for Sections
            else: # Chapter, Part, Division, Subdivision
                identifier = match_obj.group(1)
                new_key = f"{matched_level} {identifier}"

            # Start collecting for the new section
            current_section_key = new_key
            current_html_snippet_tags = [str(tag)] # Start with the tag that matched
            found_first_section = True # We are now past the preamble
        
        elif current_section_key and found_first_section:
            # If we are collecting a section (past preamble) and this tag didn't start a new one,
            # append it to the current section's snippet.
            # Include empty tags if they are part of the content.
            current_html_snippet_tags.append(str(tag))
        # else: Do nothing - ignore tags before the first marker (preamble)

    # Add the last collected section after the loop finishes
    if current_section_key and current_html_snippet_tags:
        html_string = "\\n".join(current_html_snippet_tags)
        text_for_embedding = clean_html_for_embedding(html_string)
        sections_dict[current_section_key] = {
            "html": html_string,
            "char_count": len(text_for_embedding),
            "text_for_embedding": text_for_embedding
        }

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
    input_html_file = 'itaa1997_mammoth.html'
    output_json_file = 'sections_mammoth_html.json'
    
    sections = extract_html_sections(input_html_file)
    
    if sections:
      save_to_json(sections, output_json_file)
    else:
      # Save an empty JSON if no sections found or error occurred
      save_to_json({}, output_json_file)
      print("No sections extracted, saving empty JSON.") 