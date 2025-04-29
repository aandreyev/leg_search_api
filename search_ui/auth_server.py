from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
import uvicorn
import requests
import urllib.parse
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Get credentials and settings
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")
REDIRECT_URI = os.getenv("REDIRECT_URI")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = "openid profile email offline_access User.Read"

app = FastAPI()

@app.get("/login")
async def login():
    url = (f"{AUTHORITY}/oauth2/v2.0/authorize"
           f"?client_id={CLIENT_ID}"
           f"&response_type=code"
           f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
           f"&response_mode=query"
           f"&scope={urllib.parse.quote(SCOPE)}"
           f"&state=12345")
    return RedirectResponse(url)

@app.get("/callback")
async def callback(request: Request):
    code = request.query_params.get('code')

    if code is None:
        return {"error": "No authorization code received"}

    token_url = f"{AUTHORITY}/oauth2/v2.0/token"
    data = {
        'client_id': CLIENT_ID,
        'scope': SCOPE,
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
        'client_secret': CLIENT_SECRET
    }

    token_resp = requests.post(token_url, data=data)
    tokens = token_resp.json()

    if 'access_token' not in tokens:
        return {"error": "Failed to get access token", "details": tokens}

    # Fetch user info
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    user_resp = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
    user = user_resp.json()

    # Redirect to Streamlit app with name and email
    return RedirectResponse(f"http://localhost:8501/?name={urllib.parse.quote(user['displayName'])}&email={urllib.parse.quote(user.get('mail', user['userPrincipalName']))}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)