import os, json, uuid, datetime
from typing import Optional, List, Dict, Any, Literal
from fastapi import FastAPI, APIRouter, Request, HTTPException, Depends, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field
import httpx
import uvicorn
from dotenv import load_dotenv
import asyncio

import redis.asyncio as redis
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

import time

from generators.vertexai import VertexAIRAG
from PIIFilter import PIIFilter
# Load environment variables from .env file
config = load_dotenv()

# Create the FastAPI app
app = FastAPI()

# Get RAG model
generator = VertexAIRAG(
    project=os.environ.get("PROJECT_ID"),
    location=os.environ.get("LOCATION"),
)

# --- Health & readiness endpoints ---
@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
async def ready():
    # ping redis
    pong = await r.ping()
    if not pong:
        raise HTTPException(status_code=503, detail="redis unavailable")
    # shallow PB check
    async with httpx.AsyncClient(timeout=2.0) as client:
        resp = await client.get(f"{GENERATION_PB_URL}/api/health")
        if resp.status_code != 200:
            raise HTTPException(status_code=503, detail="pocketbase unavailable")
    return {"status": "ready"}



ORIGIN_WHITELIST = {o.strip() for o in os.getenv("ORIGIN_WHITELIST", "").split(",") if o.strip()}
LIMIT_PER_IP_PER_10_SECS       = os.getenv("LIMIT_PER_IP_PER_10_SECS", "10/10 second")
LIMIT_PER_IP_PER_1_MIN         = os.getenv("LIMIT_PER_IP_PER_1_MIN", "50/minute")
LIMIT_PER_IP_PER_1_DAY         = os.getenv("LIMIT_PER_IP_PER_1_DAY", "400/day")
LIMIT_PER_ENDPOINT_PER_10_SECS = os.getenv("LIMIT_PER_ENDPOINT_PER_10_SECS", "20/10 second")
LIMIT_PER_ENDPOINT_PER_1_MIN   = os.getenv("LIMIT_PER_ENDPOINT_PER_1_MIN", "200/minute")
LIMIT_PER_ENDPOINT_PER_1_DAY   = os.getenv("LIMIT_PER_ENDPOINT_PER_1_DAY", "2000/day")
LIMIT_PER_SERVER_PER_10_SECS   = os.getenv("LIMIT_PER_SERVER_PER_10_SECS", "50/10 second")
LIMIT_PER_SERVER_PER_1_MIN     = os.getenv("LIMIT_PER_SERVER_PER_1_MIN", "300/minute")
LIMIT_PER_SERVER_PER_1_DAY     = os.getenv("LIMIT_PER_SERVER_PER_1_DAY", "4000/day")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ORIGIN_WHITELIST),  # exact origins only
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

# Redis with Rate-Limiter
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)
# Per-IP limiter (default)
def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    return (xff.split(",")[0].strip() if xff else request.client.host) or "unknown"
limiter = Limiter(key_func=client_ip, storage_uri=REDIS_URL)
def global_bucket(request: Request) -> str:
    return "global" 

def require_allowed_origin(request: Request):
    origin = request.headers.get("Origin")
    if not ORIGIN_WHITELIST or origin not in ORIGIN_WHITELIST:
        raise HTTPException(status_code=403, detail="Forbidden origin")
    return origin

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
    async with httpx.AsyncClient(timeout=2.0) as client:
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
pii_filter_instance = PIIFilter()

# before /generation/generate but now already routed GUI to / generation
@GUI.post("/generate")
@limiter.limit(f"{LIMIT_PER_IP_PER_10_SECS};{LIMIT_PER_IP_PER_1_MIN};{LIMIT_PER_IP_PER_1_DAY}") # per-IP limits
@limiter.shared_limit(f"{LIMIT_PER_ENDPOINT_PER_10_SECS};{LIMIT_PER_ENDPOINT_PER_1_MIN};{LIMIT_PER_ENDPOINT_PER_1_DAY}", scope="generation/generate", key_func=global_bucket) # global endpoint
@limiter.shared_limit(f"{LIMIT_PER_SERVER_PER_10_SECS};{LIMIT_PER_SERVER_PER_1_MIN};{LIMIT_PER_SERVER_PER_1_DAY}", scope="global:all", key_func=global_bucket) # global caps
async def generate(data: GenerateRequestGUI, request: Request, origin: str = Depends(require_allowed_origin)):
    # Extract token from request header
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    v = await verify_token(token)
    if not v:
        raise HTTPException(status_code=401, detail="Invalid token")
                        
    # Use token directly without refreshing
    auth_header = {"Authorization": f"Bearer {token}"}
    
    #clean_text = pii_filter_instance.anonymize_text(text=data.message)
    clean_text = data.message

    async with httpx.AsyncClient(timeout=5.0) as client:
        # Save user's message to PocketBase
        response = await client.post(
            f"{os.environ.get('GENERATION_PB_URL')}/api/collections/messages/records",
            json={
                "conversation": data.conversationId,
                "text": clean_text,
                "original_text": data.message,
                "role": "user",
                "rating": 0,
            },
            headers=auth_header,
        )
        response.raise_for_status()

        # Get the chat configuration
        response = await client.get(
            f"{os.environ.get('GENERATION_PB_URL')}/api/collections/conversations/records/{data.conversationId}",
            params={
                "sort": "created",
                "expand": "configuration",
            },
            headers=auth_header,
        )
        response.raise_for_status()
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
        response.raise_for_status()
        messages = response.json()["items"]

    # print("configuration UI", json.dumps(configuration, indent=2))
    # print("messages UI", messages)
    # Generate AI response
    response_text = await generator.generate_content_async(messages, **configuration)
    # print("response_text", response_text)
    async with httpx.AsyncClient(timeout=2.0) as client:
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

