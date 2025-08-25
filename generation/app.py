import os, json, uuid, datetime
from typing import Optional, List, Dict, Any, Literal
from fastapi import FastAPI, APIRouter, Request, HTTPException, Depends, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
import uvicorn
from dotenv import load_dotenv

import redis.asyncio as redis
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

from generators.vertexai import VertexAIRAG


# Load environment variables from .env file
config = load_dotenv()


# Get RAG model
generator = VertexAIRAG(
    project=os.environ.get("PROJECT_ID"),
    location=os.environ.get("LOCATION"),
)

# Initializing FastAPI
app = FastAPI()


# Model for incoming POST data
class GenerateRequestGUI(BaseModel):
    conversationId: str
    message: str


def extract_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :]
    return None


async def verify_token(token: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{os.environ.get('GENERATION_PB_URL')}/api/collections/users/auth-refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 200:
            return response.json()
    return None


def gen_config(
    config_response: dict[str, Any],
) -> dict[str, Any]:
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
            if config_response["rag_similarity_top_k"] >= 0
            else None
        ),
        "rag_vector_distance_threshold": (
            config_response["rag_vector_distance_threshold"]
            if config_response["rag_vector_distance_threshold"] >= 0
            else None
        ),
        "block_hate_speech": config_response["block_hate_speech"],
        "block_dangerous_content": config_response["block_dangerous_content"],
        "block_sexually_explicit_content": config_response[
            "block_sexually_explicit_content"
        ],
        "block_harassment_content": config_response["block_harassment_content"],
    }

GUI = APIRouter(prefix="/generation")

# before /generation/generate but now already routed GUI to / generation
@GUI.post("/generate")
async def generate(data: GenerateRequestGUI, request: Request):
    # Extract token from request header
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    # Use token directly without refreshing
    auth_header = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        # Save user's message to PocketBase
        await client.post(
            f"{os.environ.get('GENERATION_PB_URL')}/api/collections/messages/records",
            json={
                "conversation": data.conversationId,
                "text": data.message,
                "role": "user",
                "rating": 0,
            },
            headers=auth_header,
        )

        # Get the chat configuration
        response = await client.get(
            f"{os.environ.get('GENERATION_PB_URL')}/api/collections/conversations/records/{data.conversationId}",
            params={
                "sort": "created",
                "expand": "configuration",
            },
            headers=auth_header,
        )
        configuration = gen_config(response.json()["expand"]["configuration"])

        # Get the chat history
        response = await client.get(
            f"{os.environ.get('GENERATION_PB_URL')}/api/collections/messages/records",
            params={
                "sort": "created",
                "filter": f"(conversation='{data.conversationId}')",
            },  # Changed from json to params
            headers=auth_header,
        )
        messages = response.json()["items"]

    # Generate AI response
    response_text = await generator.generate_content_async(messages, **configuration)

    async with httpx.AsyncClient() as client:
        # Save AI's response to PocketBase
        await client.post(
            f"{os.environ.get('GENERATION_PB_URL')}/api/collections/messages/records",
            json={
                "conversation": data.conversationId,
                "text": response_text,
                "role": "model",
            },
            headers=auth_header,
        )

    # Return generated message with new token
    return JSONResponse(content={"status": "ok"})

#######################################################
# -------- API router --------
API = APIRouter(prefix="/v1")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TTL_MIN = int(os.getenv("CONTEXT_TTL_MINUTES", "60"))
CONFIG_CACHE_SECONDS = int(os.getenv("CONFIG_CACHE_SECONDS", "300"))
ORIGIN_WHITELIST = {o.strip() for o in os.getenv("ORIGIN_WHITELIST", "").split(",") if o.strip()}

GENERATION_PB_URL = os.environ.get("GENERATION_PB_URL")
PB_API_USER_EMAIL = os.environ.get("PB_API_USER_EMAIL")
PB_API_USER_PASSWORD = os.environ.get("PB_API_USER_PASSWORD")
                                   
r = redis.from_url(REDIS_URL, decode_responses=True)
limiter = Limiter(key_func=get_remote_address, storage_uri=REDIS_URL)

# --- PocketBase admin token management ---
_api_superuser_token: Optional[str] = None

async def pb_api_superuser_token() -> str:
    # could also cache in the future
    # but then again needs check if token from cache is ok etc. -> no real benefit
    global _api_superuser_token
    async with httpx.AsyncClient(timeout=5.0) as client:
        if _api_superuser_token:
            resp = await client.post(
                f"{GENERATION_PB_URL}/api/collections/_superusers/auth-refresh",
                headers={"Authorization": f"Bearer {_api_superuser_token}"}
            )
            if resp.status_code == 200:
                _api_superuser_token = resp.json()["token"]
                return _api_superuser_token
        # (re)login when no token or refresh failed
        resp = await client.post(
            f"{GENERATION_PB_URL}/api/collections/_superusers/auth-with-password",
            json={"identity": PB_API_USER_EMAIL, "password": PB_API_USER_PASSWORD}
        )
        resp.raise_for_status()
        _api_superuser_token = resp.json()["token"]
        return _api_superuser_token
    
