import zipfile
import xml.dom.minidom
import os # To check if file exists
import sys # Import sys module

def inspect_docx_xml(docx_path, files_to_inspect=None, max_lines=100):
    """
    Extracts and pretty-prints specified XML files from a DOCX archive.

    Args:
        docx_path (str): Path to the .docx file.
        files_to_inspect (list, optional): List of internal XML file paths
                                           to inspect. Defaults to common ones.
        max_lines (int, optional): Maximum number of lines to print per XML file
                                   to avoid flooding the console. Defaults to 100.
                                   Set to None to print everything.
    """
    # Default files if none specified
    if files_to_inspect is None:
        files_to_inspect = [
            'word/document.xml',  # Main content
            'word/styles.xml',    # Style definitions (important for headings)
            'word/numbering.xml'  # List definitions (important for list levels)
        ]

    # --- Basic File Check ---
    if not os.path.exists(docx_path):
        print(f"Error: File not found at '{docx_path}'")
        return
    if not docx_path.lower().endswith('.docx'):
        print(f"Warning: File '{docx_path}' does not have a .docx extension.")
        # Allow continuing, but warn the user

    print(f"--- Inspecting DOCX file: {docx_path} ---")

    try:
        # --- Open the DOCX file as a ZIP archive ---
        with zipfile.ZipFile(docx_path, 'r') as docx_zip:

            # Optional: List all files inside the DOCX for context
            # print("\nFiles within the archive:")
            # for name in docx_zip.namelist():
            #     print(f"- {name}")

            # --- Inspect specific XML files ---
            for xml_path in files_to_inspect:
                print(f"\n--- Processing: {xml_path} ---")

                if xml_path in docx_zip.namelist():
                    try:
                        # Read the XML content as bytes
                        xml_content_bytes = docx_zip.read(xml_path)

                        # Decode assuming UTF-8 (standard for DOCX XML)
                        xml_content_str = xml_content_bytes.decode('utf-8')

                        # Use minidom to parse and pretty-print the XML
                        dom = xml.dom.minidom.parseString(xml_content_str)
                        pretty_xml = dom.toprettyxml(indent="  ") # Use 2 spaces for indentation

                        # --- Write to file instead of printing ---
                        output_filename = f"{os.path.splitext(os.path.basename(docx_path))[0]}_{xml_path.replace('/', '_')}.xml"
                        output_filepath = os.path.join(os.path.dirname(docx_path), output_filename) # Save in same dir as docx
                        try:
                            with open(output_filepath, "w", encoding="utf-8") as f_out:
                                f_out.write(pretty_xml)
                            print(f"Saved XML content for {xml_path} to: {output_filepath}")
                        except Exception as write_err:
                            print(f"Error writing {xml_path} to file {output_filepath}: {write_err}")
                        # --- End of file writing block ---

                    except xml.parsers.expat.ExpatError as xml_err:
                        print(f"Error parsing XML in {xml_path}: {xml_err}")
                        print("File content might be corrupted or not standard XML.")
                    except Exception as read_err:
                        print(f"Error reading or processing {xml_path}: {read_err}")
                else:
                    print(f"'{xml_path}' not found in the archive.")
                print("-" * (len(xml_path) + 18)) # Separator

    except zipfile.BadZipFile:
        print(f"Error: '{docx_path}' is not a valid DOCX (ZIP) file or is corrupted.")
    except FileNotFoundError: # Should be caught by os.path.exists, but good practice
         print(f"Error: File not found at '{docx_path}' during zip processing.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# --- Get file path from command line and run inspection ---
if __name__ == "__main__":
    # Check if a filename argument was provided
    if len(sys.argv) < 2:
        print("Usage: python inspect_docx.py <filename.docx>")
        sys.exit(1) # Exit if no filename is given

    file_path = sys.argv[1] # Get filename from command line

    # Optional: Add a check to ensure the file exists (already done inside function, but good here too)
    if not os.path.exists(file_path):
        print(f"Error: File not found at '{file_path}'")
        sys.exit(1)

    # You can customize the files and line limit here if needed:
    # inspect_docx_xml(file_path, files_to_inspect=['word/document.xml'], max_lines=None)
    inspect_docx_xml(file_path, files_to_inspect=['word/document.xml']) # Removed max_lines as we write the whole file