TTL_MIN = int(os.getenv("CONTEXT_TTL_MINUTES", "60"))
CONFIG_CACHE_SECONDS = int(os.getenv("CONFIG_CACHE_SECONDS", "300"))

GENERATION_PB_URL = os.environ.get("GENERATION_PB_URL")
PB_API_USER_EMAIL = os.environ.get("PB_API_USER_EMAIL")
PB_API_USER_PASSWORD = os.environ.get("PB_API_USER_PASSWORD")
                                   
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

        cfg = gen_config(item)

    await r.set("configuration:latest", json.dumps(cfg), ex=CONFIG_CACHE_SECONDS)
    return cfg

async def store_api_event(
    conversationId: str,
    conversationId_supplied: str,
    endpoint: str,
    status_code: int,
    duration_ms: int,
    origin: str,
    chatMessages: Optional[int] = None,
    noContext: Optional[bool] = None,
    expiresAt: Optional[str] = None,
    error_message: Optional[str] = None
):
    """Store metadata about every API call (without messages)."""
    token = await pb_api_superuser_token()
    payload = {
        "conversationId": conversationId,
        "conversationId_supplied": conversationId_supplied,
        "endpoint": endpoint,
        "status_code": status_code,
        "error_message": error_message,
        "duration_ms": duration_ms,
        "origin": origin,
        "chatMessages": chatMessages,
        "noContext": noContext,
        "expiresAt": expiresAt,
        "timestamp": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),

    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.post(
            f"{GENERATION_PB_URL}/api/collections/api_events/records",
            json=payload,
            headers={"Authorization": f"Bearer {token}"}
        )
        if res.status_code >= 400:
            print("Failed to store API event:", res.text)

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
@limiter.limit(f"{LIMIT_PER_IP_PER_10_SECS};{LIMIT_PER_IP_PER_1_MIN};{LIMIT_PER_IP_PER_1_DAY}") # per-IP limits
@limiter.shared_limit(f"{LIMIT_PER_ENDPOINT_PER_10_SECS};{LIMIT_PER_ENDPOINT_PER_1_MIN};{LIMIT_PER_ENDPOINT_PER_1_DAY}", scope="v1/generation/imperia", key_func=global_bucket) # global endpoint
@limiter.shared_limit(f"{LIMIT_PER_SERVER_PER_10_SECS};{LIMIT_PER_SERVER_PER_1_MIN};{LIMIT_PER_SERVER_PER_1_DAY}", scope="global:all", key_func=global_bucket) # global caps
async def generate_imperia(data: GenerateRequestAPI, request: Request, origin: str = Depends(require_allowed_origin)):
    start_time = time.perf_counter()
    conversationId_supplied = data.conversationId
    no_context = False
    conv_id = None
    history = []

    #try:
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

    # print("configuration API", json.dumps(configuration, indent=2))
    # print("history API", history)

    response_text = await generator.generate_content_async(history, **configuration)
    
    # print("response_text", response_text)
    
    history.append({"role": "model", "text": response_text})
    await save_history(conv_id, history)
    
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    await store_api_event(
            conversationId=conv_id,
            conversationId_supplied=conversationId_supplied,
            endpoint="/v1/generation/imperia",
            status_code=200,
            duration_ms=duration_ms,
            origin=origin,
            chatMessages=len(history),
            noContext=no_context,
            expiresAt=expiry_iso(),
    )

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
    """
    # for 500 would be more detail but not needed -> global_handler
    except HTTPException as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        await store_api_event(
            conversationId=conv_id,
            conversationId_supplied=conversationId_supplied,
            endpoint="/v1/generation/imperia",
            status_code=e.status_code,
            error_message=str(e.detail),
            duration_ms=duration_ms,
            origin=origin,
            chatMessages=len(history),
            noContext=no_context,
            expiresAt=expiry_iso(),
        )
        raise
    except Exception as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        await store_api_event(
            conversationId=conv_id,
            conversationId_supplied=conversationId_supplied,
            endpoint="/v1/generation/imperia",
            status_code=500,
            error_message=str(e),
            duration_ms=duration_ms,
            origin=origin,
            chatMessages=len(history),
            noContext=no_context,
            expiresAt=expiry_iso(),
        )
        raise
    """
    
