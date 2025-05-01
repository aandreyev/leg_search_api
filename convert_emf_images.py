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
import logging

# --- Configuration (Defaults/Constants) ---
DEFAULT_OUTPUT_IMAGE_SUBDIR = 'Images' # Subdirectory name for saved intermediate PNGs
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
    # Replace problematic characters with underscores
    name = re.sub(r'[\/:"*?<>|\s\\]+', '_', name) # Added backslash to problematic chars
    # Limit length if necessary (optional)
    max_len = 50
    name = name[:max_len]
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
        with Image.open(image_path) as im:
            original_im = im.copy() # Keep original for final crop

            # Convert to grayscale for easier thresholding
            im_gray = im.convert("L")

            # Create a binary mask: 0 for background, 255 for content
            mask = im_gray.point(lambda p: 0 if p > threshold else 255)

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
                    logging.debug(f"      Successfully cropped whitespace from {os.path.basename(image_path)} using thresholding to box ({bbox[0]},{bbox[1]})-({bbox[2]},{bbox[3]}).")
                else:
                    logging.debug(f"      Skipping crop for {os.path.basename(image_path)}: Bounding box became invalid after padding.")
            else:
                # Handle case where image might be entirely background according to threshold
                logging.debug(f"      Skipping crop for {os.path.basename(image_path)}: Could not find content bounding box using threshold {threshold}.")

    except FileNotFoundError:
        logging.error(f"      Error cropping: File not found at {image_path}")
    except Exception as e:
        logging.error(f"      Error cropping {os.path.basename(image_path)}: {e}")

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
            if os.path.exists(path) and os.access(path, os.X_OK):
                logging.info(f"Using LibreOffice found at {path}")
                CONVERTER_COMMAND = path
                converter_path = path
                break
        else:
            logging.critical(f"'{CONVERTER_COMMAND}' command not found or not executable.")
            logging.critical("Please install LibreOffice and ensure it is accessible from your PATH,")
            logging.critical("or update the CONVERTER_COMMAND variable in the script.")
            logging.critical("Installation instructions: https://www.libreoffice.org/download/download/")
            return False

    logging.info(f"Using converter: {CONVERTER_COMMAND}")
    return True