# --- config loader (always from PocketBase; short-ttl cache in Redis) ---
async def latest_configuration() -> Dict[str, Any]:
    cached = await r.get("configuration:latest")
    if cached:
        return json.loads(cached)

    token = await pb_api_superuser_token()
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{GENERATION_PB_URL}/api/collections/configurations/records",
            params={"perPage": 1, "filter": "default = true", "sort": "-updated"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

        if not items:
            # fallback to latest
            resp2 = await client.get(
                f"{GENERATION_PB_URL}/api/collections/configurations/records",
                params={"perPage": 1, "sort": "-updated"},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp2.raise_for_status()
            items = resp2.json().get("items", [])

        if not items:
            raise HTTPException(status_code=500, detail="No configuration found")

        item = items[0]
        cfg = {
            "model_name": item["model_name"],
            "system_prompt": item["system_prompt"].replace("\r", ""),
            "temperature": item.get("temperature"),
            "top_p": item.get("top_p"),
            "top_k": item.get("top_k"),
            "max_output_tokens": item.get("max_output_tokens"),
            "datastore": item.get("datastore") or None,
            "rag_corpus": item.get("rag_corpus") or None,
            "rag_similarity_top_k": item.get("rag_similarity_top_k"),
            "rag_vector_distance_threshold": item.get("rag_vector_distance_threshold"),
            "block_hate_speech": item.get("block_hate_speech", False),
            "block_dangerous_content": item.get("block_dangerous_content", False),
            "block_sexually_explicit_content": item.get("block_sexually_explicit_content", False),
            "block_harassment_content": item.get("block_harassment_content", False),
        }

    await r.set("configuration:latest", json.dumps(cfg), ex=CONFIG_CACHE_SECONDS)
    return cfg

def require_allowed_origin(request: Request):
    origin = request.headers.get("Origin")
    if not ORIGIN_WHITELIST or origin not in ORIGIN_WHITELIST:
        raise HTTPException(status_code=403, detail="Forbidden origin")
    return origin

class GenerateRequestAPI(BaseModel):
    conversationId: Optional[str] = None
    message: str

class TelemetryRating(BaseModel):
    conversationId: str
    type: Literal["rating_submitted"]
    rating: Literal["up", "down"]
    timestamp: datetime.datetime

class TelemetryLink(BaseModel):
    conversationId: str
    type: Literal["link_clicked"]
    url: str
    label: str
    timestamp: datetime.datetime

TelemetryEvent = TelemetryRating | TelemetryLink

async def load_history(conv_id: str) -> List[Dict[str, str]]:
    raw = await r.get(f"conversationId:{conv_id}")
    return json.loads(raw) if raw else []

async def save_history(conv_id: str, history: List[Dict[str, str]]):
    await r.set(f"conversationId:{conv_id}", json.dumps(history), ex=TTL_MIN * 60)

async def conv_exists(conv_id: str) -> bool:
    return bool(await r.exists(f"conversationId:{conv_id}"))

def expiry_iso() -> str:
    return (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=TTL_MIN)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

@API.post("/generation/imperia")
@limiter.limit("10/10 second;100/minute;1000/day")
async def generate_imperia(data: GenerateRequestAPI, request: Request, origin: str = Depends(require_allowed_origin)):
    conversationId_supplied = data.conversationId
    no_context = False

    if conversationId_supplied:
        history = await load_history(conversationId_supplied)
        if not history:
            no_context = True
            conv_id = str(uuid.uuid4())
            history = []
        else:
            conv_id = conversationId_supplied
            # history is already loaded
    else:
        no_context = True
        conv_id = str(uuid.uuid4())
        history = []

    history.append({"role": "user", "text": data.message})
    configuration = await latest_configuration()
    response_text = await generator.generate_content_async(history, **configuration)
    history.append({"role": "model", "text": response_text})
    await save_history(conv_id, history)

    return JSONResponse(
        status_code=200,
        content={
            "conversationId": conv_id,
            "response": response_text,
            "chatMessages": len(history),
            "noContext": no_context,
            "expiresAt": expiry_iso(),
        },
    )

async def store_telemetry_in_pocketbase(events: List[TelemetryEvent], request: Request, origin: str):
    token = await pb_api_superuser_token()
    # ua = request.headers.get("User-Agent", "")
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or \
     (request.client.host if request.client else "")

    async with httpx.AsyncClient(timeout=5.0) as client:
        # PocketBase has no bulk create, so fire requests; parallelize if needed
        tasks = []
        for ev in events:
            payload = {
                "conversationId": getattr(ev, "conversationId", None),
                "type": ev.type,
                "rating": getattr(ev, "rating", None),
                "url": getattr(ev, "url", None),
                "label": getattr(ev, "label", None),
                "timestamp": ev.timestamp.isoformat(),
                "origin": origin,
                "ip": ip,
                # "userAgent": ua,
                "meta": None,
            }
            res = await client.post(
                f"{GENERATION_PB_URL}/api/collections/telemetry/records",
                json=payload, headers={"Authorization": f"Bearer {token}"}
            )
            if res.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Telemetry store failed: {res.text}")
            
@API.post("/telemetry", status_code=204)
@limiter.limit("10/10 second;100/minute;1000/day")
async def telemetry(events: List[TelemetryEvent], request: Request, origin: str = Depends(require_allowed_origin)):
    for ev in events:
        if not await conv_exists(ev.conversationId):
            raise HTTPException(status_code=404, detail="conversation unknown or expired")

    await store_telemetry_in_pocketbase(events, request, origin)
    
    Response(status_code=204)

# mount routers
app.include_router(GUI)
app.include_router(API)

# rate-limit middleware on the whole app (only API routes have decorators)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
