from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import aiohttp  # Replace requests with aiohttp
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


async def verify_token(token: str):  # Make verify_token async
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{config['PB_URL']}/api/collections/users/auth-refresh",
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            if response.status == 200:  # Note: .status in aiohttp, not .status_code
                return await response.json()
    return None


@app.post("/generate")
async def generate(data: GenerateRequest, request: Request):
    # Extract token from request header
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    # refresh auth with token (generates new token)
    auth_store = await verify_token(token)  # Use await here
    if not auth_store:
        raise HTTPException(status_code=401, detail="Invalid token")

    async with aiohttp.ClientSession() as session:
        # Save user's message to PocketBase
        async with session.post(
            f"{config['PB_URL']}/api/collections/messages/records",
            json={
                "conversation": data.conversationId,
                "text": data.message,
                "role": "user",
            },
            headers={
                "Authorization": f"Bearer {auth_store['token']}",
            },
        ) as response:
            pass  # We don't need to process this response

        # Get the conversation history
        async with session.get(
            f"{config['PB_URL']}/api/collections/messages/records",
            params={"sort": "-created"},  # Use params instead of json for GET
            headers={
                "Authorization": f"Bearer {auth_store['token']}",
            },
        ) as response:
            conversation_data = await response.json()

        # Generate AI response
        response_text = await norbert.generate_content_async(conversation_data["items"])

        # Save AI's response to PocketBase
        async with session.post(
            f"{config['PB_URL']}/api/collections/messages/records",
            json={
                "conversation": data.conversationId,
                "text": response_text,
                "role": "norbert",
            },
            headers={"Authorization": f"Bearer {auth_store['token']}"},
        ) as response:
            pass  # We don't need to process this response

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
