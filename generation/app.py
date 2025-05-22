import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

from generation.generators.vertexai import VertexAIRAG


# Load environment variables from .env file
config = load_dotenv()


# Get RAG model
generator = VertexAIRAG(
    project=os.environ.get("PROJECT_ID"),
    location=os.environ.get("LOCATION"),
)

# Initializing FastAPI
app = FastAPI()

# Add CORS if environment variable is set
if os.environ.get("CORS"):
    origins = [
        os.environ.get("PUBLIC_INTERFACE_URL"),
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
            f"{os.environ.get('PUBLIC_PB_URL')}/api/collections/users/auth-refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 200:
            return response.json()
    return None


def gen_config(
    config_response: dict[str, str | int | float],
) -> dict[str, str | int | float]:
    return {
        "model_name": config_response["model_name"],
        "system_prompt": config_response["system_prompt"].replace("\r", ""),
        "temperature": config_response["temperature"],
        "top_p": config_response["top_p"] if config_response["top_p"] >= 0 else None,
        "top_k": config_response["top_k"] if config_response["top_k"] >= 0 else None,
        "max_output_tokens": config_response["max_output_tokens"],
        "datastore": (
            config_response["datastore"] if config_response["datastore"] else None
        ),
        "rag_corpus": (
            config_response["rag_corpus"] if config_response["rag_corpus"] else None
        ),
        "rag_similarity_top_k": (
            config_response["rag_similarity_top_k"]
            if config_response["top_p"] >= 0
            else None
        ),
        "rag_vector_distance_threshold": (
            config_response["rag_vector_distance_threshold"]
            if config_response["top_p"] >= 0
            else None
        ),
    }


@app.post("/generation/generate")
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
            f"{os.environ.get('PUBLIC_PB_URL')}/api/collections/messages/records",
            json={
                "conversation": data.conversationId,
                "text": data.message,
                "role": "user",
                "rating": 0,
            },
            headers={
                "Authorization": f"Bearer {auth_store['token']}",
            },
        )

        # Get the chat configuration
        response = await client.get(
            f"{os.environ.get('PUBLIC_PB_URL')}/api/collections/conversations/records/{data.conversationId}",
            params={
                "sort": "created",
                "expand": "configuration",
            },
            headers={
                "Authorization": f"Bearer {auth_store['token']}",
            },
        )
        configuration = gen_config(response.json()["expand"]["configuration"])

        # Get the chat history
        response = await client.get(
            f"{os.environ.get('PUBLIC_PB_URL')}/api/collections/messages/records",
            params={"sort": "created"},  # Changed from json to params
            headers={
                "Authorization": f"Bearer {auth_store['token']}",
            },
        )
        messages = response.json()["items"]

    # Generate AI response
    response_text = await generator.generate_content_async(messages, **configuration)

    async with httpx.AsyncClient() as client:
        # Save AI's response to PocketBase
        await client.post(
            f"{os.environ.get('PUBLIC_PB_URL')}/api/collections/messages/records",
            json={
                "conversation": data.conversationId,
                "text": response_text,
                "role": "model",
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
