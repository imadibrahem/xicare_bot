from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import requests
from pydantic import BaseModel

app = FastAPI()

PB_URL = "http://localhost:8090"


# Example model for the incoming POST body
class GenerateRequest(BaseModel):
    conversationId: str
    message: str


# Dummy implementation — replace with real token check
def extract_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :]
    return None


def verify_token(token: str):
    response = requests.get(
        f"{PB_URL}/api/users/auth-refresh", headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return None


# Dummy AI generator
def run_ai(message: str) -> str:
    return f"Echo: {message}"


@app.post("/generate")
async def generate(data: GenerateRequest, request: Request):
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

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
        headers={"Authorization": f"Bearer {auth_store["token"]}"},
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

    return JSONResponse(content={"status": "ok"})
