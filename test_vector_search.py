#!/usr/bin/env python3
"""
Generic Vector Search integration test.

Reads config the same way the generation API does:
  - PROJECT_ID, LOCATION, GCS_BUCKET from .env
  - VECTOR_SEARCH_* vars from .env (with same defaults as vertexai.py)
  - Optionally fetches vector_search_index_endpoint from PocketBase config
    using GENERATION_PB_URL + PB_API_USER_EMAIL/PASSWORD from .env

Usage:
    python test_vector_search.py                          # default query
    python test_vector_search.py "your test query"        # custom query
"""

import sys
import os
import json

from dotenv import load_dotenv
load_dotenv()

import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage
from vertexai.language_models import TextEmbeddingModel
import vertexai
import httpx

# ---- Config from .env (same vars the app uses) ----
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION")
GCS_BUCKET = os.getenv("GCS_BUCKET")

PUBLIC_ENDPOINT = os.getenv("VECTOR_SEARCH_PUBLIC_ENDPOINT")
VECTOR_SEARCH_PROJECT_ID = os.getenv("VECTOR_SEARCH_PROJECT_ID")
DEPLOYED_INDEX_ID = os.getenv("VECTOR_SEARCH_DEPLOYED_INDEX_ID")

# ---- Try to get vector_search_index_endpoint from PocketBase (like app.py does) ----
INDEX_ENDPOINT = os.getenv("VECTOR_SEARCH_INDEX_ENDPOINT")  # manual override

if not INDEX_ENDPOINT:
    pb_url = os.getenv("GENERATION_PB_URL")
    pb_email = os.getenv("PB_API_USER_EMAIL")
    pb_password = os.getenv("PB_API_USER_PASSWORD")
    if pb_url and pb_email and pb_password:
        try:
            print("[config] Fetching vector_search_index_endpoint from PocketBase...")
            auth = httpx.post(
                f"{pb_url}/api/collections/_superusers/auth-with-password",
                json={"identity": pb_email, "password": pb_password}, timeout=5.0,
            )
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
            if items:
                INDEX_ENDPOINT = items[0].get("vector_search_index_endpoint") or None
                print(f"[config] Got index endpoint from PocketBase: {INDEX_ENDPOINT}")
            else:
                print("[config] WARNING: No configuration records in PocketBase")
        except Exception as e:
            print(f"[config] WARNING: Could not fetch from PocketBase: {e}")

# ---- Validate ----
REQUIRED = {
    "PROJECT_ID": PROJECT_ID,
    "LOCATION": LOCATION,
    "GCS_BUCKET": GCS_BUCKET,
    "VECTOR_SEARCH_PUBLIC_ENDPOINT": PUBLIC_ENDPOINT,
    "VECTOR_SEARCH_PROJECT_ID": VECTOR_SEARCH_PROJECT_ID,
    "VECTOR_SEARCH_INDEX_ENDPOINT": INDEX_ENDPOINT,
    "VECTOR_SEARCH_DEPLOYED_INDEX_ID": DEPLOYED_INDEX_ID,
}

missing = [k for k, v in REQUIRED.items() if not v]
if missing:
    print(f"ERROR: Could not resolve: {', '.join(missing)}")
    print("Set them in .env or ensure PocketBase is reachable.")
    sys.exit(1)

query = sys.argv[1] if len(sys.argv) > 1 else "healthcare and digital technology"
passed = 0
total = 4

print()
print(f"[CONFIG]")
for k, v in REQUIRED.items():
    print(f"  {k}: {v}")
print(f"  QUERY: {query}")
print()

# ===== [1] Embedding generation =====
print(f"[1/4] Embedding generation...")
try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    embedding_model = TextEmbeddingModel.from_pretrained("text-multilingual-embedding-002")
    query_embedding = embedding_model.get_embeddings([query])[0].values
    print(f"  PASS - {len(query_embedding)} dimensions")
    passed += 1
