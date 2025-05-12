from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
from pydantic import BaseModel

# Initializing FastAPI with CORS
app = FastAPI()

origins = [
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PB_URL = "http://localhost:8090"


# Model for incoming POST data
class GenerateRequest(BaseModel):
    conversationId: str
    message: str


def extract_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :]
    return None


def verify_token(token: str):
    response = requests.post(
        f"{PB_URL}/api/collections/users/auth-refresh",
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code == 200:
        return response.json()
    return None


# Dummy AI generator
def run_ai(message: str) -> str:
    return f"Echo: {message}"


@app.post("/generate")
async def generate(data: GenerateRequest, request: Request):
    # Extract token from request header
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    # refresh auth with token (generates new token)
    auth_store = verify_token(token)
    if not auth_store:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Save user's message to PocketBase
    requests.post(
        f"{PB_URL}/api/collections/messages/records",
        json={
            "conversation": data.conversationId,
            "text": data.message,
            "role": "user",
        },
        headers={
            "Authorization": f"Bearer {auth_store["token"]}",
        },
    )

    # Generate AI response
    response_text = run_ai(data.message)

    # Save AI's response to PocketBase
    requests.post(
        f"{PB_URL}/api/collections/messages/records",
        json={
            "conversation": data.conversationId,
            "text": response_text,
            "role": "norbert",
        },
        headers={"Authorization": f"Bearer {auth_store["token"]}"},
    )

    # Return generated message with new token
    return JSONResponse(
        headers={
            "Authorization": f"Bearer {auth_store["token"]}",
            "Access-Control-Expose-Headers": "Authorization",
        },
        content={"status": "ok"},
    )
