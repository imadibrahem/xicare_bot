from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
from pydantic import BaseModel
import uvicorn

import vertexai
from vertexai import rag
from vertexai.generative_models import (
    GenerativeModel,
    Tool,
    GenerationConfig,
    Part,
    SafetySetting,
    Content,
)

from dotenv import dotenv_values

# Load environment variables from .env file
config = dotenv_values(".env")

# Load system prompt
with open("server/system_prompt.txt") as file:
    system_prompt = file.read()


def create_rag_model():
    # Initialize Vertex AI with project and location from config
    vertexai.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    # Get RAG corpus
    rag_corpus = rag.get_corpus(config["RAG_CORPUS"])

    # Direct context retrieval
    rag_retrieval_config = rag.RagRetrievalConfig(
        top_k=3,  # Optional
        filter=rag.Filter(vector_distance_threshold=0.5),  # Optional
    )

    # Enhance generation
    rag_retrieval_tool = Tool.from_retrieval(
        retrieval=rag.Retrieval(
            source=rag.VertexRagStore(
                rag_resources=[
                    rag.RagResource(
                        rag_corpus=rag_corpus.name,  # Currently only 1 corpus is allowed.
                        # Optional: supply IDs from `rag.list_files()`.
                        # rag_file_ids=["rag-file-1", "rag-file-2", ...],
                    )
                ],
                rag_retrieval_config=rag_retrieval_config,
            ),
        )
    )

    generate_content_config = GenerationConfig(
        temperature=1,
        top_p=1,
        max_output_tokens=8192,
    )

    # Create a Gemini model instance
    # return client, generate_content_config
    return GenerativeModel(
        model_name="gemini-2.0-flash-001",
        tools=[rag_retrieval_tool],
        system_instruction=Part.from_text(text=system_prompt),
        generation_config=generate_content_config,
        safety_settings=[
            SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
            SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
        ],
    )


# Get RAG model
norbert = create_rag_model()

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
        f"{config["PB_URL"]}/api/collections/users/auth-refresh",
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code == 200:
        return response.json()
    return None


def create_conversation_contents(items: dict[str, str]) -> list[Part]:
    return [
        Content(
            role="user" if item["role"] == "user" else "model",
            parts=[Part.from_text(text=item["text"])],
        )
        for item in items
    ]


# Dummy AI generator
def run_ai(contents: list[Part]) -> str:
    response = norbert.generate_content(contents)
    return response.candidates[0].content.parts[0].text


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
        f"{config["PB_URL"]}/api/collections/messages/records",
        json={
            "conversation": data.conversationId,
            "text": data.message,
            "role": "user",
        },
        headers={
            "Authorization": f"Bearer {auth_store["token"]}",
        },
    )

    # Get the conversation history
    response = requests.get(
        f"{config["PB_URL"]}/api/collections/messages/records",
        json={"sort": "-created"},
        headers={
            "Authorization": f"Bearer {auth_store["token"]}",
        },
    )

    # Create conversation parts
    parts = create_conversation_contents(response.json()["items"])

    # Generate AI response
    response_text = run_ai(parts)

    # Save AI's response to PocketBase
    requests.post(
        f"{config["PB_URL"]}/api/collections/messages/records",
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