except Exception as e:
    print(f"  FAIL - {e}")
    print("  Cannot continue without embeddings.")
    sys.exit(1)
print()

# ===== [2] Vector Search findNeighbors =====
print(f"[2/4] Vector Search findNeighbors...")
neighbor_ids = []
try:
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if not credentials.valid:
        credentials.refresh(Request())

    endpoint_id = INDEX_ENDPOINT.split("/")[-1]

    rest_url = (
        f"https://{PUBLIC_ENDPOINT}/v1/projects/{VECTOR_SEARCH_PROJECT_ID}"
        f"/locations/{LOCATION}/indexEndpoints/{endpoint_id}:findNeighbors"
    )

    request_body = {
        "deployed_index_id": DEPLOYED_INDEX_ID,
        "queries": [{
            "datapoint": {"feature_vector": query_embedding},
            "neighbor_count": 5,
        }],
    }
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }

    print(f"  URL: {rest_url}")
    resp = httpx.post(rest_url, json=request_body, headers=headers, timeout=30.0)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

    nearest = resp.json().get("nearestNeighbors", [])
    if nearest and "neighbors" in nearest[0]:
        for n in nearest[0]["neighbors"]:
            nid = n.get("datapoint", {}).get("datapointId")
            if nid:
                neighbor_ids.append(nid)

    if not neighbor_ids:
        raise RuntimeError("Response OK but no neighbors returned")

    print(f"  PASS - {len(neighbor_ids)} neighbors found")
    for i, nid in enumerate(neighbor_ids[:5]):
        print(f"    [{i+1}] {nid}")
    passed += 1
except Exception as e:
    print(f"  FAIL - {e}")
print()

# ===== [3] GCS metadata retrieval =====
print(f"[3/4] GCS metadata.jsonl retrieval...")
id_to_uri = {}
try:
    storage_client = storage.Client(project=PROJECT_ID)
    blob = storage_client.bucket(GCS_BUCKET).blob("corpus_latest/metadata.jsonl")
    if not blob.exists():
        raise RuntimeError("corpus_latest/metadata.jsonl not found in bucket")

    for line in blob.download_as_text().strip().split("\n"):
        if line:
            rec = json.loads(line)
            id_to_uri[rec["id"]] = rec["gcs_text_uri"]

    print(f"  PASS - {len(id_to_uri)} records loaded")
    passed += 1
except Exception as e:
    print(f"  FAIL - {e}")
print()

# ===== [4] Document retrieval for neighbors =====
print(f"[4/4] Document retrieval for returned neighbors...")
try:
    if not neighbor_ids:
        raise RuntimeError("Skipped - no neighbors from step 2")
    if not id_to_uri:
        raise RuntimeError("Skipped - no metadata from step 3")

    found, missing_ids = 0, []
    for nid in neighbor_ids[:5]:
        base_id = nid.split("_part")[0]
        uri = id_to_uri.get(nid) or id_to_uri.get(base_id)
        if not uri:
            missing_ids.append(nid)
            continue
        bucket_name, blob_path = uri.replace("gs://", "").split("/", 1)
        doc_blob = storage_client.bucket(bucket_name).blob(blob_path)
        text = doc_blob.download_as_text()
        found += 1
        if found == 1:
            print(f"    Sample ({nid}): {text[:150].strip()}...")

    if missing_ids:
        print(f"    WARNING: {len(missing_ids)} neighbor IDs not in metadata: {missing_ids}")
    if found == 0:
        raise RuntimeError("No documents could be retrieved for any neighbor")

    print(f"  PASS - {found}/{len(neighbor_ids[:5])} documents retrieved")
    passed += 1
except Exception as e:
    print(f"  FAIL - {e}")
print()

# ===== Summary =====
print("=" * 50)
print(f"Results: {passed}/{total} steps passed")
if passed == total:
    print("Vector Search retrieval is fully working.")
else:
    print("Some steps failed - check output above.")
    sys.exit(1)
