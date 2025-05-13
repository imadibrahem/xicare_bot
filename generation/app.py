from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel
import uvicorn
from dotenv import dotenv_values

from generators.vertexai_rag import VertexAIRAG


# Load environment variables from .env file
config = dotenv_values(".env")

# Load system prompt
with open("generation/system_prompt.txt") as file:
    system_prompt = file.read()


# Get RAG model
norbert = VertexAIRAG(
    system_prompt=system_prompt,
    project=config["PROJECT_ID"],
    rag_corpus=config["RAG_CORPUS"],
    location=config["LOCATION"],
    temp=1.0,
    top_p=1.0,
    max_output_tokens=8192,
)

# Initializing FastAPI with CORS
app = FastAPI()

origins = [
    config["INTERFACE_URL"],
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Model for incoming POST data
class GenerateRequest(BaseModel):
    conversationId: str
    message: str


def extract_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :]
    return None


async def verify_token(token: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{config['PB_URL']}/api/collections/users/auth-refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 200:
            return response.json()
    return None


@app.post("/generate")
async def generate(data: GenerateRequest, request: Request):
    # Extract token from request header
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    # refresh auth with token (generates new token)
    auth_store = await verify_token(token)
    if not auth_store:
        raise HTTPException(status_code=401, detail="Invalid token")

    async with httpx.AsyncClient() as client:
        # Save user's message to PocketBase
        await client.post(
            f"{config['PB_URL']}/api/collections/messages/records",
            json={
                "conversation": data.conversationId,
                "text": data.message,
                "role": "user",
            },
            headers={
                "Authorization": f"Bearer {auth_store['token']}",
            },
        )

        # Get the conversation history
        response = await client.get(
            f"{config['PB_URL']}/api/collections/messages/records",
            params={"sort": "-created"},  # Changed from json to params
            headers={
                "Authorization": f"Bearer {auth_store['token']}",
            },
        )
        response_data = response.json()

    # Generate AI response
    response_text = await norbert.generate_content_async(response_data["items"])

    async with httpx.AsyncClient() as client:
        # Save AI's response to PocketBase
        await client.post(
            f"{config['PB_URL']}/api/collections/messages/records",
            json={
                "conversation": data.conversationId,
                "text": response_text,
                "role": "norbert",
            },
            headers={"Authorization": f"Bearer {auth_store['token']}"},
        )

    # Return generated message with new token
    return JSONResponse(
        headers={
            "Authorization": f"Bearer {auth_store['token']}",
            "Access-Control-Expose-Headers": "Authorization",
        },
        content={"status": "ok"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
