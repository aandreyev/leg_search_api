import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv
import time
import sys # Import sys for command-line arguments
import datetime # Import datetime module

# --- Configuration ---
# SOURCE_JSON_FILE = 'sections_with_embeddings.json' # Replaced by sys.argv
SUPABASE_TABLE_NAME = 'sections' # The table name you created in Supabase
BATCH_SIZE = 100 # Number of records to insert in one go
# --- Configuration End ---

# Load environment variables (recommended for credentials)
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # Use Anon key or Service Role key

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_KEY environment variables must be set.")
    exit(1)

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

def main(source_json_filepath, act_name, compilation_date):
    print("--- Starting Supabase Upload ---") # Start marker
    # Get the current timestamp for this run
    run_timestamp_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(f"Processing Act: {act_name}")
    print(f"Compilation Date: {compilation_date}")
    print(f"Upload Timestamp (UTC): {run_timestamp_iso}")

    # Load the data with embeddings
    sections_data = load_json_data(source_json_filepath)
    if not sections_data or not isinstance(sections_data, dict):
        print("Exiting due to issues loading or validating input JSON data.")
        print("--- Finished Supabase Upload (with error) ---") # End marker
        sys.exit(1)

    # Initialize Supabase client
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Supabase client initialized successfully.")
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        print("--- Finished Supabase Upload (with error) ---") # End marker
        sys.exit(1)

    # Prepare data for batch insertion
    records_to_insert = []
    for key, data in sections_data.items():
        # **Important:** Adapt this mapping to your exact JSON structure and Supabase table columns
        record = {
            'section_key': key, # Assuming the dict key is the unique section identifier
            'structure_type': data.get('structure_type'),
            'full_id': data.get('full_id'),
            'primary_id': data.get('primary_id'),
            'secondary_id': data.get('secondary_id'),
            'guide_target_type': data.get('guide_target_type'), # Might be None if not a guide
            'html_content': data.get('html'), # Map 'html' from JSON to 'html_content' column
            'text_content': data.get('text_for_embedding'), # Map 'text_for_embedding' to 'text_content'
            'char_count': data.get('char_count'),
            'heading_text': data.get('heading_text'),
            'embedding': data.get('embedding'), # Ensure this key exists and contains the list of floats
            'last_updated': run_timestamp_iso, # Add the timestamp for this run
            'act_name': act_name, # Add the act name passed as argument
            'act_compilation_dt': compilation_date # Add the compilation date passed as argument
        }
        # Add only if embedding exists to avoid errors
        if record['embedding'] and record['section_key']: # Also check key exists
            records_to_insert.append(record)
        else:
            print(f"Warning: Skipping section '{key or 'UNKNOWN'}' because 'embedding' or 'section_key' data is missing.")

    total_records = len(records_to_insert)
    print(f"Prepared {total_records} records for insertion.")

    if not records_to_insert:
        print("No records to insert.")
        print("--- Finished Supabase Upload (no records) ---") # End marker
        sys.exit(0)

    # Insert data in batches
    print(f"Starting batch insertion (batch size: {BATCH_SIZE})...")
    start_time = time.time()
    inserted_count = 0
    for i in range(0, total_records, BATCH_SIZE):
        batch = records_to_insert[i:i + BATCH_SIZE]
        try:
            # Use upsert=False if you want duplicates to cause errors instead of updates
            # data, count = supabase.table(SUPABASE_TABLE_NAME).insert(batch, upsert=False).execute()
            # Using upsert=True might be safer if you might re-run the script
            # It requires specifying the 'on_conflict' column (your primary key or unique constraint)
            # Example: Assuming 'section_key' is a unique column in your Supabase table
            # Assign to underscore '_' to indicate the variable is intentionally unused
            _ = supabase.table(SUPABASE_TABLE_NAME).upsert(batch, on_conflict='section_key').execute()

            # Simple count check (actual response structure might vary slightly)
            # Note: Supabase Python v1+ response might differ, check library docs if needed.
            # A successful insert/upsert might not return a detailed count in older versions.
            # Check for errors in the response if available.
            # if response.get('error'):
            #    print(f"Error inserting batch starting at index {i}: {response['error']}")
            # else:
            #    inserted_count += len(batch) # Assuming success if no error
            #    print(f"Inserted batch {i // BATCH_SIZE + 1}/{(total_records + BATCH_SIZE - 1) // BATCH_SIZE}...")

            # Simplified success metric for now
            inserted_count += len(batch)
            print(f"Processed batch {i // BATCH_SIZE + 1}/{(total_records + BATCH_SIZE - 1) // BATCH_SIZE}...")


        except Exception as e:
            print(f"Error inserting batch starting at index {i}: {e}")
            # Decide if you want to stop or continue on error
            # break # Uncomment to stop on first error

    end_time = time.time()
    print(f"\nFinished insertion.")
    print(f"Attempted to insert/upsert {inserted_count} records (out of {total_records} prepared).")
    print(f"Total time: {end_time - start_time:.2f} seconds.")
    print("--- Finished Supabase Upload (successfully) ---") # End marker

if __name__ == "__main__":
    # Expect three arguments: input JSON path, act name, compilation date
    if len(sys.argv) != 4:
        print(f"Usage: python {os.path.basename(sys.argv[0])} <input_json_file> <act_name> <compilation_date_YYYY-MM-DD>")
        sys.exit(1)

    input_json_path = sys.argv[1]
    act_name_arg = sys.argv[2]
    compilation_date_arg = sys.argv[3]

    # Optional: Add validation for date format if needed here as well

    # Ensure input file exists
    if not os.path.exists(input_json_path):
        print(f"Error: Input JSON file not found at '{input_json_path}'", file=sys.stderr)
        sys.exit(1)

    # Create a .env file in the same directory with:
    # SUPABASE_URL=your_supabase_project_url
    # SUPABASE_KEY=your_supabase_anon_or_service_key
    main(input_json_path, act_name_arg, compilation_date_arg)
