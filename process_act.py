# process_act.py
import argparse
import json
import os
import sys
import subprocess
import datetime # Keep for potential future use, though timestamp now in upload script
from dotenv import load_dotenv # Needed for deletion step
from supabase import create_client, Client # Needed for deletion step

def read_config(config_path):
    """Reads the configuration file (JSON format).

    Expects config structure:
    {
      "keep_intermediates": boolean (optional, defaults to True),
      "docx_files": [
        {
          "path": "path/to/file.docx",
          "act_name": "Name of the Act",
          "compilation_date": "YYYY-MM-DD"
        },
        ...
      ]
    }

    Returns:
        tuple: (list of docx file info dicts, boolean keep_intermediates setting)
    """
    keep_intermediates_default = True
    config_data = []
    keep_intermediates = keep_intermediates_default

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Get keep_intermediates setting
        keep_intermediates = config.get("keep_intermediates", keep_intermediates_default)
        if not isinstance(keep_intermediates, bool):
            print(f"Warning: 'keep_intermediates' setting in '{config_path}' is not a boolean. Defaulting to {keep_intermediates_default}.", file=sys.stderr)
            keep_intermediates = keep_intermediates_default

        # Validate and process docx_files list
        if "docx_files" not in config or not isinstance(config["docx_files"], list):
            print(f"Error: Config file '{config_path}' must contain a 'docx_files' list.", file=sys.stderr)
            return None, keep_intermediates # Return None for data to indicate error

        config_dir = os.path.dirname(os.path.abspath(config_path))
        for item in config["docx_files"]:
            if not isinstance(item, dict):
                print(f"Error: Entry in 'docx_files' is not a dictionary: {item}", file=sys.stderr)
                return None, keep_intermediates
            
            required_keys = ["path", "act_name", "compilation_date"]
            if not all(key in item for key in required_keys):
                print(f"Error: Entry in 'docx_files' is missing required keys ({required_keys}): {item}", file=sys.stderr)
                return None, keep_intermediates

            # Basic validation (can be expanded)
            if not isinstance(item["path"], str) or not item["path"].lower().endswith(".docx"):
                print(f"Error: Invalid 'path' in docx_files entry: {item['path']}", file=sys.stderr)
                return None, keep_intermediates
            if not isinstance(item["act_name"], str) or not item["act_name"].strip():
                 print(f"Error: Invalid 'act_name' in docx_files entry: {item['act_name']}", file=sys.stderr)
                 return None, keep_intermediates
            # Basic date format check (YYYY-MM-DD)
            try:
                 datetime.datetime.strptime(item["compilation_date"], '%Y-%m-%d')
            except ValueError:
                 print(f"Error: Invalid 'compilation_date' format (use YYYY-MM-DD): {item['compilation_date']}", file=sys.stderr)
                 return None, keep_intermediates

            # Resolve path relative to config file
            resolved_path = os.path.abspath(os.path.join(config_dir, item['path']))
            config_data.append({
                "path": resolved_path,
                "act_name": item["act_name"].strip(),
                "compilation_date": item["compilation_date"]
            })

        return config_data, keep_intermediates

    except FileNotFoundError:
        print(f"Error: Config file not found at '{config_path}'", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from config file '{config_path}'", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading config file '{config_path}': {e}", file=sys.stderr)
        sys.exit(1)

