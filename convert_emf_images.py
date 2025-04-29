import json
import base64
import subprocess
import tempfile
import os
import sys
import shutil
import copy
from bs4 import BeautifulSoup
import time
import re # Added for sanitization
from PIL import Image # Added for cropping

# --- Configuration ---
# INPUT_JSON_FILE = 'sections_mammoth_html.json' # No longer needed, taken from argv
# OUTPUT_JSON_FILE = 'sections_mammoth_display.json' # No longer needed, overwrites input
OUTPUT_IMAGE_DIR = 'images' # Relative path for converted PNGs
# Path to the LibreOffice executable
CONVERTER_COMMAND = 'libreoffice'
# Maximum number of retries for failed conversions
MAX_RETRIES = 2
# Delay between retries in seconds
RETRY_DELAY = 1
# --- End Configuration ---

def sanitize_filename(name):
    """Removes or replaces characters unsafe for filenames."""
    # Remove leading/trailing whitespace
    name = name.strip()
    # Replace problematic characters (e.g., spaces, slashes, colons) with underscores
    name = re.sub(r'[\/:"*?<>|\s]+', '_', name)
    # Limit length if necessary (optional)
    # max_len = 50
    # name = name[:max_len]
    return name

def crop_whitespace(image_path, padding=0, threshold=230):
    """Crops whitespace from an image file (in-place) using thresholding.

    Assumes background is light (close to white).

    Args:
        image_path (str): Path to the image file.
        padding (int): Optional padding to add around the cropped content.
        threshold (int): Pixel value (0-255) above which is considered background.
                         Lower for darker backgrounds, higher for lighter.
    """
    try:
        im = Image.open(image_path)
        original_im = im.copy() # Keep original for final crop
        
        # Convert to grayscale for easier thresholding
        im = im.convert("L") 
        
        # Create a binary mask: 0 for background, 255 for content
        # Pixels lighter than threshold become 0 (background)
        mask = im.point(lambda p: 0 if p > threshold else 255)
        
        # Invert the mask so that content is non-zero (required by getbbox)
        # mask_inverted = Image.eval(mask, lambda p: 255 - p)
        # Actually, getbbox finds non-zero, so the mask above is correct (content=255)

        # Get the bounding box of the non-background pixels from the mask
        bbox = mask.getbbox()

        if bbox:
            # Add padding to the bounding box found from the mask
            left = max(0, bbox[0] - padding)
            top = max(0, bbox[1] - padding)
            right = min(original_im.width, bbox[2] + padding)
            bottom = min(original_im.height, bbox[3] + padding)

            # Ensure the box has valid dimensions after padding
            if right > left and bottom > top:
                # Crop the *original* image using the calculated box
                cropped_im = original_im.crop((left, top, right, bottom))
                # Overwrite the original file with the cropped version
                cropped_im.save(image_path)
                print(f"      Successfully cropped whitespace from {os.path.basename(image_path)} using thresholding to box ({bbox[0]},{bbox[1]})-({bbox[2]},{bbox[3]}).")
            else:
                print(f"      Skipping crop for {os.path.basename(image_path)}: Bounding box became invalid after padding.")
        else:
            # Handle case where image might be entirely background according to threshold
            print(f"      Skipping crop for {os.path.basename(image_path)}: Could not find content bounding box using threshold {threshold}.")

    except FileNotFoundError:
        print(f"      Error cropping: File not found at {image_path}", file=sys.stderr)
    except Exception as e:
        print(f"      Error cropping {os.path.basename(image_path)}: {e}", file=sys.stderr)

def check_dependencies():
    """Checks if the required converter command is available."""
    global CONVERTER_COMMAND
    converter_path = shutil.which(CONVERTER_COMMAND)

    if converter_path is None:
        # Check common macOS installation paths
        macos_paths = [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice.bin"
        ]
        for path in macos_paths:
            if os.path.exists(path):
                print(f"Info: Using LibreOffice found at {path}")
                CONVERTER_COMMAND = path
                converter_path = path
                break
        else:
            print(f"Error: '{CONVERTER_COMMAND}' command not found.", file=sys.stderr)
            print("Please install LibreOffice and ensure it is accessible from your PATH,", file=sys.stderr)
            print("or update the CONVERTER_COMMAND variable in the script.", file=sys.stderr)
            print("Installation instructions: https://www.libreoffice.org/download/download/", file=sys.stderr)
            return False

    if not os.access(converter_path, os.X_OK):
         print(f"Error: Found '{converter_path}' but it is not executable.", file=sys.stderr)
         return False

    print(f"Using converter: {CONVERTER_COMMAND}")
    return True

