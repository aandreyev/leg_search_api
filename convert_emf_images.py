import json
import base64
import subprocess
import tempfile
import os
import sys
import shutil
import copy
from bs4 import BeautifulSoup

# --- Configuration ---
INPUT_JSON_FILE = 'sections_mammoth_html.json'
OUTPUT_JSON_FILE = 'sections_mammoth_display.json'
# Path to the 'inkscape' executable
# If 'inkscape' is in your system's PATH (or Applications folder symlink for macOS), you can often just use 'inkscape'
# Otherwise, provide the full path, e.g., '/Applications/Inkscape.app/Contents/MacOS/inkscape'
CONVERTER_COMMAND = 'inkscape' # Changed from CONVERT_COMMAND
# --- End Configuration ---

def check_dependencies():
    """Checks if the required converter command is available."""
    global CONVERTER_COMMAND # Allow modification of the global variable
    converter_path = shutil.which(CONVERTER_COMMAND)

    if converter_path is None:
        # Specific check for macOS common install location if `which` fails
        macos_path = "/Applications/Inkscape.app/Contents/MacOS/inkscape"
        if sys.platform == "darwin" and os.path.exists(macos_path):
            print(f"Info: Using Inkscape found at {macos_path}")
            CONVERTER_COMMAND = macos_path # Use the full path
            converter_path = macos_path # Set for return check
        else:
            print(f"Error: '{CONVERTER_COMMAND}' command not found.", file=sys.stderr)
            print("Please install Inkscape and ensure it is accessible from your PATH,", file=sys.stderr)
            print("or update the CONVERTER_COMMAND variable in the script.", file=sys.stderr)
            print("Installation instructions: https://inkscape.org/release/inkscape-1.3.2/", file=sys.stderr)
            return False

    # Optional: Check if the found command is executable
    if not os.access(converter_path, os.X_OK):
         print(f"Error: Found '{converter_path}' but it is not executable.", file=sys.stderr)
         return False

    print(f"Using converter: {CONVERTER_COMMAND}")
    return True

def convert_emf_to_png_base64(emf_base64_data):
    """
    Converts base64 encoded EMF data to base64 encoded PNG data
    using the external Inkscape command.
    Returns the PNG base64 string or None if conversion fails.
    """
    if not emf_base64_data:
        return None

    try:
        emf_binary_data = base64.b64decode(emf_base64_data)
    except base64.binascii.Error as e:
        print(f"  Error decoding base64 EMF data: {e}", file=sys.stderr)
        return None

    png_base64_string = None
    # Use temporary files for conversion
    temp_emf_path = None # Ensure paths are defined for finally block
    temp_png_path = None
    try:
        # Create temp files manually to control deletion better
        temp_emf_fd, temp_emf_path = tempfile.mkstemp(suffix=".emf")
        temp_png_fd, temp_png_path = tempfile.mkstemp(suffix=".png")
        os.close(temp_emf_fd) # Close file descriptors, we only need the path
        os.close(temp_png_fd)

        # Write EMF data to temp file
        with open(temp_emf_path, 'wb') as temp_emf_file:
            temp_emf_file.write(emf_binary_data)

        # Run Inkscape command
        # Options might vary slightly between Inkscape versions
        cmd = [
            CONVERTER_COMMAND,
            temp_emf_path,
            '--export-type=png',
            f'--export-filename={temp_png_path}'
            # Add other options if needed, e.g., --export-dpi=96
        ]
        # print(f"  Running command: {' '.join(cmd)}") # Optional: for debugging
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            # Inkscape often prints warnings to stderr even on success, check stdout too
            print(f"  Inkscape conversion may have failed or warned (return code {result.returncode}):", file=sys.stderr)
            if result.stderr:
                 print(f"  Stderr: {result.stderr.strip()}", file=sys.stderr)
            if result.stdout:
                 print(f"  Stdout: {result.stdout.strip()}", file=sys.stderr)
            # Continue to check if the file was actually created despite warnings/errors

        # Check if the output file was actually created and is not empty
        if os.path.exists(temp_png_path) and os.path.getsize(temp_png_path) > 0:
            # Read the converted PNG data
            with open(temp_png_path, 'rb') as temp_png_file:
                png_binary_data = temp_png_file.read()

            if png_binary_data:
                # Encode PNG data to base64
                png_base64_string = base64.b64encode(png_binary_data).decode('utf-8')
        elif result.returncode == 0:
             # If Inkscape reported success but the file is bad, log that
             print(f"  Inkscape ran successfully but output file '{temp_png_path}' is missing or empty.", file=sys.stderr)
        # else: Inkscape failed and file is missing/empty, error already logged

    except FileNotFoundError:
         print(f"  Error: '{CONVERTER_COMMAND}' command failed. Is Inkscape installed and accessible?", file=sys.stderr)
    except Exception as e:
        print(f"  An error occurred during file handling or conversion: {e}", file=sys.stderr)
    finally:
        # Clean up temporary files
        if temp_emf_path and os.path.exists(temp_emf_path):
            try:
                os.remove(temp_emf_path)
            except OSError as e:
                print(f"  Warning: Could not remove temp file {temp_emf_path}: {e}", file=sys.stderr)
        if temp_png_path and os.path.exists(temp_png_path):
             try:
                os.remove(temp_png_path)
             except OSError as e:
                print(f"  Warning: Could not remove temp file {temp_png_path}: {e}", file=sys.stderr)

    return png_base64_string

