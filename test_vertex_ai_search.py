#!/usr/bin/env python3
"""
Vertex AI Search (Discovery Engine) integration test.

Reads config from .env and PocketBase, same as the generation API.
Tests: PocketBase config fetch, datastore grounding via Gemini, direct search API.

Usage:
    python test_vertex_ai_search.py                       # default query
    python test_vertex_ai_search.py "your test query"     # custom query
"""

import sys
import os
import json

from dotenv import load_dotenv
load_dotenv()

import httpx

# ---- Config from .env ----
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION")

# ---- Fetch datastore from PocketBase ----
DATASTORE = os.getenv("VERTEX_AI_SEARCH_DATASTORE")  # manual override

pb_url = os.getenv("GENERATION_PB_URL")
pb_email = os.getenv("PB_API_USER_EMAIL")
pb_password = os.getenv("PB_API_USER_PASSWORD")
pb_config = {}

passed = 0
total = 4
query = sys.argv[1] if len(sys.argv) > 1 else "Pflegeleistungen bei Demenz"

# ===== [1/4] PocketBase config fetch =====
print("[1/4] Fetching configuration from PocketBase...")
try:
    if not pb_url or not pb_email or not pb_password:
        raise RuntimeError("GENERATION_PB_URL, PB_API_USER_EMAIL, PB_API_USER_PASSWORD required in .env")

    auth = httpx.post(
        f"{pb_url}/api/collections/_superusers/auth-with-password",
        json={"identity": pb_email, "password": pb_password}, timeout=5.0,
    )
    if auth.status_code != 200:
        raise RuntimeError(f"PocketBase auth failed: {auth.status_code} {auth.text[:200]}")
    token = auth.json().get("token")

    resp = httpx.get(
        f"{pb_url}/api/collections/configurations/records",
        params={"perPage": 1, "filter": "default = true", "sort": "-updated"},
        headers={"Authorization": f"Bearer {token}"}, timeout=5.0,
    )
    items = resp.json().get("items", [])
    if not items:
        resp = httpx.get(
            f"{pb_url}/api/collections/configurations/records",
            params={"perPage": 1, "sort": "-updated"},
            headers={"Authorization": f"Bearer {token}"}, timeout=5.0,
        )
        items = resp.json().get("items", [])

    if not items:
        raise RuntimeError("No configuration records found in PocketBase")

    pb_config = items[0]
    if not DATASTORE:
        DATASTORE = pb_config.get("datastore") or None

    print(f"  model_name: {pb_config.get('model_name')}")
    print(f"  datastore: {DATASTORE}")
    print(f"  vector_search_index_endpoint: {pb_config.get('vector_search_index_endpoint') or '(empty)'}")
    print(f"  rag_corpus: {pb_config.get('rag_corpus') or '(empty)'}")

    if not DATASTORE:
        raise RuntimeError("datastore field is empty in PocketBase config")

    print(f"  PASS - datastore is configured")
    passed += 1
except Exception as e:
    print(f"  FAIL - {e}")
    if not DATASTORE:
        print("  Cannot continue without datastore.")
        sys.exit(1)
print()

# ===== [2/4] Verify datastore exists via Discovery Engine API =====
print("[2/4] Verifying datastore exists...")
try:
    import google.auth
    from google.auth.transport.requests import Request
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if not credentials.valid:
        credentials.refresh(Request())

    ds_url = f"https://discoveryengine.googleapis.com/v1/{DATASTORE}"
    resp = httpx.get(
        ds_url,
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "x-goog-user-project": PROJECT_ID,
        },
        timeout=10.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

    ds_info = resp.json()
    print(f"  displayName: {ds_info.get('displayName')}")
    print(f"  contentConfig: {ds_info.get('contentConfig')}")

    # Check document count
    docs_url = f"https://discoveryengine.googleapis.com/v1/{DATASTORE}/branches/default_branch/documents"
    resp2 = httpx.get(
        docs_url,
        params={"pageSize": 1},
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "x-goog-user-project": PROJECT_ID,
        },
        timeout=10.0,
    )
    if resp2.status_code == 200:
        docs_data = resp2.json()
        has_docs = len(docs_data.get("documents", [])) > 0
        print(f"  Has documents: {has_docs}")
        if not has_docs:
            raise RuntimeError("Datastore has no documents")
    else:
        print(f"  WARNING: Could not list documents: {resp2.status_code}")

    print(f"  PASS - datastore exists and has documents")
    passed += 1
except Exception as e:
    print(f"  FAIL - {e}")
print()

# ===== [3/4] Test Gemini with datastore grounding =====
print(f"[3/4] Testing Gemini generation with datastore grounding...")
print(f"  Query: {query}")
try:
    from google import genai
    from google.genai import types
    from google.genai.types import HttpOptions

    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
        http_options=HttpOptions(api_version="v1"),
    )

    model_name = pb_config.get("model_name", "gemini-2.0-flash-001")
    config = types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=1024,
        tools=[
            types.Tool(
                retrieval=types.Retrieval(
                    vertex_ai_search=types.VertexAISearch(datastore=DATASTORE)
                )
            )
        ],
        system_instruction=[types.Part.from_text(text="Answer based on the provided context.")],
    )

    response = client.models.generate_content(
        model=model_name,
        contents=[types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)],
        )],
        config=config,
    )

    if response.text:
        print(f"  Response length: {len(response.text)} chars")
        print(f"  Preview: {response.text[:200].strip()}...")
        print(f"  PASS - Gemini returned grounded response")
        passed += 1
    else:
        raise RuntimeError("Gemini returned empty response")
except Exception as e:
    print(f"  FAIL - {e}")
    import traceback
    traceback.print_exc()
print()

# ===== [4/4] Test Discovery Engine search directly =====
print(f"[4/4] Testing Discovery Engine search API directly...")
try:
    # Find the serving config (search app)
    search_url = f"https://discoveryengine.googleapis.com/v1/{DATASTORE}/servingConfigs/default_search:search"
    body = {
        "query": query,
        "pageSize": 3,
        "contentSearchSpec": {
            "snippetSpec": {"returnSnippet": True},
            "extractiveContentSpec": {"maxExtractiveSegmentCount": 3},
        },
    }
    resp = httpx.post(
        search_url,
        json=body,
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "x-goog-user-project": PROJECT_ID,
        },
        timeout=15.0,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

    results = resp.json().get("results", [])
    print(f"  Results returned: {len(results)}")
    for i, r in enumerate(results[:3]):
        doc = r.get("document", {})
        doc_name = doc.get("name", "").split("/")[-1]
        derived = doc.get("derivedStructData", {})
        title = derived.get("title", "N/A")
        link = derived.get("link", "N/A")
        print(f"    [{i+1}] {doc_name}: {title}")
        print(f"        link: {link}")
        snippets = derived.get("snippets", [])
        if snippets:
            print(f"        snippet: {snippets[0].get('snippet', '')[:100]}...")

    if not results:
        raise RuntimeError("Search returned no results")

    print(f"  PASS - search returned {len(results)} results")
    passed += 1
except Exception as e:
    print(f"  FAIL - {e}")
    import traceback
    traceback.print_exc()
print()

# ===== Summary =====
print("=" * 50)
print(f"Results: {passed}/{total} steps passed")
print(f"  DATASTORE: {DATASTORE}")
if passed == total:
    print("Vertex AI Search is fully working.")
else:
    print("Some steps failed - check output above.")
    sys.exit(1)