def convert_emf_data_to_png_file(emf_base64_data, output_png_path, section_key_for_error_msg):
    """
    Converts base64 encoded EMF data to a PNG file saved at output_png_path
    using LibreOffice with retry logic.
    Returns True on success, False on failure.
    """
    if not emf_base64_data:
        return False

    try:
        emf_binary_data = base64.b64decode(emf_base64_data)
    except base64.binascii.Error as e:
        print(f"  Error decoding base64 EMF data for section {section_key_for_error_msg}: {e}", file=sys.stderr)
        return False

    conversion_success = False
    temp_emf_path = None
    temp_out_dir = None
    retry_count = 0
    expected_png_filename_in_temp = None

    while retry_count <= MAX_RETRIES:
        try:
            # Create temp file for EMF and a temp dir for PNG output
            temp_emf_fd, temp_emf_path = tempfile.mkstemp(suffix=".emf")
            os.close(temp_emf_fd)
            temp_out_dir = tempfile.mkdtemp()

            # Expected filename LibreOffice will create in temp_out_dir
            expected_png_filename_in_temp = os.path.splitext(os.path.basename(temp_emf_path))[0] + '.png'
            expected_png_fullpath_in_temp = os.path.join(temp_out_dir, expected_png_filename_in_temp)

            # Write EMF data to temp file
            with open(temp_emf_path, 'wb') as temp_emf_file:
                temp_emf_file.write(emf_binary_data)

            # Run LibreOffice command
            cmd = [
                CONVERTER_COMMAND,
                '--headless',
                '--convert-to', 'png',
                '--outdir', temp_out_dir, # Output to temp dir
                temp_emf_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            # Check if the expected output file was created and is valid
            if os.path.exists(expected_png_fullpath_in_temp) and os.path.getsize(expected_png_fullpath_in_temp) > 0:
                # Move the converted file to the final destination
                try:
                    shutil.move(expected_png_fullpath_in_temp, output_png_path)
                    print(f"    Successfully converted and saved to {output_png_path}")
                    
                    # --- Add cropping step --- 
                    print(f"      Attempting to crop whitespace...")
                    crop_whitespace(output_png_path) # Crop the resulting PNG
                    # --- End cropping step ---
                    
                    conversion_success = True
                    break  # Success, exit retry loop
                except OSError as move_err:
                     print(f"  Error moving converted PNG from temp to {output_png_path}: {move_err}", file=sys.stderr)
                     # Fall through to retry or fail

            # If we get here, conversion failed or move failed
            if retry_count < MAX_RETRIES:
                print(f"  Conversion/Save attempt {retry_count + 1} failed for image in section '{section_key_for_error_msg}'. Retrying...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  LibreOffice conversion failed after {MAX_RETRIES + 1} attempts for image in section '{section_key_for_error_msg}':", file=sys.stderr)
                if result.stderr:
                    print(f"  Stderr: {result.stderr.strip()}", file=sys.stderr)
                if result.stdout:
                    print(f"  Stdout: {result.stdout.strip()}", file=sys.stderr)

        except Exception as e:
            print(f"  Error during conversion attempt {retry_count + 1} for image in section '{section_key_for_error_msg}': {e}", file=sys.stderr)
            if retry_count < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        finally:
            # Clean up temporary file and directory
            if temp_emf_path and os.path.exists(temp_emf_path):
                try:
                    os.remove(temp_emf_path)
                except OSError as e:
                    print(f"  Warning: Could not remove temp EMF file {temp_emf_path}: {e}", file=sys.stderr)
            if temp_out_dir and os.path.exists(temp_out_dir):
                 try:
                     shutil.rmtree(temp_out_dir)
                 except OSError as e:
                     print(f"  Warning: Could not remove temp output dir {temp_out_dir}: {e}", file=sys.stderr)

        retry_count += 1

    return conversion_success

def process_json_images(json_filepath):
    """
    Loads the input JSON, processes HTML content to convert EMF images
    to PNG files saved in OUTPUT_IMAGE_DIR, updates the HTML snippets
    with relative paths to the PNGs, and overwrites the input JSON file.
    """
    print(f"Loading data from {json_filepath}...")
    try:
        with open(json_filepath, 'r', encoding='utf-8') as f:
            # Use copy.deepcopy if you want to avoid modifying the original dict during iteration
            # data = json.load(f)
            # processed_data = copy.deepcopy(data) 
            # Or load directly if modification during iteration is safe (should be here)
            processed_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found at {json_filepath}", file=sys.stderr)
        return
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {json_filepath}: {e}", file=sys.stderr)
        return
    except Exception as e:
        print(f"Error reading input file {json_filepath}: {e}", file=sys.stderr)
        return

    # Ensure the output directory for images exists
    try:
        os.makedirs(OUTPUT_IMAGE_DIR, exist_ok=True)
        print(f"Ensured image output directory exists: '{OUTPUT_IMAGE_DIR}'")
    except OSError as e:
        print(f"Error creating output directory '{OUTPUT_IMAGE_DIR}': {e}", file=sys.stderr)
        return

    total_sections = len(processed_data)
    print(f"Found {total_sections} sections to process.")

    processed_count = 0
    converted_images = 0
    conversion_errors = 0

    for section_key, section_data in processed_data.items():
        processed_count += 1
        if processed_count % 50 == 0 or processed_count == total_sections:
             print(f"Processing section {processed_count}/{total_sections} ('{section_key}')...")

        if not isinstance(section_data, dict) or 'html' not in section_data:
            print(f"  Skipping section '{section_key}': Invalid format or missing 'html' key.", file=sys.stderr)
            continue

        html_content = section_data.get('html', '')
        if not html_content:
            continue

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            images_found_in_section = False
            modified = False
            img_index = 0 # Counter for images within this section

            for img_tag in soup.find_all('img'):
                src = img_tag.get('src', '')
                if src.startswith('data:image/x-emf;base64,'):
                    images_found_in_section = True
                    print(f"  Found EMF image {img_index} in section '{section_key}'. Attempting conversion...")
                    emf_base64 = src.split(',', 1)[1]

                    # Generate filename for the PNG
                    safe_section_key = sanitize_filename(section_key)
                    png_filename = f"section_{safe_section_key}_img_{img_index}.png"
                    output_png_filepath = os.path.join(OUTPUT_IMAGE_DIR, png_filename)
                    relative_png_path = os.path.join(OUTPUT_IMAGE_DIR, png_filename) # Path for HTML src

                    # Convert and save the PNG file
                    success = convert_emf_data_to_png_file(emf_base64, output_png_filepath, section_key)

                    if success:
                        # Update the img src tag in the parsed HTML
                        img_tag['src'] = relative_png_path
                        img_tag['alt'] = img_tag.get('alt', '') + " (converted to PNG)"
                        converted_images += 1
                        modified = True
                    else:
                        print(f"    Conversion failed for image {img_index} in '{section_key}'. Keeping original EMF src.", file=sys.stderr)
                        conversion_errors += 1

                    img_index += 1 # Increment index for the next image in this section

            if modified:
                # Update the HTML in the main dictionary
                processed_data[section_key]['html'] = str(soup)

        except Exception as e:
             print(f"  Error processing HTML for section '{section_key}': {e}", file=sys.stderr)
             # Revert? For now, we keep potentially partial modifications if error occurs mid-section
             # processed_data[section_key]['html'] = html_content # Option to revert

    print("Processing complete.")
    print(f"Total images successfully converted and saved: {converted_images}")
    if conversion_errors > 0:
        print(f"Total image conversion errors: {conversion_errors}", file=sys.stderr)

    print(f"Saving updated data back to {json_filepath}...")
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(processed_data, f, indent=4, ensure_ascii=False)
        print("Successfully saved updated data.")
    except Exception as e:
        print(f"Error saving updated data to JSON file {json_filepath}: {e}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <input_json_file>")
        sys.exit(1)

    input_json_path = sys.argv[1]

    if not os.path.exists(input_json_path):
        print(f"Error: Input JSON file not found at '{input_json_path}'", file=sys.stderr)
        sys.exit(1)

    if check_dependencies():
        process_json_images(input_json_path)
    else:
        sys.exit(1)
        