def process_json_images(input_filepath, output_filepath):
    """
    Loads the input JSON, processes HTML content to convert EMF images
    to PNG data URIs, and saves to the output JSON.
    """
    print(f"Loading data from {input_filepath}...")
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_filepath}", file=sys.stderr)
        return
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {input_filepath}: {e}", file=sys.stderr)
        return
    except Exception as e:
        print(f"Error reading input file {input_filepath}: {e}", file=sys.stderr)
        return

    # Create a deep copy to modify, preserving the original data structure
    processed_data = copy.deepcopy(data)
    total_sections = len(processed_data)
    print(f"Found {total_sections} sections to process.")

    processed_count = 0
    converted_images = 0
    conversion_errors = 0

    # Iterate through each section
    for section_key, section_data in processed_data.items():
        processed_count += 1
        if processed_count % 50 == 0 or processed_count == total_sections:
             print(f"Processing section {processed_count}/{total_sections} ('{section_key}')...")

        if not isinstance(section_data, dict) or 'html' not in section_data:
            print(f"  Skipping section '{section_key}': Invalid format or missing 'html' key.", file=sys.stderr)
            continue

        html_content = section_data.get('html', '')
        if not html_content:
            # print(f"  Skipping section '{section_key}': Empty HTML content.")
            continue

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            images_found_in_section = False
            modified = False

            # Find all image tags
            for img_tag in soup.find_all('img'):
                src = img_tag.get('src', '')
                # Check if it's an embedded EMF image
                if src.startswith('data:image/x-emf;base64,'):
                    images_found_in_section = True
                    print(f"  Found EMF image in section '{section_key}'. Attempting conversion...")
                    emf_base64 = src.split(',', 1)[1] # Get the base64 part

                    # Convert EMF to PNG base64
                    png_base64 = convert_emf_to_png_base64(emf_base64)

                    if png_base64:
                        # Update the src attribute with the PNG data URI
                        img_tag['src'] = f"data:image/png;base64,{png_base64}"
                        img_tag['alt'] = img_tag.get('alt', '') + " (converted to PNG)" # Optional: update alt text
                        print(f"    Successfully converted and updated src for image in '{section_key}'.")
                        converted_images += 1
                        modified = True
                    else:
                        print(f"    Conversion failed for image in '{section_key}'. Keeping original EMF src.", file=sys.stderr)
                        conversion_errors += 1
                        # Optionally remove the tag or leave it as is
                        # img_tag.decompose() # Remove tag if conversion fails

            # If modifications were made, update the HTML string in the dictionary
            if modified:
                processed_data[section_key]['html'] = str(soup)
            # elif images_found_in_section:
            #     print(f"  Found img tags in '{section_key}' but none were EMF data URIs.")

        except Exception as e:
             print(f"  Error processing HTML for section '{section_key}': {e}", file=sys.stderr)
             # Decide how to handle errors, e.g., skip the section or keep original html
             processed_data[section_key]['html'] = html_content # Keep original on error

    print("\nProcessing complete.")
    print(f"Total images successfully converted: {converted_images}")
    if conversion_errors > 0:
        print(f"Total image conversion errors: {conversion_errors}", file=sys.stderr)

    # Save the processed data to the output file
    print(f"Saving processed data to {output_filepath}...")
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            json.dump(processed_data, f, indent=4, ensure_ascii=False)
        print("Successfully saved processed data.")
    except Exception as e:
        print(f"Error saving data to JSON file {output_filepath}: {e}", file=sys.stderr)

if __name__ == "__main__":
    if check_dependencies():
        process_json_images(INPUT_JSON_FILE, OUTPUT_JSON_FILE)
    else:
        sys.exit(1) # Exit with error code if dependency check fails
        