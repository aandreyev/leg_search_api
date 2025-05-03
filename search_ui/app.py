import streamlit as st
import time
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer
import sys

# --- Configuration Loading (Adapted for Streamlit) ---
load_dotenv()

def load_app_config():
    """Loads configuration needed for the Streamlit app (Auth + Search)."""
    config = {
        "client_id": os.getenv("CLIENT_ID"),
        "client_secret": os.getenv("CLIENT_SECRET"),
        "tenant_id": os.getenv("TENANT_ID"),
        "redirect_uri": os.getenv("REDIRECT_URI"),
        "supabase_url": os.getenv("SUPABASE_URL"),
        "supabase_key": os.getenv("SUPABASE_KEY"),
        "search_function": "match_sections",
        "embedding_model_name": os.getenv("EMBEDDING_MODEL", 'BAAI/bge-large-en-v1.5'),
        "search_limit": int(os.getenv("SEARCH_LIMIT", 5)),
        "allowed_domain": os.getenv("ALLOWED_DOMAIN", "adlvlaw.com.au")
    }
    if not all([config["supabase_url"], config["supabase_key"]]):
        st.error("FATAL ERROR: Supabase URL/Key not configured in search_ui/.env file.")
        st.stop()
    if not all([config["client_id"], config["tenant_id"], config["redirect_uri"]]):
         st.warning("Auth variables (CLIENT_ID, TENANT_ID, REDIRECT_URI) seem missing in search_ui/.env. Login might fail.")
    # print("Streamlit App Configuration loaded.") # Quieten console
    return config

# --- Initialize Embedding Model (Cached) ---
@st.cache_resource # Cache the model loading
def get_embedding_model(model_name):
    """Loads and returns the SentenceTransformer model."""
    # st.info(f"Loading embedding model: {model_name}...") # Quieten UI - happens only once
    try:
        model = SentenceTransformer(model_name)
        # dimension = model.get_sentence_embedding_dimension() # Not strictly needed here
        # st.success(f"Model '{model_name}' loaded (Dimension: {dimension}).") # Quieten UI
        # print(f"Model '{model_name}' loaded.") # Quieten console
        return model
    except Exception as e:
        st.error(f"Error loading SentenceTransformer model '{model_name}': {e}")
        print(f"Error loading SentenceTransformer model '{model_name}': {e}") # Keep error print for server logs
        st.stop()

# --- Initialize Supabase Client (Cached) ---
@st.cache_resource # Cache the Supabase client
def init_supabase_client(url, key):
    """Initializes and returns the Supabase client."""
    try:
        client = create_client(url, key)
        # print("Supabase client initialized.") # Quieten console
        return client
    except Exception as e:
        st.error(f"Error initializing Supabase client: {e}")
        print(f"Error initializing Supabase client: {e}") # Keep error print for server logs
        st.stop()

# --- Embedding Generation ---
# No caching here as query changes
def get_query_embedding(query: str, model: SentenceTransformer) -> list[float] | None:
    """Gets the embedding for the user query."""
    try:
        embedding = model.encode(query)
        embedding_list = embedding.tolist()
        # print(f"Generated query embedding (dimension: {len(embedding_list)}).") # Quieten console
        return embedding_list
    except Exception as e:
         st.error(f"An unexpected error occurred while getting query embedding: {e}")
         print(f"An unexpected error occurred while getting query embedding: {e}") # Keep error print for server logs
         return None

# --- Supabase Search ---
# No caching here as query embedding changes
def search_similar_sections(supabase: Client, search_function: str, query_embedding: list[float], limit: int):
    """Performs vector similarity search using the specified RPC function."""
    try:
        match_response = supabase.rpc(
            search_function,
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.5, # Minimum similarity threshold
                'match_count': limit
            }
        ).execute()

        if hasattr(match_response, 'data') and match_response.data:
            # print(f"Found {len(match_response.data)} potentially relevant sections.") # Quieten console
            return match_response.data
        else:
            if hasattr(match_response, 'error') and match_response.error:
                 st.warning(f"Supabase RPC error: {match_response.error}")
                 print(f"Supabase RPC error: {match_response.error}") # Keep error print for server logs
            return []
    except Exception as e:
        st.error(f"Error during similarity search RPC call: {e}")
        print(f"Error during similarity search RPC call: {e}") # Keep error print for server logs
        return []

# === Main App Logic ===

# 1. Load Configuration
config = load_app_config()

# 2. Initialize Model and Client (will be cached after first run)
model = get_embedding_model(config["embedding_model_name"])
supabase_client = init_supabase_client(config["supabase_url"], config["supabase_key"])

# 3. Authentication Check (Existing Logic)
if 'user' not in st.session_state:
    st.session_state['user'] = None

params = st.query_params
name_param = params.get('name')
email_param = params.get('email')

if name_param and email_param and not st.session_state['user']:
    st.session_state['user'] = {"name": name_param, "email": email_param}
    st.query_params.clear()

if st.session_state['user'] is None:
    st.title("Login Required")
    login_url = "http://localhost:8000/login"
    if st.button("🔐 Login with Microsoft"):
        with st.spinner('Redirecting to Microsoft login...'):
            time.sleep(0.5)
            st.markdown(f'<meta http-equiv="refresh" content="0; url={login_url}">', unsafe_allow_html=True)
            st.stop()
    st.stop()

# 4. Sidebar (Existing Logic)
with st.sidebar:
    # Keep login success message in UI
    st.success(f"✅ Logged in as:\n\n**{st.session_state['user']['name']}**")
    st.write(st.session_state['user']['email'])
    if st.button("🚪 Log Out"):
        st.session_state['user'] = None
        st.query_params.clear()
        # Keep logout message in UI
        st.success("Logged out successfully.")
        time.sleep(1)
        st.rerun()

# 5. Domain Restriction Check (Adapted)
user_email = st.session_state['user']['email']
allowed_domain = config["allowed_domain"]
if not user_email.endswith(f"@{allowed_domain}"):
    st.error(f"🚫 Access denied. You must use a @{allowed_domain} email address.")
    st.stop()

# --- Main App Content Area ---
st.title("📚 Legislative Document Search")
st.markdown(f"Powered by `{config['embedding_model_name']}`")

# CSS Injection (Keep as is)
table_override_css = """
<style>
    div[data-testid="stMarkdownContainer"] table {
        width: 100% !important; table-layout: auto !important; border-collapse: collapse;
    }
    div[data-testid="stMarkdownContainer"] table th,
    div[data-testid="stMarkdownContainer"] table td {
        width: auto !important; border: 1px solid #ccc; padding: 6px; text-align: left; vertical-align: top;
    }
</style>
"""
st.markdown(table_override_css, unsafe_allow_html=True)

# Search Input
search_query = st.text_input("Enter your search query:", placeholder="e.g., definition of resident for tax purposes")

# Search Button and Results Area
if st.button("🔍 Search", type="primary"):
    if search_query:
        # Keep spinners as they provide user feedback
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
                # Display results using correct logic
                for i, section in enumerate(similar_sections):
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
                        # --- Display HTML Content ---
                        st.markdown(html_content, unsafe_allow_html=True)
                        # --- End HTML Display ---
            else:
                # Keep this message for user feedback
                st.info("No relevant sections found matching your query and threshold.")
        else:
             # Keep error message for user feedback
            st.error("Failed to generate embedding for the query.")
    else:
         # Keep warning message for user feedback
        st.warning("Please enter a search query.")

# Footer
st.markdown("---")
st.caption("Internal Search Tool")
