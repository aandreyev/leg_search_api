import os
from dotenv import load_dotenv
from supabase import create_client, Client
import json # For pretty printing results
import sys
from sentence_transformers import SentenceTransformer # Import for local embeddings

# --- Configuration Loading ---
def load_config():
    """Loads configuration from .env file."""
    load_dotenv()
    config = {
        "supabase_url": os.getenv("SUPABASE_URL"),
        "supabase_key": os.getenv("SUPABASE_KEY"), # Use Anon or Service key
        "sections_table": "sections", # Hardcode our table name
        "search_function": "match_sections", # The SQL function we created
        "embedding_model": os.getenv("EMBEDDING_MODEL", 'BAAI/bge-large-en-v1.5'),
        "search_limit": int(os.getenv("SEARCH_LIMIT", 5)), # Default to top 5
        # pgvector_dimension is derived from the model later
    }
    if not all([config["supabase_url"], config["supabase_key"]]):
        print("Error: Supabase URL/Key not configured in .env file.")
        sys.exit(1)
    print("Configuration loaded.")
    return config

# --- Initialize Embedding Model ---
# Load model globally to avoid reloading in the loop
def initialize_embedding_model(model_name):
    print(f"Loading embedding model: {model_name}...")
    try:
        model = SentenceTransformer(model_name)
        dimension = model.get_sentence_embedding_dimension()
        print(f"Model loaded successfully. Embedding dimension: {dimension}")
        return model, dimension
    except Exception as e:
        print(f"Error loading SentenceTransformer model '{model_name}': {e}")
        sys.exit(1)


# --- Embedding Generation ---
def get_query_embedding(query: str, model: SentenceTransformer) -> list[float] | None:
    """Gets the embedding for the user query using the local SentenceTransformer model."""
    try:
        print(f"Generating embedding for query...")
        embedding = model.encode(query)
        # Ensure it's a list of floats for Supabase
        embedding_list = embedding.tolist()
        print(f"Generated query embedding (dimension: {len(embedding_list)}).")
        return embedding_list
    except Exception as e:
         print(f"An unexpected error occurred while getting query embedding: {e}")
         return None

# --- Supabase Search ---
def search_similar_sections(supabase: Client, search_function: str, query_embedding: list[float], limit: int):
    """Performs vector similarity search using the specified RPC function."""
    try:
        print(f"Searching for similar sections using RPC function '{search_function}'...")
        # Call the PostgreSQL function `match_sections` via RPC
        match_response = supabase.rpc(
            search_function,
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.5, # Minimum similarity threshold (adjust lower if needed)
                'match_count': limit
            }
        ).execute()

        if hasattr(match_response, 'data') and match_response.data:
            print(f"Found {len(match_response.data)} potentially relevant sections.")
            return match_response.data
        else:
            print("No similar sections found matching the threshold.")
            # Log potential Supabase errors if available
            if hasattr(match_response, 'error') and match_response.error:
                 print(f"Supabase RPC error: {match_response.error}")
            # Check for other potential issues in the response object if needed
            # print(f"DEBUG: Full Supabase response: {match_response}")
            return []

    except Exception as e:
        print(f"Error during similarity search RPC call: {e}")
        # import traceback
        # traceback.print_exc() # Uncomment for detailed traceback
        return []


# --- Main Execution ---
def main():
    config = load_config()

    # Initialize Embedding Model
    model, pgvector_dimension = initialize_embedding_model(config["embedding_model"])

    # Initialize Supabase Client
    try:
        supabase: Client = create_client(config["supabase_url"], config["supabase_key"])
        print("Supabase client initialized.")
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        sys.exit(1)

    print(f"\n--- Ready to Search ---")
    print(f"Model: {config['embedding_model']} ({pgvector_dimension} dims)")
    print(f"Table: {config['sections_table']}")
    print(f"Function: {config['search_function']}")
    print(f"Limit: {config['search_limit']}")
    print("------------------------")
    print("\nEnter your search query (or type 'quit' to exit).")

    while True:
        query = input("Query: ")
        if query.lower() == 'quit':
            break
        if not query.strip():
            continue

        # 1. Get Query Embedding (using local model)
        query_embedding = get_query_embedding(query, model)
        if not query_embedding:
            print("Could not get embedding for query. Please try again.")
            continue

        # 2. Search for Similar Sections (using RPC)
        similar_sections = search_similar_sections(
            supabase,
            config["search_function"],
            query_embedding,
            config["search_limit"]
        )
        if not similar_sections:
            # Message already printed in search function if empty
            continue

        # 3. Display Results (simplified)
        print("\n--- Search Results ---")
        # Results are already sorted by similarity from the SQL function
        for i, section in enumerate(similar_sections):
            # Display relevant info directly from the returned section data
            section_key = section.get('section_key', 'N/A')
            structure_type = section.get('structure_type', '')
            full_id = section.get('full_id', '')
            similarity = section.get('similarity', 0.0)
            text_content = section.get('text_content', '[Content not available]')

            print(f"\n{i+1}. {structure_type} {full_id} (Key: {section_key})")
            print(f"   Similarity Score: {similarity:.4f}")
            print(f"   Content Preview: {text_content[:300]}...") # Show preview

        print("---------------------\n")

    print("Exiting search.")


if __name__ == "__main__":
    # Ensure the PostgreSQL function `match_sections` is created in Supabase first!
    # See the SQL comment block provided separately.
    # Ensure SentenceTransformer is installed: pip install sentence-transformers
    main()

"""
-- =================================================================== --
-- REQUIRED PostgreSQL Function for Similarity Search                --
-- =================================================================== --
-- Run this SQL in your Supabase SQL Editor ONCE before using search.py
--
-- This function takes a query embedding, match threshold, and count,
-- performs a cosine similarity search on the document_chunks table,
-- and returns the relevant chunk details along with the similarity score.
--
-- Notes:
--   - Assumes your chunks table is named 'document_chunks' and has columns
--     'id', 'document_id', 'chunk_index', 'embedding', 'chunk_text'. Adjust if needed.
--   - Assumes your embedding column uses cosine distance ('vector_cosine_ops').
--   - Calculates similarity as `1 - cosine_distance`.

-- Drop function if it already exists with potentially different args
DROP FUNCTION IF EXISTS match_document_chunks(vector, double precision, integer);

CREATE OR REPLACE FUNCTION match_document_chunks (
  query_embedding vector,         -- The vector embedding of the search query
  match_threshold double precision, -- Minimum similarity score (e.g., 0.7)
  match_count integer             -- Max number of results to return
)
RETURNS TABLE (                 -- Specify columns returned by the function
  id uuid,
  document_id bigint,         -- Match the type of documents.id (BIGINT in our case)
  chunk_index integer,
  content text,
  similarity double precision
)
LANGUAGE sql STABLE -- Indicates the function doesn't modify the database
AS $$
  SELECT
    dc.id,
    dc.document_id,
    dc.chunk_index,
    dc.chunk_text, -- Return the chunk text (adjust column name if different)
    1 - (dc.embedding <=> query_embedding) as similarity -- Calculate cosine similarity
  FROM
    document_chunks dc
  WHERE 1 - (dc.embedding <=> query_embedding) > match_threshold -- Filter by threshold
  ORDER BY
    similarity DESC -- Order by similarity score descending
    -- dc.embedding <=> query_embedding ASC -- Alternative: order by distance ascending
  LIMIT
    match_count;
$$;

""" 