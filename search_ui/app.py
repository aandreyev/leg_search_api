import streamlit as st
import time
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer
import sys
import torch # Ensure torch is imported if it wasn't already

# --- Add the workaround line ---
torch.classes.__path__ = []
# --- End workaround ---

# --- Configuration Loading (Adapted for Streamlit) ---
load_dotenv()

def load_app_config():
    """Loads configuration needed for the Streamlit app (Auth + Search)."""
    config = {
        # Auth vars (implicitly used by auth_server.py, but good to check)
        "client_id": os.getenv("CLIENT_ID"),
        "client_secret": os.getenv("CLIENT_SECRET"),
        "tenant_id": os.getenv("TENANT_ID"),
        "redirect_uri": os.getenv("REDIRECT_URI"),
        # Search vars
        "supabase_url": os.getenv("SUPABASE_URL"),
        "supabase_key": os.getenv("SUPABASE_KEY"), # Use Anon or Service key
        "search_function": "match_sections", # The SQL function we created
        "embedding_model_name": os.getenv("EMBEDDING_MODEL", 'BAAI/bge-large-en-v1.5'),
        "search_limit": int(os.getenv("SEARCH_LIMIT", 5)), # Default to top 5
        "allowed_domain": os.getenv("ALLOWED_DOMAIN", "adlvlaw.com.au") # Load allowed domain
    }
    # Basic validation for search config
    if not all([config["supabase_url"], config["supabase_key"]]):
        st.error("FATAL ERROR: Supabase URL/Key not configured in streamlit/.env file.")
        st.stop() # Stop Streamlit execution

    # Basic validation for auth config (less critical here as auth_server handles it)
    if not all([config["client_id"], config["tenant_id"], config["redirect_uri"]]):
         st.warning("Auth variables (CLIENT_ID, TENANT_ID, REDIRECT_URI) seem missing in streamlit/.env. Login might fail.")

    print("Streamlit App Configuration loaded.") # For server logs
    return config

# --- Initialize Embedding Model (Cached) ---
@st.cache_resource # Cache the model loading
def get_embedding_model(model_name):
    """Loads and returns the SentenceTransformer model."""
    st.info(f"Loading embedding model: {model_name}...") # Show status in UI
    try:
        model = SentenceTransformer(model_name)
        dimension = model.get_sentence_embedding_dimension()
        st.success(f"Model '{model_name}' loaded (Dimension: {dimension}).")
        print(f"Model '{model_name}' loaded (Dimension: {dimension}).") # Server log
        return model
    except Exception as e:
        st.error(f"Error loading SentenceTransformer model '{model_name}': {e}")
        print(f"Error loading SentenceTransformer model '{model_name}': {e}") # Server log
        st.stop() # Stop if model fails to load

# --- Initialize Supabase Client (Cached) ---
@st.cache_resource # Cache the Supabase client
def init_supabase_client(url, key):
    """Initializes and returns the Supabase client."""
    try:
        client = create_client(url, key)
        print("Supabase client initialized.") # Server log
        return client
    except Exception as e:
        st.error(f"Error initializing Supabase client: {e}")
        print(f"Error initializing Supabase client: {e}") # Server log
        st.stop()

# --- Moved Function Definitions ---
# @st.cache_resource ... get_embedding_model definition removed from here
# @st.cache_resource ... init_supabase_client definition removed from here

# --- Embedding Generation ---
# No caching here as query changes
def get_query_embedding(query: str, model: SentenceTransformer) -> list[float] | None:
    """Gets the embedding for the user query."""
    try:
        embedding = model.encode(query)
        embedding_list = embedding.tolist()
        print(f"Generated query embedding (dimension: {len(embedding_list)}).") # Server log
        return embedding_list
    except Exception as e:
         st.error(f"An unexpected error occurred while getting query embedding: {e}")
         print(f"An unexpected error occurred while getting query embedding: {e}") # Server log
         return None

# --- Supabase Search ---
# No caching here as query embedding changes
def search_similar_sections(supabase: Client, search_function: str, query_embedding: list[float], limit: int):
    """Performs vector similarity search using the specified RPC function."""
    try:
        # Call the PostgreSQL function `match_sections` via RPC
        match_response = supabase.rpc(
            search_function,
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.5, # Minimum similarity threshold
                'match_count': limit
            }
        ).execute()

        if hasattr(match_response, 'data') and match_response.data:
            print(f"Found {len(match_response.data)} potentially relevant sections.") # Server log
            return match_response.data
        else:
            # Log potential Supabase errors if available
            if hasattr(match_response, 'error') and match_response.error:
                 st.warning(f"Supabase RPC error: {match_response.error}")
                 print(f"Supabase RPC error: {match_response.error}") # Server log
            # Check for other potential issues in the response object if needed
            # print(f"DEBUG: Full Supabase response: {match_response}")
            return []
    except Exception as e:
        st.error(f"Error during similarity search RPC call: {e}")
        print(f"Error during similarity search RPC call: {e}") # Server log
        return []

# === Main App Logic ===

# 1. Load Configuration
config = load_app_config()