def delete_act_data_from_supabase(act_names_to_delete):
    """Connects to Supabase and deletes existing data for the specified Act names."""
    print("\n--- Attempting to delete existing Supabase data --- ")
    if not act_names_to_delete:
        print("No act names specified for deletion. Skipping.")
        return True

    load_dotenv() # Load .env file for credentials
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY must be set in environment variables or .env file for deletion step.", file=sys.stderr)
        return False

    try:
        print(f"Initializing Supabase client for deletion...")
        supabase: Client = create_client(supabase_url, supabase_key)
        print("Supabase client initialized.")
        
        table_name = 'sections' # Hardcoded table name, consistent with upload script
        all_success = True

        for act_name in act_names_to_delete:
            print(f"Deleting data for Act: '{act_name}' from table '{table_name}'...")
            try:
                # Execute the delete operation
                response = supabase.table(table_name).delete().eq('act_name', act_name).execute()
                # Basic check: Supabase API v1+ might not have a detailed count in the response
                # We assume success if no exception is raised. Check docs if specific counts are needed.
                print(f"  Deletion command executed for '{act_name}'.")
                # Optional: Add more robust response checking if API provides it
                # if hasattr(response, 'error') and response.error:
                #    print(f"  Error deleting data for '{act_name}': {response.error}", file=sys.stderr)
                #    all_success = False
            except Exception as delete_error:
                print(f"  Error during Supabase delete operation for '{act_name}': {delete_error}", file=sys.stderr)
                all_success = False
        
        print("--- Finished Supabase deletion step ---")
        return all_success

    except Exception as e:
        print(f"Error connecting to or interacting with Supabase during deletion: {e}", file=sys.stderr)
        print("--- Finished Supabase deletion step (with error) ---")
        return False