@API.post("/generation/imperia/stream")
@limiter.limit(f"{LIMIT_PER_IP_PER_10_SECS};{LIMIT_PER_IP_PER_1_MIN};{LIMIT_PER_IP_PER_1_DAY}") # per-IP limits
@limiter.shared_limit(f"{LIMIT_PER_ENDPOINT_PER_10_SECS};{LIMIT_PER_ENDPOINT_PER_1_MIN};{LIMIT_PER_ENDPOINT_PER_1_DAY}", scope="v1/generation/imperia/stream", key_func=global_bucket) # global endpoint
@limiter.shared_limit(f"{LIMIT_PER_SERVER_PER_10_SECS};{LIMIT_PER_SERVER_PER_1_MIN};{LIMIT_PER_SERVER_PER_1_DAY}", scope="global:all", key_func=global_bucket) # global caps
async def generate_imperia_stream(
    data: GenerateRequestAPI,
    request: Request,
    origin: str = Depends(require_allowed_origin),
):
    start_time = time.perf_counter()
    conversationId_supplied = data.conversationId
    no_context = False
    conv_id = None
    history = []

    # build conv + history exactly like your non-streaming route
    if conversationId_supplied:
        history = await load_history(conversationId_supplied)
        if not history:
            no_context = True
            conv_id = str(uuid.uuid4())
            history = []
        else:
            conv_id = conversationId_supplied
    else:
        no_context = True
        conv_id = str(uuid.uuid4())
        history = []

    history.append({"role": "user", "text": data.message})
    configuration = await latest_configuration()

    async def ndjson_generator():
        buffer = []
        try:
            # stream from Vertex and forward deltas as NDJSON lines
            async for delta in generator.astream_content(history, **configuration):
                buffer.append(delta)
                yield (json.dumps({"type": "delta", "delta": delta}) + "\n").encode("utf-8")
                await asyncio.sleep(0)  # let the loop flush

            full_text = "".join(buffer)

            # persist like your normal endpoint
            history.append({"role": "model", "text": full_text})
            await save_history(conv_id, history)

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            await store_api_event(
                conversationId=conv_id,
                conversationId_supplied=conversationId_supplied,
                endpoint="/v1/generation/imperia/stream",
                status_code=200,
                duration_ms=duration_ms,
                origin=origin,
                chatMessages=len(history),
                noContext=no_context,
                expiresAt=expiry_iso(),
            )

            # send a final object that mirrors the non-streaming response
            final_obj = {
                "conversationId": conv_id,
                "response": full_text,
                "chatMessages": len(history),
                "noContext": no_context,
                "expiresAt": expiry_iso(),
            }
            yield (json.dumps({"type": "final", "data": final_obj}) + "\n").encode("utf-8")

        except Exception as e:
            # surface as an error line; also log telemetry like your handlers do
            err_line = json.dumps({"type": "error", "error": str(e)}) + "\n"
            yield err_line.encode("utf-8")
            raise

    return StreamingResponse(
        ndjson_generator(),
        # media_type="text/plain",
        media_type="application/x-ndjson",  # newline-delimited JSON
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # helpful if you’re behind nginx
            "Connection": "keep-alive",
        },
    )
    
######################################################
    
