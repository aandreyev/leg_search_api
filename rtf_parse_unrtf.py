# rtf_parse_unrtf.py
import re
import subprocess
import sys
import os

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: 'beautifulsoup4' library not found.")
    print("Please install it first using: pip install beautifulsoup4")
    # Optionally exit if bs4 is critical for the script to even load
    # sys.exit(1) 

def run_unrtf(rtf_path):
    """Runs the unrtf command to convert RTF to HTML."""
    # Check if unrtf is callable
    try:
        # Use 'command -v unrtf' on Unix-like systems to check if unrtf exists
        # Use 'where unrtf' on Windows
        check_cmd = "command -v unrtf" if os.name != 'nt' else "where unrtf"
        subprocess.run(check_cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print(f"Error: 'unrtf' command not found or not executable in system PATH.")
        print("Please ensure 'unrtf' is installed and accessible.")
        print("(e.g., 'brew install unrtf' or 'sudo apt-get install unrtf')")
        return None
    except Exception as e:
         print(f"Error checking for unrtf: {e}")
         return None

    try:
        # Run unrtf to get HTML output
        result = subprocess.run(
            ['unrtf', '--html', rtf_path],
            capture_output=True,
            text=True, # Decode output as text
            check=True, # Raise exception for non-zero exit codes
            encoding='utf-8', # Assume unrtf outputs utf-8
            errors='ignore' # Ignore decoding errors if any
        )
        return result.stdout
    except FileNotFoundError:
        # This specific error usually means unrtf itself wasn't found,
        # even if the path check above passed (less likely but possible)
        print("Error: 'unrtf' command failed to execute. Is it installed correctly?")
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error running unrtf for file '{rtf_path}':")
        print(f"Exit Code: {e.returncode}")
        # Decode stderr if it's bytes
        stderr_output = e.stderr.decode('utf-8', errors='ignore') if isinstance(e.stderr, bytes) else e.stderr
        print(f"Stderr: {stderr_output}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while running unrtf: {e}")
        return None

def extract_rtf_sections_via_unrtf(rtf_path):
    """
    Extracts sections from an RTF file using unrtf and BeautifulSoup.
    Sections are based on bolded 'XX-XXX Title' patterns (which unrtf might change to 'XXXX Title')
    found in the HTML output.
    """
    if not os.path.exists(rtf_path):
         print(f"Error: Input file not found at '{rtf_path}'")
         return {}

    # 1. Convert RTF to HTML using unrtf
    html_content = run_unrtf(rtf_path)
    if html_content is None:
        print(f"Failed to get HTML content from '{rtf_path}' via unrtf.")
        return {} # Error message already printed by run_unrtf

    # Check if BeautifulSoup is available
    try:
        from bs4 import BeautifulSoup, NavigableString
    except ImportError:
        print("Error: 'beautifulsoup4' library not found. Cannot parse HTML.")
        print("Please install it using: pip install beautifulsoup4")
        return {}

    # 2. Parse the HTML
    soup = BeautifulSoup(html_content, 'html.parser')

    # Regex to find sequences of 4 or more digits
    section_id_pattern = re.compile(r"^(\\d{4,})")
    # Regex to clean non-digits
    non_digit_pattern = re.compile(r'\\D')

    sections = {}
    current_section_id = None
    current_section_content = []

    # 3. Iterate through potential section containers (paragraphs first)
    for element in soup.find_all(['p', 'div']): # Look in paragraphs or divs
        potential_id_text = ""
        is_bold_sequence = False
        title_part = ""

        # Check children for leading bold tags containing digits
        child_nodes = list(element.children)
        if child_nodes:
            first_non_empty_child_idx = 0
            # Skip initial whitespace nodes
            while first_non_empty_child_idx < len(child_nodes) and isinstance(child_nodes[first_non_empty_child_idx], NavigableString) and child_nodes[first_non_empty_child_idx].strip() == "":
                first_non_empty_child_idx += 1

            if first_non_empty_child_idx < len(child_nodes):
                first_tag = child_nodes[first_non_empty_child_idx]
                # Check if the first significant content is within a <b> tag
                if first_tag.name == 'b' or (isinstance(first_tag, NavigableString) and first_tag.parent.name == 'b'):
                    is_bold_sequence = True
                    # Concatenate text from consecutive bold tags at the start
                    temp_id_text = ""
                    processed_children = 0
                    for i in range(first_non_empty_child_idx, len(child_nodes)):
                        child = child_nodes[i]
                        if isinstance(child, NavigableString) and child.strip() == "":
                            processed_children += 1
                            continue # Skip whitespace between tags
                        if child.name == 'b':
                             # Also handle font tags inside bold tags if present
                             inner_text = child.get_text(strip=True)
                             temp_id_text += inner_text
                             processed_children += 1
                        else:
                             # Stop concatenation at the first non-bold tag/text
                             break
                    # Clean and check if it looks like a section ID
                    cleaned_id = non_digit_pattern.sub('', temp_id_text)
                    if len(cleaned_id) >= 4: # Check if we got enough digits
                         potential_id_text = cleaned_id


        is_section_start = False
        section_id_match = None
        full_element_text = element.get_text(" ", strip=True) # Full text for context

        if is_bold_sequence and potential_id_text:
             # We found a bold sequence yielding 4+ digits. Assume it's a heading.
             # Now extract the title part from the full text
             title_match = re.match(r"^\\s*\\d+\s*(.*)", full_element_text)
             title_part = title_match.group(1).strip() if title_match else ""
             section_id_match = re.match(section_id_pattern, potential_id_text) # Match on cleaned digits
             if section_id_match:
                  is_section_start = True

        # --- Logic to store previous section and start new one ---
        if is_section_start:
            if current_section_id:
                # Clean up trailing blank lines from the previous section
                while current_section_content and not current_section_content[-1].strip():
                    current_section_content.pop()
                sections[current_section_id] = "\\n".join(current_section_content).strip()

            # Start the new section
            captured_id = section_id_match.group(1) # The digits like "2040" or "20110"
            # Try to reconstruct the hyphenated ID
            if len(captured_id) == 4: # e.g., 2040 -> 20-40
                current_section_id = f"{captured_id[:2]}-{captured_id[2:]}"
            elif len(captured_id) == 5: # e.g., 10530 -> 105-30
                 current_section_id = f"{captured_id[:3]}-{captured_id[3:]}"
            elif len(captured_id) == 6: # e.g., 707250 -> 707-250 (Guessing based on pattern)
                 current_section_id = f"{captured_id[:3]}-{captured_id[3:]}"
            else:
                 current_section_id = captured_id # Keep as is for other lengths

            current_section_content = [full_element_text] # Start with the full heading line's text
            print(f"Found Section Start: {current_section_id} (Raw ID: {captured_id}) - Title: '{title_part[:50]}...'") # Debugging

        elif current_section_id:
            # Add paragraph content to the current section
            if full_element_text: # Add non-empty paragraphs
                current_section_content.append(full_element_text)
            # Add a single blank line to represent spacing, only if the last line wasn't blank
            elif current_section_content and current_section_content[-1].strip():
                 current_section_content.append("")

    # --- Store the very last section ---
    if current_section_id:
         # Clean up trailing blank lines
         while current_section_content and not current_section_content[-1].strip():
             current_section_content.pop()
         sections[current_section_id] = "\\n".join(current_section_content).strip()

    return sections

# --- Example Usage ---
if __name__ == "__main__":
    # Ensure bs4 is importable here as well, as it's needed for parsing
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Error message already printed at the top level
        sys.exit(1)

    if len(sys.argv) > 1:
        rtf_file = sys.argv[1]
    else:
        # Keep asking until a valid file path is given
        while True:
            rtf_file = input("Enter the path to the .rtf file: ")
            if os.path.exists(rtf_file):
                break
            else:
                print(f"Error: File not found at '{rtf_file}'. Please try again.")


    print(f"Processing RTF file: {rtf_file}")
    extracted_data = extract_rtf_sections_via_unrtf(rtf_file)

    if extracted_data:
        print(f"\\nSuccessfully extracted {len(extracted_data)} sections.")

        # Display preview (optional)
        # count = 0
        # for section_id, content in extracted_data.items():
        #     print("-" * 20)
        #     print(f"Section ID: {section_id}")
        #     print(f"Content Preview (first 100 chars):\\n{content[:100]}...")
        #     print("-" * 20)
        #     count += 1
        #     if count >= 3: break # Limit output if needed

        # Example: Save to a file (e.g., JSON)
        import json
        output_filename = os.path.splitext(os.path.basename(rtf_file))[0] + "_extracted.json"
        try:
            with open(output_filename, 'w', encoding='utf-8') as f_out:
                json.dump(extracted_data, f_out, indent=4, ensure_ascii=False)
            print(f"Extracted data saved to: {output_filename}")
        except Exception as e:
            print(f"Error saving data to JSON: {e}")

    else:
        print("Could not extract any sections. Check the RTF structure (bolded XXXX+ headings), the file itself, or the unrtf conversion.") 