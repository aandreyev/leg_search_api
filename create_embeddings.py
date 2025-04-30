import json
from sentence_transformers import SentenceTransformer
import numpy as np
import time # Optional: for timing the process
import sys # Import sys for command-line arguments
import os # Import os for path operations

# --- Configuration (Defaults/Constants) ---
# INPUT_JSON_FILE = 'sections_mammoth_html.json' # Replaced by sys.argv
# OUTPUT_JSON_FILE = 'sections_with_embeddings.json' # Replaced by sys.argv
MODEL_NAME = 'BAAI/bge-large-en-v1.5'
# Set batch size based on your available memory (GPU or CPU)
# Lower this if you encounter memory errors
BATCH_SIZE = 32
# --- Configuration End ---

def load_json_data(filepath):
    """Loads data from a JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"Successfully loaded data from {filepath}")
        return data
    except FileNotFoundError:
        print(f"Error: Input JSON file not found at {filepath}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {filepath}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while loading {filepath}: {e}")
        return None

def save_json_data(data, filepath):
    """Saves data to a JSON file."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            # Use numpy encoder to handle potential numpy types if needed,
            # though we convert embeddings to lists manually below.
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved data with embeddings to {filepath}")
    except Exception as e:
        print(f"Error saving data to JSON: {e}")

def main(input_filepath, output_filepath):
    print("--- Starting Embedding Creation ---") # Added start marker
    # Load the data
    sections_data = load_json_data(input_filepath)
    if not sections_data or not isinstance(sections_data, dict):
        print("Exiting due to issues loading or validating input JSON data.")
        sys.exit(1) # Exit if loading fails

    # Prepare texts and corresponding keys for embedding
    keys_list = []
    texts_to_embed = []
    valid_section_count = 0
    for key, section_info in sections_data.items():
        if isinstance(section_info, dict) and 'text_for_embedding' in section_info:
            text = section_info['text_for_embedding']
            # Ensure text is a non-empty string before adding
            if isinstance(text, str) and text.strip():
                keys_list.append(key)
                texts_to_embed.append(text)
                valid_section_count += 1
            else:
                 print(f"Warning: Skipping section '{key}' due to missing, empty, or non-string 'text_for_embedding'.")
        else:
            print(f"Warning: Skipping section '{key}' due to unexpected format or missing 'text_for_embedding'.")

    if not texts_to_embed:
        print("No valid texts found to embed. Saving original data (or empty if none loaded).")
        # Optionally save the original (potentially filtered) data back or just exit
        save_json_data(sections_data, output_filepath) # Save even if no embeddings generated
        sys.exit(0) # Exit successfully, as no work needed

    print(f"Found {valid_section_count} sections with valid text to embed.")

    # Load the embedding model
    print(f"Loading embedding model: {MODEL_NAME}...")
    try:
        model = SentenceTransformer(MODEL_NAME)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Error loading SentenceTransformer model: {e}")
        sys.exit(1) # Exit if model loading fails

    # Generate embeddings in batches
    print(f"Generating embeddings for {len(texts_to_embed)} texts (batch size: {BATCH_SIZE})...")
    start_time = time.time()
    all_embeddings = model.encode(
        texts_to_embed,
        batch_size=BATCH_SIZE,
        show_progress_bar=True # Shows a progress bar during encoding
    )
    end_time = time.time()
    print(f"Embeddings generated in {end_time - start_time:.2f} seconds.")

    # Add embeddings back to the original data structure
    print("Adding embeddings to the data structure...")
    for i, key in enumerate(keys_list):
        # Convert numpy array to list for JSON serialization
        sections_data[key]['embedding'] = all_embeddings[i].tolist()

    # Save the updated data
    save_json_data(sections_data, output_filepath)
    print("--- Finished Embedding Creation --- N") # Added end marker

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python {os.path.basename(sys.argv[0])} <input_json_file> <output_json_file>")
        sys.exit(1)

    input_json_path = sys.argv[1]
    output_json_path = sys.argv[2]

    # Ensure input file exists
    if not os.path.exists(input_json_path):
        print(f"Error: Input JSON file not found at '{input_json_path}'", file=sys.stderr)
        sys.exit(1)
        
    # Ensure output directory exists
    output_dir = os.path.dirname(output_json_path) or '.'
    if output_dir != '.':
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            print(f"Error: Could not create output directory '{output_dir}': {e}", file=sys.stderr)
            sys.exit(1)

    main(input_json_path, output_json_path)