async def store_telemetry_in_pocketbase(events: List[TelemetryEvent], request: Request, origin: str):
    token = await pb_api_superuser_token()
    # ua = request.headers.get("User-Agent", "")
    # ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or \
    # (request.client.host if request.client else "")

    async with httpx.AsyncClient(timeout=5.0) as client:
        # PocketBase has no bulk create, so fire requests; parallelize if needed
        for ev in events:
            payload = {
                "conversationId": getattr(ev, "conversationId", None),
                "type": ev.type,
                "rating": getattr(ev, "rating", None),
                "url": getattr(ev, "url", None),
                "label": getattr(ev, "label", None),
                "timestamp": ev.timestamp.isoformat(),
                "origin": origin,
                # "ip": ip,
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
@limiter.limit(f"{LIMIT_PER_IP_PER_10_SECS};{LIMIT_PER_IP_PER_1_MIN};{LIMIT_PER_IP_PER_1_DAY}") # per-IP limits
@limiter.shared_limit(f"{LIMIT_PER_ENDPOINT_PER_10_SECS};{LIMIT_PER_ENDPOINT_PER_1_MIN};{LIMIT_PER_ENDPOINT_PER_1_DAY}", scope="v1/telemetry", key_func=global_bucket) # global endpoint
@limiter.shared_limit(f"{LIMIT_PER_SERVER_PER_10_SECS};{LIMIT_PER_SERVER_PER_1_MIN};{LIMIT_PER_SERVER_PER_1_DAY}", scope="global:all", key_func=global_bucket) # global caps
async def telemetry(events: List[TelemetryEvent], request: Request, origin: str = Depends(require_allowed_origin)):
    start_time = time.perf_counter()
    conversationIds = [ev.conversationId for ev in events]
    #try:
    for ev in events:
        if not await conv_exists(ev.conversationId):
            raise HTTPException(status_code=404, detail="conversation unknown or expired")

    await store_telemetry_in_pocketbase(events, request, origin)
    
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    
    await store_api_event(
            conversationId=None,
            conversationId_supplied=",".join(conversationIds),
            endpoint="/v1/telemetry",
            status_code=204,
            duration_ms=duration_ms,
            origin=origin,
    )
    
    return Response(status_code=204)
    
    """
    # global handler
    except HTTPException as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        await store_api_event(
            conversationId=None,
            conversationId_supplied=",".join(conversationIds),
            endpoint="/v1/telemetry",
            status_code=e.status_code,
            error_message=str(e.detail),
            duration_ms=duration_ms,
            origin=origin
        )
        raise
    except Exception as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        await store_api_event(
            conversationId=None,
            conversationId_supplied=",".join(conversationIds),
            endpoint="/v1/telemetry",
            status_code=500,
            error_message=str(e),
            duration_ms=duration_ms,
            origin=origin
        )
        raise
    """

# mount routers
app.include_router(GUI)
app.include_router(API)

# rate-limit middleware on the whole app
app.state.limiter = limiter

async def extract_conversation_ids(request: Request) -> Optional[str]:
    """Try to extract conversationId(s) from request body (both single + telemetry list)."""
    try:
        body = await request.json()
        if isinstance(body, dict) and "conversationId" in body:
            return body["conversationId"]
        elif isinstance(body, list) and body and "conversationId" in body[0]:
            return ",".join(
                str(ev.get("conversationId")) for ev in body if "conversationId" in ev
            )
    except Exception:
        pass
    return None


async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    # Default error message from SlowAPI
    error_message = str(exc.detail) if hasattr(exc, "detail") else str(exc)

    conversationId_supplied = await extract_conversation_ids(request)
    
    print(f"429 [RateLimitExceeded] {error_message}")

    # Store in PocketBase
    await store_api_event(
        conversationId=None,
        conversationId_supplied=conversationId_supplied,
        endpoint=str(request.url.path),
        status_code=429,
        error_message=error_message,
        duration_ms=0,
        origin=request.headers.get("Origin", "")
    )

    # Return normal SlowAPI response
    return _rate_limit_exceeded_handler(request, exc)

# override default
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)


app.add_middleware(SlowAPIMiddleware)


# Errors before logic
# If the error comes from outside FastAPI e.g. 403 Caddy Forbidden this is not stored.

# 401, 403, 404, 405, 429 (limiter also within FastAPI decorator)
# will trigger for any raise HTTPException inside FastAPI routes/ dependencies
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    conversationId_supplied = await extract_conversation_ids(request)

    print(f"[HTTPException] {exc.status_code} {exc.detail}")
    
    await store_api_event(
        conversationId=None,
        conversationId_supplied=conversationId_supplied,
        endpoint=str(request.url.path),
        status_code=exc.status_code,
        error_message=str(exc.detail),
        duration_ms=0,
        origin=request.headers.get("Origin", "")
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    # return JSONResponse(status_code=exc.status_code)

# 422 Unprocessable Entity FastAPI’s automatic validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    conversationId_supplied = await extract_conversation_ids(request)
    
    print(f"422 [ValidationError] {exc.errors()}")
    
    await store_api_event(
        conversationId=None,
        conversationId_supplied=conversationId_supplied,
        endpoint=str(request.url.path),
        status_code=422,
        error_message=str(exc.errors()),
        duration_ms=0,
        origin=request.headers.get("Origin", "")
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})
    # return JSONResponse(status_code=422)

# 500
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    conversationId_supplied = await extract_conversation_ids(request)

    print(f"500 [Exception] {repr(exc)}")
    
    await store_api_event(
        conversationId=None,
        conversationId_supplied=conversationId_supplied,
        endpoint=request.url.path,
        status_code=500,
        error_message=str(exc),
        duration_ms=0,
        origin=request.headers.get("Origin", "")
    )
    print({"detail": "Internal Server Error", "error": str(exc)})
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