# 3. Authentication Check (Existing Logic)
if 'user' not in st.session_state:
    st.session_state['user'] = None

# Try to capture name and email from URL after redirect from auth_server
params = st.query_params
name_param = params.get('name')
email_param = params.get('email')

if name_param and email_param and not st.session_state['user']:
    st.session_state['user'] = {"name": name_param, "email": email_param}
    st.query_params.clear() # Clear params from URL after capturing

# Check login state
if st.session_state['user'] is None:
    st.title("Login Required")
    login_url = "http://localhost:8000/login" # URL for the auth_server
    if st.button("🔐 Login with Microsoft"):
        with st.spinner('Redirecting to Microsoft login...'):
            time.sleep(0.5) # Give spinner time to show
            # Use meta refresh tag for redirect
            st.markdown(f'<meta http-equiv="refresh" content="0; url={login_url}">', unsafe_allow_html=True)
            # It's important that st.stop() comes *after* the markdown
            # to ensure the markdown is sent to the browser before stopping.
            st.stop()
    st.stop() # Stop if not logged in

# 4. Sidebar (Existing Logic)
with st.sidebar:
    st.success(f"✅ Logged in as:\n\n**{st.session_state['user']['name']}**")
    st.write(st.session_state['user']['email'])
    if st.button("🚪 Log Out"):
        st.session_state['user'] = None
        # Clear query params on logout just in case
        st.query_params.clear()
        st.success("Logged out successfully.")
        time.sleep(1)
        st.rerun() # Rerun to show login page

# 5. Domain Restriction Check (Adapted)
user_email = st.session_state['user']['email']
allowed_domain = config["allowed_domain"] # Get from config
if not user_email.endswith(f"@{allowed_domain}"):
    st.error(f"🚫 Access denied. You must use a @{allowed_domain} email address.")
    st.stop()

# --- Define and Initialize AFTER Auth/Domain Checks --- 

# --- Actual Initialization Calls ---
model = get_embedding_model(config["embedding_model_name"])
supabase_client = init_supabase_client(config["supabase_url"], config["supabase_key"])

# --- Main App Content Area ---
st.title("📚 Legislative Document Search")
st.markdown(f"Powered by `{config['embedding_model_name']}`")

# --- Inject CSS to override table styles ---
# This targets tables within the markdown containers rendered by Streamlit.
# You might need to make the selector more specific if it affects other tables.
table_override_css = """
<style>
    /* Target tables rendered via st.markdown */
    div[data-testid="stMarkdownContainer"] table {
        width: 100% !important;         /* Force table to use available width */
        table-layout: auto !important;  /* Ask browser to auto-size columns */
        border-collapse: collapse;      /* Standard table look */
    }
    /* Apply to header and data cells */
    div[data-testid="stMarkdownContainer"] table th,
    div[data-testid="stMarkdownContainer"] table td {
        width: auto !important; /* Reset any fixed widths */
        /* Add some basic styling for readability */
        border: 1px solid #ccc;
        padding: 6px;
        text-align: left;
        vertical-align: top;
    }
</style>
"""
st.markdown(table_override_css, unsafe_allow_html=True)
# --- End CSS Injection ---

# Search Input
search_query = st.text_input("Enter your search query:", placeholder="e.g., definition of resident for tax purposes")

# Search Button and Results Area
if st.button("🔍 Search", type="primary"):
    if search_query:
        with st.spinner("Generating query embedding..."):
            query_embedding = get_query_embedding(search_query, model)

        if query_embedding:
            with st.spinner(f"Searching for relevant sections in Supabase..."):
                similar_sections = search_similar_sections(
                    supabase_client,
                    config["search_function"],
                    query_embedding,
                    config["search_limit"]
                )

            st.subheader("Search Results")
            if similar_sections:
                # Display results
                for i, section in enumerate(similar_sections):
                    # Retrieve data (including heading_text now)
                    section_key = section.get('section_key', 'N/A')
                    structure_type = section.get('structure_type', '')
                    full_id = section.get('full_id', '')
                    similarity = section.get('similarity', 0.0)
                    html_content = section.get('html_content', '<p>HTML content not available.</p>')
                    # --- Use heading_text directly from Supabase ---
                    heading = section.get('heading_text', '') # Get heading text
                    # Construct the label using structure_type, full_id, and heading_text
                    expander_title = f"{structure_type} {full_id} {heading}".strip()
                    expander_label = f"**{i+1}. {expander_title}** (Similarity: {similarity:.4f})"
                    # --- End Label Construction ---

                    # Use an expander for each result with the structured title
                    with st.expander(expander_label):
                        st.markdown(f"**Key:** `{section_key}` | **Type:** `{structure_type}` | **ID:** `{full_id}`")
                        st.markdown("---")
                        # Display HTML Content
                        st.markdown(html_content, unsafe_allow_html=True)

            else:
                st.info("No relevant sections found matching your query and threshold.")
        else:
            st.error("Failed to generate embedding for the query.")
    else:
        st.warning("Please enter a search query.")

# Add footer or other info if needed
st.markdown("---")
st.caption("Internal Search Tool")