def convert_emf_data_to_png_file(emf_base64_data, output_png_path, section_key_for_error_msg):
    """
    Converts base64 encoded EMF/WMF data to a PNG file saved at output_png_path,
    reads the PNG, encodes it as Base64, and returns a data URI string.
    Returns data URI string on success, None on failure.
    """
    if not emf_base64_data:
        return None

    try:
        emf_binary_data = base64.b64decode(emf_base64_data)
    except base64.binascii.Error as e:
        logging.error(f"  Error decoding base64 EMF/WMF data for section {section_key_for_error_msg}: {e}")
        return None

    temp_emf_path = None
    temp_out_dir = None
    retry_count = 0
    base64_data_uri = None
    result_info = None

    while retry_count <= MAX_RETRIES:
        temp_emf_path = None
        temp_out_dir = None
        try:
            # Create temp file for EMF/WMF and a temp dir for PNG output
            temp_emf_fd, temp_emf_path = tempfile.mkstemp(suffix=".bin")
            os.close(temp_emf_fd)
            temp_out_dir = tempfile.mkdtemp()

            # Expected filename LibreOffice will create in temp_out_dir
            expected_png_filename_in_temp = os.path.splitext(os.path.basename(temp_emf_path))[0] + '.png'
            expected_png_fullpath_in_temp = os.path.join(temp_out_dir, expected_png_filename_in_temp)

            # Write EMF/WMF data to temp file
            with open(temp_emf_path, 'wb') as temp_emf_file:
                temp_emf_file.write(emf_binary_data)

            # Run LibreOffice command
            cmd = [
                CONVERTER_COMMAND,
                '--headless',
                '--convert-to', 'png',
                '--outdir', temp_out_dir,
                temp_emf_path
            ]
            logging.debug(f"    Running conversion: {' '.join(cmd)}")
            result_info = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30) # Added timeout

            # Check if the expected output file was created and is valid
            if os.path.exists(expected_png_fullpath_in_temp) and os.path.getsize(expected_png_fullpath_in_temp) > 0:
                try:
                    # Ensure output dir for final PNG exists
                    os.makedirs(os.path.dirname(output_png_path), exist_ok=True)
                    # Move first to ensure it's safe before reading/cropping
                    shutil.move(expected_png_fullpath_in_temp, output_png_path)
                    logging.info(f"    Successfully converted and saved intermediate PNG to {os.path.basename(output_png_path)}")

                    # --- Crop whitespace ---
                    logging.debug(f"      Attempting to crop whitespace from {os.path.basename(output_png_path)}...")
                    crop_whitespace(output_png_path)
                    # --- End cropping step ---

                    # --- Read FINAL (cropped) PNG and encode to Base64 ---
                    logging.debug(f"      Reading final PNG and encoding to Base64...")
                    with open(output_png_path, 'rb') as png_file:
                        png_binary_data = png_file.read()
                    base64_encoded_string = base64.b64encode(png_binary_data).decode('utf-8')
                    base64_data_uri = f"data:image/png;base64,{base64_encoded_string}"
                    logging.debug(f"      Generated Base64 Data URI (length: {len(base64_data_uri)}).")
                    # --- End Base64 encoding ---

                    # --- Optional: Clean up the intermediate PNG file ---
                    # try:
                    #     os.remove(output_png_path)
                    #     logging.debug(f"      Removed intermediate PNG file: {os.path.basename(output_png_path)}")
                    # except OSError as e:
                    #     logging.warning(f"      Could not remove intermediate PNG file {output_png_path}: {e}")
                    # --- End Optional Cleanup ---

                    break  # Success, exit retry loop

                except OSError as move_err:
                     logging.error(f"  Error moving converted PNG from temp to {output_png_path}: {move_err}")
                except FileNotFoundError:
                    logging.error(f"  Error reading saved PNG file for Base64 encoding: {output_png_path}")
                except Exception as e:
                    logging.error(f"  Error during post-conversion (crop/read/encode) for {output_png_path}: {e}")
                     # Fall through to retry or fail
            else:
                # Conversion failed to produce output file
                if retry_count >= MAX_RETRIES:
                    logging.error(f"  Image processing failed after {MAX_RETRIES + 1} attempts for image in section '{section_key_for_error_msg}':")
                    if result_info and result_info.stderr:
                        logging.error(f"  LibreOffice Stderr: {result_info.stderr.strip()}")
                    if result_info and result_info.stdout:
                        logging.error(f"  LibreOffice Stdout: {result_info.stdout.strip()}")
                    if not os.path.exists(expected_png_fullpath_in_temp):
                        logging.error(f"  Reason: Output file was not created in temp dir ({expected_png_fullpath_in_temp}).")
                    elif os.path.getsize(expected_png_fullpath_in_temp) == 0:
                        logging.error(f"  Reason: Output file was created but empty in temp dir ({expected_png_fullpath_in_temp}).")

            # Retry if attempts remain
            if retry_count < MAX_RETRIES:
                logging.warning(f"  Image processing attempt {retry_count + 1} failed for section '{section_key_for_error_msg}'. Retrying...")
                time.sleep(RETRY_DELAY)

        except subprocess.TimeoutExpired:
             logging.error(f"  LibreOffice command timed out after 30 seconds during attempt {retry_count + 1} for image in section '{section_key_for_error_msg}'.")
             if retry_count >= MAX_RETRIES:
                  logging.error("  Conversion failed due to timeout.")
             else:
                  time.sleep(RETRY_DELAY) # Wait before retry on timeout
        except Exception as e:
            logging.error(f"  Unexpected error during conversion attempt {retry_count + 1} for image in section '{section_key_for_error_msg}': {e}")
            if retry_count < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        finally:
            # Clean up temporary file and directory
            if temp_emf_path and os.path.exists(temp_emf_path):
                try: os.remove(temp_emf_path)
                except OSError as e: logging.warning(f"Could not remove temp input file {temp_emf_path}: {e}")
            if temp_out_dir and os.path.exists(temp_out_dir):
                 try: shutil.rmtree(temp_out_dir)
                 except OSError as e: logging.warning(f"Could not remove temp output dir {temp_out_dir}: {e}")

        retry_count += 1

    return base64_data_uri # Return URI string or None

