import os
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field # Use Field for potential examples/validation
from dotenv import load_dotenv
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer
import uvicorn
from typing import List, Dict, Any, Optional

# --- Configuration & Globals ---
load_dotenv() # Load from root .env file

# --- Embedding Model Cache ---
# Load the model globally on startup. For more complex apps, consider lifespan events.
MODEL_NAME = os.getenv("EMBEDDING_MODEL", 'BAAI/bge-large-en-v1.5')
try:
    print(f"Loading embedding model: {MODEL_NAME}...")
    embedding_model = SentenceTransformer(MODEL_NAME)
    print("Embedding model loaded successfully.")
except Exception as e:
    print(f"FATAL: Could not load embedding model: {e}")
    embedding_model = None # Ensure it's None if loading failed

# --- Supabase Client Cache ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
try:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    print("Initializing Supabase client...")
    supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Supabase client initialized successfully.")
except Exception as e:
    print(f"FATAL: Could not initialize Supabase client: {e}")
    supabase_client = None # Ensure it's None if init failed

# --- API Configuration ---
SEARCH_FUNCTION = os.getenv("SEARCH_FUNCTION", "match_sections")
SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT", 5))
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", 0.5)) # Allow configuration

# --- FastAPI App Instance ---
app = FastAPI(
    title="Legislative Search API",
    description="API for performing semantic search on legislative document sections.",
    version="1.0.0",
)

# --- Request & Response Models ---
class SearchQuery(BaseModel):
    query: str = Field(..., example="definition of resident for tax purposes")
    limit: Optional[int] = Field(SEARCH_LIMIT, example=5, description="Max number of results")
    threshold: Optional[float] = Field(MATCH_THRESHOLD, example=0.5, description="Minimum similarity score")

# Define a model for the items in the results list for clarity
class SearchResultItem(BaseModel):
    section_key: str
    structure_type: str
    full_id: str
    text_content: str
    html_content: str
    heading_text: str
    similarity: float

class SearchResponse(BaseModel):
    results: List[SearchResultItem]

# --- Health Check Endpoint ---
@app.get("/health", tags=["Health"])
async def health_check():
    """Check if the API and its dependencies (model, db client) are operational."""
    # Basic checks - could be expanded
    if embedding_model is None:
        raise HTTPException(status_code=503, detail="Embedding model not loaded")
    if supabase_client is None:
        raise HTTPException(status_code=503, detail="Supabase client not initialized")
    # Could add a simple Supabase ping here if needed
    return {"status": "ok"}

# --- Search Endpoint ---
@app.post("/search", response_model=SearchResponse, tags=["Search"])
async def search_sections(search_query: SearchQuery):
    """
    Performs semantic search based on the provided query.
    Generates an embedding for the query and searches Supabase for similar sections.
    """
    if embedding_model is None:
        raise HTTPException(status_code=503, detail="Embedding model not available")
    if supabase_client is None:
        raise HTTPException(status_code=503, detail="Supabase client not available")

    # 1. Generate Query Embedding
    try:
        query_vector = embedding_model.encode(search_query.query).tolist()
    except Exception as e:
        print(f"Error generating embedding: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate query embedding")

    # 2. Search Supabase
    try:
        search_limit = search_query.limit if search_query.limit is not None else SEARCH_LIMIT
        match_threshold = search_query.threshold if search_query.threshold is not None else MATCH_THRESHOLD

        response = supabase_client.rpc(
            SEARCH_FUNCTION,
            {
                'query_embedding': query_vector,
                'match_threshold': match_threshold,
                'match_count': search_limit
            }
        ).execute()

        if hasattr(response, 'data') and response.data:
            # Validate data structure slightly if needed, or rely on Supabase function correctness
            # Pydantic will validate on return based on SearchResponse model
             return {"results": response.data}
        elif hasattr(response, 'error') and response.error:
            print(f"Supabase RPC error: {response.error}")
            raise HTTPException(status_code=500, detail=f"Database search error: {response.error.get('message', 'Unknown DB error')}")
        else:
             return {"results": []} # No error, but no results found

    except HTTPException as http_exc:
         raise http_exc # Re-raise HTTP exceptions
    except Exception as e:
        print(f"Error during Supabase search RPC call: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred during search")

# --- Run Instruction (for local dev) ---
if __name__ == "__main__":
    print("\n--- To run the API server: ---")
    print("uvicorn main_api:app --reload --host 0.0.0.0 --port 8080")
    print("-----------------------------\n")
    # Example run command if needed, though 'uvicorn' is standard
    # uvicorn.run("main_api:app", host="0.0.0.0", port=8080, reload=True)
