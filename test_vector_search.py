#!/usr/bin/env python3
"""
Standalone Vector Search integration test using REST API
For Vertex AI Vector Search (Streaming Index) with public endpoint
Run: python3 test_vector_search.py "your test query"
"""

import sys
import os
import json
from dotenv import load_dotenv
import google.auth
import httpx

# Load environment
load_dotenv()

# Configuration
PROJECT_ID = "655677396893"  # Numeric project ID
PROJECT_ALIAS = "sqlxpert"   # Project alias for SDK init
LOCATION = "europe-west4"
GCS_BUCKET = "xicare-rag-bucket"

# Vector Search IDs
INDEX_ENDPOINT = "projects/655677396893/locations/europe-west4/indexEndpoints/4998863644985917440"
DEPLOYED_INDEX_ID = "xicare_rag_endpoint_europe"
INDEX_ID = "8473144466897633280"

# Public REST endpoint for Vertex AI Vector Search (from gcloud describe)
PUBLIC_ENDPOINT = "1905681392.europe-west4-655677396893.vdb.vertexai.goog"
REST_API_BASE = f"https://{PUBLIC_ENDPOINT}/v1"

query = sys.argv[1] if len(sys.argv) > 1 else "healthcare and digital technology"

print(f"[CONFIG]")
print(f"  PROJECT_ID: {PROJECT_ID}")
print(f"  PUBLIC_ENDPOINT: {PUBLIC_ENDPOINT}")
print(f"  LOCATION: {LOCATION}")
print(f"  GCS_BUCKET: {GCS_BUCKET}")
print(f"  INDEX_ID: {INDEX_ID}")
print(f"  DEPLOYED_INDEX_ID: {DEPLOYED_INDEX_ID}")
print()


try:
    # ===== [1] Test embedding generation =====
    print(f"[1] Testing embedding generation...")
    import vertexai
    from vertexai.language_models import TextEmbeddingModel
    
    vertexai.init(project=PROJECT_ALIAS, location=LOCATION)
    embedding_model = TextEmbeddingModel.from_pretrained("text-multilingual-embedding-002")
    query_embedding = embedding_model.get_embeddings([query])[0].values
    print(f"✓ Embedding generated ({len(query_embedding)} dims)")
    print()
    
    # ===== [2] Test Vector Search via REST API =====
    print(f"[2] Testing Vector Search via REST API (Streaming Index)...")
    
    # Get credentials for auth header
    credentials, project = google.auth.default()
    auth_token = credentials.token
    print(f"✓ Authentication successful for project: {project}")
    
    # Construct REST request to public endpoint
    # For Vertex AI Vector Search, use the public VDB endpoint
    rest_url = f"{REST_API_BASE}/projects/{PROJECT_ID}/locations/{LOCATION}/indexes/{INDEX_ID}:findNeighbors"
    
    request_body = {
        "deployed_index_id": DEPLOYED_INDEX_ID,
        "queries": [
            {
                "datapoint": {
                    "feature_vector": query_embedding
                },
                "neighbor_count": 4
            }
        ]
    }
    
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    
    print(f"✓ Calling REST endpoint: {rest_url}")
    
    # Make REST call
    response = httpx.post(rest_url, json=request_body, headers=headers, timeout=30.0)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Vector Search REST call succeeded (status {response.status_code})")
        
        # Parse neighbors from response
        nearest = result.get("nearestNeighbors", [])
        if nearest and len(nearest) > 0 and "neighbors" in nearest[0]:
            neighbors = nearest[0]["neighbors"]
            print(f"✓ Found {len(neighbors)} neighbors")
            for i, neighbor in enumerate(neighbors[:5]):
                datapoint_id = neighbor.get("datapoint", {}).get("datapointId", "N/A")
                distance = neighbor.get("distance", "N/A")
                print(f"  [{i+1}] ID: {datapoint_id}, Distance: {distance}")
        else:
            print("✗ No neighbors in response")
            print(f"Response: {result}")
            raise RuntimeError("No neighbors found in Vector Search response")
    else:
        print(f"✗ REST call failed with status {response.status_code}")
        print(f"Response: {response.text}")
        raise RuntimeError(f"Vector Search REST API failed: {response.status_code}")
    
    print()
    
    # ===== [3] Test GCS metadata retrieval =====
    print(f"[3] Testing GCS metadata retrieval...")
    from google.cloud import storage
    
    storage_client = storage.Client(project=PROJECT_ALIAS)
    metadata_blob = storage_client.bucket(GCS_BUCKET).blob("corpus_latest/metadata.jsonl")
    
    if metadata_blob.exists():
        metadata_content = metadata_blob.download_as_text()
        lines = metadata_content.strip().split('\n')
        print(f"✓ Metadata retrieved ({len(lines)} records)")
        
        # Show first metadata record
        first_record = json.loads(lines[0])
        print(f"  First record: {first_record['id']}")
        print(f"  GCS URI: {first_record['gcs_text_uri']}")
    else:
        print(f"✗ Metadata file not found in GCS!")
    print()
    
    # ===== [4] Test document retrieval =====
    print(f"[4] Testing document retrieval...")
    if response.status_code == 200 and nearest and len(nearest) > 0 and "neighbors" in nearest[0]:
        # Parse all metadata
        id_to_uri = {}
        for line in lines:
            if line:
                record = json.loads(line)
                id_to_uri[record["id"]] = record["gcs_text_uri"]
        
        # Try to fetch first neighbor's document
        first_neighbor_id = nearest[0]["neighbors"][0].get("datapoint", {}).get("datapointId", None)
        
        if first_neighbor_id:
            gcs_uri = id_to_uri.get(first_neighbor_id)
            
            if gcs_uri:
                bucket_name, blob_path = gcs_uri.replace("gs://", "").split("/", 1)
                doc_blob = storage_client.bucket(bucket_name).blob(blob_path)
                
                if doc_blob.exists():
                    text_content = doc_blob.download_as_text()
                    print(f"✓ Document retrieved ({len(text_content)} chars)")
                    print(f"  Preview: {text_content[:200]}...")
                else:
                    print(f"✗ Document blob not found: {gcs_uri}")
            else:
                print(f"✗ Neighbor ID not in metadata: {first_neighbor_id}")
        else:
            print(f"✗ Could not extract neighbor ID from response")
    print()
    
    print("=" * 60)
    print("[✓] All tests passed! Vector Search is working.")
    print("=" * 60)
    
except Exception as e:
    print(f"\n[✗] ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
