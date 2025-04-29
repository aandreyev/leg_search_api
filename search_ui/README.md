# Legislative Document Search - Streamlit App (UI)

This directory (`search_ui`) contains the Streamlit front-end application for searching the legislative document embeddings. It includes Azure Active Directory authentication.

## Prerequisites

*   Python 3.9+ (due to `supabase-py` requirements)
*   Virtual environment tool (like `venv`) recommended.
*   Access to the Supabase project containing the 'sections' table with embeddings (configured via `.env`).
*   An Azure AD App Registration with appropriate permissions and redirect URI configured (configured via `.env`).

## Setup

1.  **Navigate to this directory:**
    Make sure you are inside the `search_ui` directory within your main project structure.
    ```bash
    # Example: from the root 'xml-inspection' directory
    cd search_ui
    ```

2.  **Create and Activate Virtual Environment (Recommended if separate from main):**
    If you want a dedicated environment just for the UI:
    ```bash
    # Create (only once) - run this command inside the 'search_ui' directory
    python -m venv .venv
    # Activate (run each time you work on the UI) - run this inside 'search_ui'
    # macOS / Linux:
    source .venv/bin/activate
    # Windows:
    # .venv\Scripts\activate
    ```
    *Note: You might be using the main `.venv` from the root directory, which is also fine.*

3.  **Install Dependencies:**
    Ensure your active virtual environment has the required packages. Run this inside the `search_ui` directory:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    Create a file named `.env` inside this `search_ui` directory (if it doesn't exist). Add the following variables, replacing the placeholder values with your actual credentials:

    ```dotenv
    # Azure AD App Registration Details
    CLIENT_ID="your_azure_ad_application_client_id"
    CLIENT_SECRET="your_azure_ad_client_secret"
    TENANT_ID="your_azure_ad_tenant_id"
    REDIRECT_URI="http://localhost:8000/callback" # Default for local dev

    # Supabase Project Details
    SUPABASE_URL="your_supabase_project_url"
    SUPABASE_KEY="your_supabase_anon_or_service_key"

    # Optional: Allowed Email Domain for Access Control
    # ALLOWED_DOMAIN="yourcompany.com" # Defaults to adlvlaw.com.au if not set
    ```
    *   **Important:** Ensure the `REDIRECT_URI` matches **exactly** what you configured in your Azure AD App Registration for the `http://localhost:8000/callback` redirect.

## Running the Application

The application requires two components running simultaneously: the authentication callback server and the Streamlit app itself. You need to run these commands **from within the `search_ui` directory**, ensuring the correct virtual environment is activated.

1.  **Terminal 1: Start the Authentication Server:**
    *   Activate virtual environment (if needed).
    *   Make sure you are in the `search_ui` directory.
    *   Run the FastAPI server:
        ```bash
        python auth_server.py
        ```
    *   Keep this terminal running.

2.  **Terminal 2: Start the Streamlit App:**
    *   Open a *new* terminal window or tab.
    *   Activate the virtual environment (if needed).
    *   Make sure you are in the `search_ui` directory.
    *   Run the Streamlit app:
        ```bash
        streamlit run app.py
        ```
    *   Keep this terminal running.

3.  **Access the App:**
    *   Open your web browser and navigate to the URL provided by the `streamlit run` command (usually `http://localhost:8501`).
    *   Log in via Microsoft.

## Stopping the Application

*   Press `Ctrl+C` in each terminal window.
*   Deactivate the virtual environment (optional): `deactivate`
    