def process_single_file(docx_path, act_name, compilation_date, save_intermediates=True):
    """Processes a single DOCX file through the pipeline."""
    print(f"\nStarting processing for: {docx_path}")
    print(f"  Act Name: {act_name}")
    print(f"  Compilation Date: {compilation_date}")
    base_path_no_ext, _ = os.path.splitext(docx_path)
    output_dir = os.path.dirname(docx_path) or '.'
    file_basename = os.path.basename(base_path_no_ext)

    # --- Step 1: DOCX to HTML ---
    print(f"  Step 1: Convert DOCX to HTML")
    # Output path for the HTML generated by mammoth
    mammoth_html_path = os.path.join(output_dir, f"{file_basename}.mammoth.html")

    try:
        # Assuming docx_to_html.py is executable and takes input/output paths
        # Example: python docx_to_html.py <input_docx> <output_html>
        script_path = os.path.join(os.path.dirname(__file__), "docx_to_html.py") # Assume script is in the same dir
        if not os.path.exists(script_path):
             # Try finding it in the current working directory if not besides process_act.py
             script_path = "docx_to_html.py"
             if not os.path.exists(script_path):
                 print(f"  Error: Cannot find the 'docx_to_html.py' script.", file=sys.stderr)
                 return False # Indicate failure for this file

        cmd = [sys.executable, script_path, docx_path, mammoth_html_path]
        print(f"    Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"    Successfully generated HTML: {mammoth_html_path}")
        # print(f"    STDOUT:\n{result.stdout}") # Uncomment for debugging stdout
        # print(f"    STDERR:\n{result.stderr}") # Uncomment for debugging stderr

        # User mentioned intermediate xxx.mammoth_html.json.
        # Let's read the generated HTML and save it as JSON for the next step.
        intermediate_json_path = os.path.join(output_dir, f"{file_basename}_mammoth_html.json")
        try:
            with open(mammoth_html_path, 'r', encoding='utf-8') as f_html:
                html_content = f_html.read()
            with open(intermediate_json_path, 'w', encoding='utf-8') as f_json:
                json.dump({"html_content": html_content}, f_json, indent=2)
            print(f"    Saved intermediate HTML content to: {intermediate_json_path}")

            # Clean up the raw .html file if intermediates are not kept,
            # but keep the json version as it might be the input for the next step.
            if not save_intermediates:
                 os.remove(mammoth_html_path)
                 print(f"    Removed intermediate file: {mammoth_html_path}")

        except Exception as e:
            print(f"  Error processing/saving intermediate HTML for {docx_path}: {e}", file=sys.stderr)
            # Decide if this is fatal for this file's processing
            # Clean up intermediate file potentially?
            if os.path.exists(mammoth_html_path):
                 try: os.remove(mammoth_html_path)
                 except OSError: pass
            if os.path.exists(intermediate_json_path):
                 try: os.remove(intermediate_json_path)
                 except OSError: pass
            return False # Indicate failure

    except FileNotFoundError:
         # This catches if sys.executable (python interpreter) isn't found.
         print(f"  Error: Python interpreter '{sys.executable}' not found?", file=sys.stderr)
         return False
    except subprocess.CalledProcessError as e:
        print(f"  Error running docx_to_html.py for {docx_path}:", file=sys.stderr)
        print(f"    Return Code: {e.returncode}", file=sys.stderr)
        # Attempt to decode stderr/stdout if they are bytes
        stderr_str = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else e.stderr
        stdout_str = e.stdout.decode('utf-8', errors='replace') if isinstance(e.stdout, bytes) else e.stdout
        print(f"    Stderr: {stderr_str}", file=sys.stderr)
        print(f"    Stdout: {stdout_str}", file=sys.stderr) # Include stdout for context
        return False # Indicate failure
    except Exception as e:
        print(f"  An unexpected error occurred during Step 1 for {docx_path}: {e}", file=sys.stderr)
        return False # Indicate failure

    # --- Placeholder for subsequent steps ---
    current_step_input = intermediate_json_path 

    # Step 2: HTML Parser
    print(f"  Step 2: Parse HTML (using {os.path.basename(current_step_input)})")
    parsed_json_path = os.path.join(output_dir, f"{file_basename}.parsed.json")

    try:
        script_path = os.path.join(os.path.dirname(__file__), "html_parser.py")
        if not os.path.exists(script_path):
             script_path = "html_parser.py" # Try current dir
             if not os.path.exists(script_path):
                 print(f"  Error: Cannot find the 'html_parser.py' script.", file=sys.stderr)
                 # Cleanup previous intermediate if needed
                 if not save_intermediates and os.path.exists(current_step_input):
                     try: os.remove(current_step_input)
                     except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
                 return False # Indicate failure

        cmd = [sys.executable, script_path, current_step_input, parsed_json_path]
        print(f"    Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"    Successfully generated parsed JSON: {parsed_json_path}")
        # print(f"    STDOUT:\n{result.stdout}") # Uncomment for debugging stdout
        # print(f"    STDERR:\n{result.stderr}") # Uncomment for debugging stderr

        # Cleanup previous intermediate file if requested
        if not save_intermediates and os.path.exists(current_step_input):
             try:
                 os.remove(current_step_input)
                 print(f"    Removed intermediate file: {current_step_input}")
             except OSError as e:
                 print(f"  Warning: Could not remove intermediate file {current_step_input}: {e}", file=sys.stderr)

        current_step_output = parsed_json_path # Update for the next step

    except FileNotFoundError:
         print(f"  Error: Python interpreter '{sys.executable}' not found?", file=sys.stderr)
         # Cleanup potentially created files if step fails midway? Difficult.
         return False
    except subprocess.CalledProcessError as e:
        print(f"  Error running html_parser.py for {os.path.basename(docx_path)}:", file=sys.stderr)
        print(f"    Return Code: {e.returncode}", file=sys.stderr)
        stderr_str = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else e.stderr
        stdout_str = e.stdout.decode('utf-8', errors='replace') if isinstance(e.stdout, bytes) else e.stdout
        print(f"    Stderr: {stderr_str}", file=sys.stderr)
        print(f"    Stdout: {stdout_str}", file=sys.stderr)
        # Cleanup previous intermediate if needed
        if not save_intermediates and os.path.exists(current_step_input):
            try: os.remove(current_step_input)
            except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
        # Also cleanup the potentially incomplete output of this step
        if os.path.exists(parsed_json_path):
             try: os.remove(parsed_json_path)
             except OSError as rm_err: print(f"  Warning: Could not remove potentially incomplete file {parsed_json_path}: {rm_err}", file=sys.stderr)
        return False # Indicate failure
    except Exception as e:
        print(f"  An unexpected error occurred during Step 2 for {os.path.basename(docx_path)}: {e}", file=sys.stderr)
        # Cleanup previous intermediate if needed
        if not save_intermediates and os.path.exists(current_step_input):
             try: os.remove(current_step_input)
             except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
        # Also cleanup the potentially incomplete output of this step
        if os.path.exists(parsed_json_path):
             try: os.remove(parsed_json_path)
             except OSError as rm_err: print(f"  Warning: Could not remove potentially incomplete file {parsed_json_path}: {rm_err}", file=sys.stderr)
        return False # Indicate failure

    # --- Step 3: Convert EMF Images --- 
    # Input is the .parsed.json from Step 2
    current_step_input = parsed_json_path # Rename for clarity
    print(f"  Step 3: Convert EMF Images (using {os.path.basename(current_step_input)})")
    converted_json_path = os.path.join(output_dir, f"{file_basename}.converted.json")

    try:
        script_path = os.path.join(os.path.dirname(__file__), "convert_emf_images.py")
        if not os.path.exists(script_path):
             script_path = "convert_emf_images.py" # Try current dir
             if not os.path.exists(script_path):
                 print(f"  Error: Cannot find the 'convert_emf_images.py' script.", file=sys.stderr)
                 # Cleanup previous intermediate if needed
                 if not save_intermediates and os.path.exists(current_step_input):
                     try: os.remove(current_step_input)
                     except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
                 return False # Indicate failure

        cmd = [sys.executable, script_path, current_step_input, converted_json_path]
        print(f"    Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"    Successfully generated converted JSON: {converted_json_path}")
        # print(f"    STDOUT:\n{result.stdout}") # Uncomment for debugging stdout
        # print(f"    STDERR:\n{result.stderr}") # Uncomment for debugging stderr

        # Cleanup previous intermediate file if requested
        if not save_intermediates and os.path.exists(current_step_input):
             try:
                 os.remove(current_step_input)
                 print(f"    Removed intermediate file: {current_step_input}")
             except OSError as e:
                 print(f"  Warning: Could not remove intermediate file {current_step_input}: {e}", file=sys.stderr)

        current_step_output = converted_json_path # Update for the next step

    except FileNotFoundError:
         print(f"  Error: Python interpreter '{sys.executable}' not found?", file=sys.stderr)
         return False
    except subprocess.CalledProcessError as e:
        print(f"  Error running convert_emf_images.py for {os.path.basename(docx_path)}:", file=sys.stderr)
        print(f"    Return Code: {e.returncode}", file=sys.stderr)
        stderr_str = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else e.stderr
        stdout_str = e.stdout.decode('utf-8', errors='replace') if isinstance(e.stdout, bytes) else e.stdout
        print(f"    Stderr: {stderr_str}", file=sys.stderr)
        print(f"    Stdout: {stdout_str}", file=sys.stderr)
        # Cleanup previous intermediate if needed
        if not save_intermediates and os.path.exists(current_step_input):
            try: os.remove(current_step_input)
            except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
        # Also cleanup the potentially incomplete output of this step
        if os.path.exists(converted_json_path):
             try: os.remove(converted_json_path)
             except OSError as rm_err: print(f"  Warning: Could not remove potentially incomplete file {converted_json_path}: {rm_err}", file=sys.stderr)
        return False # Indicate failure
    except Exception as e:
        print(f"  An unexpected error occurred during Step 3 for {os.path.basename(docx_path)}: {e}", file=sys.stderr)
        # Cleanup previous intermediate if needed
        if not save_intermediates and os.path.exists(current_step_input):
             try: os.remove(current_step_input)
             except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
        # Also cleanup the potentially incomplete output of this step
        if os.path.exists(converted_json_path):
             try: os.remove(converted_json_path)
             except OSError as rm_err: print(f"  Warning: Could not remove potentially incomplete file {converted_json_path}: {rm_err}", file=sys.stderr)
        return False # Indicate failure

    # --- Step 3.5: Apply HTML Styling --- 
    # Input is the .converted.json from Step 3
    current_step_input = converted_json_path # Rename for clarity
    print(f"  Step 3.5: Apply HTML Styling (using {os.path.basename(current_step_input)})")
    styled_json_path = os.path.join(output_dir, f"{file_basename}.styled.json")

    try:
        script_path = os.path.join(os.path.dirname(__file__), "style_html_content.py")
        if not os.path.exists(script_path):
             script_path = "style_html_content.py" # Try current dir
             if not os.path.exists(script_path):
                 print(f"  Error: Cannot find the 'style_html_content.py' script.", file=sys.stderr)
                 # Cleanup previous intermediate if needed
                 if not save_intermediates and os.path.exists(current_step_input):
                     try: os.remove(current_step_input)
                     except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
                 return False # Indicate failure

        cmd = [sys.executable, script_path, current_step_input, styled_json_path]
        print(f"    Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"    Successfully generated styled JSON: {styled_json_path}")
        # print(f"    STDOUT:\n{result.stdout}") # Uncomment for debugging stdout
        # print(f"    STDERR:\n{result.stderr}") # Uncomment for debugging stderr

        # Cleanup previous intermediate file if requested
        if not save_intermediates and os.path.exists(current_step_input):
             try:
                 os.remove(current_step_input)
                 print(f"    Removed intermediate file: {current_step_input}")
             except OSError as e:
                 print(f"  Warning: Could not remove intermediate file {current_step_input}: {e}", file=sys.stderr)

        current_step_output = styled_json_path # Update for the next step (Embeddings)

    except FileNotFoundError:
         print(f"  Error: Python interpreter '{sys.executable}' not found?", file=sys.stderr)
         return False
    except subprocess.CalledProcessError as e:
        print(f"  Error running style_html_content.py for {os.path.basename(docx_path)}:", file=sys.stderr)
        print(f"    Return Code: {e.returncode}", file=sys.stderr)
        stderr_str = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else e.stderr
        stdout_str = e.stdout.decode('utf-8', errors='replace') if isinstance(e.stdout, bytes) else e.stdout
        print(f"    Stderr: {stderr_str}", file=sys.stderr)
        print(f"    Stdout: {stdout_str}", file=sys.stderr)
        # Cleanup previous intermediate if needed
        if not save_intermediates and os.path.exists(current_step_input):
            try: os.remove(current_step_input)
            except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
        # Also cleanup the potentially incomplete output of this step
        if os.path.exists(styled_json_path):
             try: os.remove(styled_json_path)
             except OSError as rm_err: print(f"  Warning: Could not remove potentially incomplete file {styled_json_path}: {rm_err}", file=sys.stderr)
        return False # Indicate failure
    except Exception as e:
        print(f"  An unexpected error occurred during Step 3.5 (Styling) for {os.path.basename(docx_path)}: {e}", file=sys.stderr)
        # Cleanup previous intermediate if needed
        if not save_intermediates and os.path.exists(current_step_input):
             try: os.remove(current_step_input)
             except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
        # Also cleanup the potentially incomplete output of this step
        if os.path.exists(styled_json_path):
             try: os.remove(styled_json_path)
             except OSError as rm_err: print(f"  Warning: Could not remove potentially incomplete file {styled_json_path}: {rm_err}", file=sys.stderr)
        return False # Indicate failure

    # --- Step 4: Create Embeddings --- 
    # Input is the .styled.json from Step 3.5
    current_step_input = styled_json_path # Update input source
    print(f"  Step 4: Create Embeddings (using {os.path.basename(current_step_input)})")
    # This is the FINAL output file for this document
    final_json_path = os.path.join(output_dir, f"{file_basename}.json")

    try:
        script_path = os.path.join(os.path.dirname(__file__), "create_embeddings.py")
        if not os.path.exists(script_path):
             script_path = "create_embeddings.py" # Try current dir
             if not os.path.exists(script_path):
                 print(f"  Error: Cannot find the 'create_embeddings.py' script.", file=sys.stderr)
                 # Cleanup previous intermediate if needed
                 if not save_intermediates and os.path.exists(current_step_input):
                     try: os.remove(current_step_input)
                     except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
                 return False # Indicate failure

        cmd = [sys.executable, script_path, current_step_input, final_json_path]
        print(f"    Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"    Successfully generated final JSON with embeddings: {final_json_path}")
        # print(f"    STDOUT:\n{result.stdout}") # Uncomment for debugging stdout
        # print(f"    STDERR:\n{result.stderr}") # Uncomment for debugging stderr

        # Cleanup previous intermediate file if requested
        if not save_intermediates and os.path.exists(current_step_input):
             try:
                 os.remove(current_step_input)
                 print(f"    Removed intermediate file: {current_step_input}")
             except OSError as e:
                 print(f"  Warning: Could not remove intermediate file {current_step_input}: {e}", file=sys.stderr)

        # No more steps, this was the last output
        # current_step_output = final_json_path 

    except FileNotFoundError:
         print(f"  Error: Python interpreter '{sys.executable}' not found?", file=sys.stderr)
         return False
    except subprocess.CalledProcessError as e:
        print(f"  Error running create_embeddings.py for {os.path.basename(docx_path)}:", file=sys.stderr)
        print(f"    Return Code: {e.returncode}", file=sys.stderr)
        stderr_str = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else e.stderr
        stdout_str = e.stdout.decode('utf-8', errors='replace') if isinstance(e.stdout, bytes) else e.stdout
        print(f"    Stderr: {stderr_str}", file=sys.stderr)
        print(f"    Stdout: {stdout_str}", file=sys.stderr)
        # Cleanup previous intermediate if needed
        if not save_intermediates and os.path.exists(current_step_input):
            try: os.remove(current_step_input)
            except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
        # Also cleanup the potentially incomplete output of this step
        if os.path.exists(final_json_path):
             try: os.remove(final_json_path)
             except OSError as rm_err: print(f"  Warning: Could not remove potentially incomplete file {final_json_path}: {rm_err}", file=sys.stderr)
        return False # Indicate failure
    except Exception as e:
        print(f"  An unexpected error occurred during Step 4 for {os.path.basename(docx_path)}: {e}", file=sys.stderr)
        # Cleanup previous intermediate if needed
        if not save_intermediates and os.path.exists(current_step_input):
             try: os.remove(current_step_input)
             except OSError as rm_err: print(f"  Warning: Could not remove intermediate file {current_step_input}: {rm_err}", file=sys.stderr)
        # Also cleanup the potentially incomplete output of this step
        if os.path.exists(final_json_path):
             try: os.remove(final_json_path)
             except OSError as rm_err: print(f"  Warning: Could not remove potentially incomplete file {final_json_path}: {rm_err}", file=sys.stderr)
        return False # Indicate failure

    # --- Step 5: Upload to Supabase --- 
    # Input is the final JSON file from Step 4
    current_step_input = final_json_path # Rename for clarity
    print(f"  Step 5: Upload to Supabase (using {os.path.basename(current_step_input)})")

    try:
        script_path = os.path.join(os.path.dirname(__file__), "upload_to_supabase.py")
        if not os.path.exists(script_path):
             script_path = "upload_to_supabase.py" # Try current dir
             if not os.path.exists(script_path):
                 print(f"  Error: Cannot find the 'upload_to_supabase.py' script.", file=sys.stderr)
                 # Don't automatically clean up final file on upload script missing
                 return False # Indicate failure

        # Pass json path, act name, and compilation date to the upload script
        cmd = [sys.executable, script_path, current_step_input, act_name, compilation_date]
        print(f"    Running command: {' '.join(cmd)}")
        # NOTE: We assume the upload script handles its own Supabase errors internally
        # and exits non-zero if it fails critically.
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"    Successfully ran upload script for: {current_step_input}")
        # print(f"    STDOUT:\n{result.stdout}") # Uncomment for debugging stdout
        # print(f"    STDERR:\n{result.stderr}") # Uncomment for debugging stderr

        # Optional: Cleanup final JSON file if intermediates are not kept?
        # For now, we follow the keep_intermediates flag for the final file too.
        if not save_intermediates and os.path.exists(current_step_input):
             try:
                 os.remove(current_step_input)
                 print(f"    Removed final JSON file: {current_step_input}")
             except OSError as e:
                 print(f"  Warning: Could not remove final JSON file {current_step_input}: {e}", file=sys.stderr)

    except FileNotFoundError:
         print(f"  Error: Python interpreter '{sys.executable}' not found?", file=sys.stderr)
         return False
    except subprocess.CalledProcessError as e:
        print(f"  Error running upload_to_supabase.py for {os.path.basename(docx_path)}:", file=sys.stderr)
        print(f"    Return Code: {e.returncode}", file=sys.stderr)
        stderr_str = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else e.stderr
        stdout_str = e.stdout.decode('utf-8', errors='replace') if isinstance(e.stdout, bytes) else e.stdout
        print(f"    Stderr: {stderr_str}", file=sys.stderr)
        print(f"    Stdout: {stdout_str}", file=sys.stderr)
        # Don't automatically clean up file if upload fails
        return False # Indicate failure
    except Exception as e:
        print(f"  An unexpected error occurred during Step 5 for {os.path.basename(docx_path)}: {e}", file=sys.stderr)
        # Don't automatically clean up file if upload fails
        return False # Indicate failure

    # --- Pipeline Complete --- 
    print(f"  Pipeline finished successfully for {os.path.basename(docx_path)}. Final data uploaded.")
    print("-" * 20)
    return True # Indicate success for this file

def main():
    parser = argparse.ArgumentParser(description="Process DOCX files through a defined pipeline.")
    parser.add_argument("config_file", help="Path to the configuration file (JSON).")
    args = parser.parse_args()

    config_data, keep_intermediates = read_config(args.config_file)

    if config_data is None:
        print("Exiting due to configuration errors.")
        sys.exit(1)
        
    if not config_data:
        print("No DOCX files specified in the configuration file.")
        return

    # --- Pre-Deletion Step --- 
    # Get unique act names from the config data
    unique_act_names = sorted(list(set(item['act_name'] for item in config_data)))
    if not unique_act_names:
         print("Warning: Could not extract any act names from config. Cannot perform pre-deletion.")
         # Decide if we should exit or continue without deleting?
         # For now, let's continue, but this indicates a config issue.
    else:
         print(f"Acts found in config for processing (will attempt pre-delete): {unique_act_names}")
         delete_success = delete_act_data_from_supabase(unique_act_names)
         if not delete_success:
             print("Exiting because Supabase pre-deletion step failed.", file=sys.stderr)
             sys.exit(1)
         else:
              print("Supabase pre-deletion completed successfully.")
    # --- End Pre-Deletion --- 

    print(f"\nProcessing {len(config_data)} files (Keep intermediates: {keep_intermediates})")
    successful_files = 0
    failed_files = 0
    # Loop through the list of file information dictionaries
    for file_info in config_data:
        docx_path = file_info['path']
        act_name = file_info['act_name']
        compilation_date = file_info['compilation_date']

        print(f"\nProcessing: {os.path.basename(docx_path)} (Act: '{act_name}')")
        if not os.path.exists(docx_path):
            print(f"  Warning: File not found, skipping: {docx_path}", file=sys.stderr)
            failed_files += 1
            continue
        if not docx_path.lower().endswith(".docx"):
             print(f"  Warning: File does not have .docx extension, skipping: {docx_path}", file=sys.stderr)
             failed_files += 1
             continue

        # Process the file, passing the setting from the config and act info
        success = process_single_file(docx_path, act_name, compilation_date, save_intermediates=keep_intermediates)
        if success:
            successful_files += 1
        else:
            failed_files += 1
            print(f"Failed to process: {os.path.basename(docx_path)}")

    print("\n--- Summary ---")
    print(f"Successfully processed: {successful_files}")
    print(f"Failed to process:    {failed_files}")
    print("---------------")


if __name__ == "__main__":
    main()
    