def process_json_images(input_json_filepath, output_json_filepath):
    """
    Loads the input JSON, processes HTML content to convert EMF/WMF images
    to PNG data URIs, updates the HTML snippets, and saves the result
    to the output JSON file.
    """
    logging.info("--- Starting Metafile Image Conversion to Base64 ---")
    logging.info(f"Loading data from {input_json_filepath}...")
    try:
        with open(input_json_filepath, 'r', encoding='utf-8') as f:
            processed_data = json.load(f)
    except FileNotFoundError:
        logging.critical(f"Input file not found at {input_json_filepath}")
        return False
    except json.JSONDecodeError as e:
        logging.critical(f"Error decoding JSON from {input_json_filepath}: {e}")
        return False
    except Exception as e:
        logging.critical(f"Error reading input file {input_json_filepath}: {e}")
        return False

    # Determine the base directory for SAVING INTERMEDIATE PNGs
    output_base_dir = os.path.dirname(output_json_filepath) or '.'
    image_output_dir_abs = os.path.join(output_base_dir, DEFAULT_OUTPUT_IMAGE_SUBDIR)

    # Ensure the output directory for INTERMEDIATE images exists
    try:
        os.makedirs(image_output_dir_abs, exist_ok=True)
        logging.info(f"Ensured intermediate image output directory exists: '{image_output_dir_abs}'")
    except OSError as e:
        logging.error(f"Error creating intermediate image directory '{image_output_dir_abs}': {e}")
        return False

    total_sections = len(processed_data)
    logging.info(f"Found {total_sections} sections to process.")

    processed_count = 0
    converted_images = 0
    conversion_errors = 0

    # Create a deep copy to modify, avoiding issues with iterating and modifying
    output_data = copy.deepcopy(processed_data)

    for section_key, section_data in output_data.items(): # Iterate over the copy
        processed_count += 1
        if processed_count % 50 == 0 or processed_count == total_sections:
             logging.info(f"Processing section {processed_count}/{total_sections} ('{section_key}')...")

        if not isinstance(section_data, dict) or 'html' not in section_data:
            logging.warning(f"  Skipping section '{section_key}': Invalid format or missing 'html' key.")
            continue

        html_content = section_data.get('html', '')
        if not html_content:
            continue

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            modified = False
            img_index = 0

            for img_tag in soup.find_all('img'):
                src = img_tag.get('src', '')
                if src.startswith(('data:image/x-emf;base64,', 'data:image/x-wmf;base64,')):
                    logging.debug(f"  Found Metafile image (EMF/WMF) {img_index} in section '{section_key}'. Attempting conversion...")
                    emf_base64 = src.split(',', 1)[1]

                    # Generate filename for the intermediate PNG
                    safe_section_key = sanitize_filename(section_key)
                    png_filename = f"section_{safe_section_key}_img_{img_index}.png"
                    output_png_filepath_abs = os.path.join(image_output_dir_abs, png_filename)

                    # Convert, save PNG (intermediate), and get Base64 URI
                    base64_data_uri = convert_emf_data_to_png_file(emf_base64, output_png_filepath_abs, section_key)

                    if base64_data_uri:
                        # Update the img src tag with the Base64 URI
                        img_tag['src'] = base64_data_uri
                        # Retain original alt text if present, append note
                        original_alt = img_tag.get('alt', '')
                        img_tag['alt'] = f"{original_alt} (converted to PNG)".strip()
                        converted_images += 1
                        modified = True
                        logging.debug(f"    Updated src for image {img_index} in section '{section_key}' to data URI.")
                    else:
                        logging.warning(f"    Conversion failed for image {img_index} in '{section_key}'. Keeping original EMF/WMF src.")
                        conversion_errors += 1

                    img_index += 1

            if modified:
                # Update the HTML in the output dictionary
                output_data[section_key]['html'] = str(soup)

        except Exception as e:
             logging.error(f"  Error processing HTML for section '{section_key}': {e}")
             # Continue processing other sections

    logging.info("Image processing complete.")
    logging.info(f"Total images successfully converted and embedded: {converted_images}")
    if conversion_errors > 0:
        logging.warning(f"Total image conversion errors: {conversion_errors}")

    logging.info(f"Saving updated data to {output_json_filepath}...")
    try:
        with open(output_json_filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False) # Save the modified copy
        logging.info("Successfully saved updated data.")
        logging.info("--- Finished Metafile Image Conversion (successfully) ---")
        return True
    except Exception as e:
        logging.error(f"Error saving updated data to JSON file {output_json_filepath}: {e}")
        logging.error("--- Finished Metafile Image Conversion (with error) ---")
        return False

if __name__ == "__main__":
    # --- Configure Logging ---
    log_filename = 'convert_emf_images.log' # Specific log file name
    logging.basicConfig(
        level=logging.INFO, # Default level INFO
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=log_filename,
        filemode='w' # Overwrite log file each time
    )
    # Add handler for console output (INFO and above)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)
    # Set higher level for noisy libraries if needed, e.g.:
    # logging.getLogger("PIL").setLevel(logging.WARNING)
    # --- End Logging Configuration ---

    if len(sys.argv) != 3:
        logging.critical(f"Usage: python {os.path.basename(__file__)} <input_json_file> <output_json_file>")
        sys.exit(1)

    input_json_path = sys.argv[1]
    output_json_path = sys.argv[2]

    if not os.path.exists(input_json_path):
        logging.critical(f"Input JSON file not found at '{input_json_path}'")
        sys.exit(1)

    output_dir = os.path.dirname(output_json_path) or '.'
    if output_dir != '.':
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            logging.critical(f"Could not create output directory '{output_dir}': {e}")
            sys.exit(1)

    if check_dependencies():
        success = process_json_images(input_json_path, output_json_path)
        if not success:
             logging.critical("Processing failed.")
             sys.exit(1)
        else:
            logging.info("Processing completed successfully.")
    else:
        logging.critical("Dependency check failed. Exiting.")
        sys.exit(1)
        