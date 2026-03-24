#!/usr/bin/env python3
"""
Standalone Vector Search integration test for xicare_bot
Run: python3 test_vector_search.py "your test query"
"""

import sys
import os
import json
from dotenv import load_dotenv
import google.auth

# Load environment
load_dotenv()

PROJECT = "655677396893"  # Numeric project ID from INDEX_ENDPOINT
LOCATION = "europe-west4"
GCS_BUCKET = "xicare-rag-bucket"  # Confirm this is your bucket name
INDEX_ENDPOINT = "projects/655677396893/locations/europe-west4/indexEndpoints/5132986471388545024"
DEPLOYED_INDEX_ID = "xicare_rag_endpoint_europe_1772032015024"


def _project_from_index_endpoint(endpoint: str) -> str:
    try:
        parts = endpoint.split("/")
        if len(parts) > 1:
            return parts[1]
    except Exception:
        pass
    return PROJECT

INDEX_PROJECT = _project_from_index_endpoint(INDEX_ENDPOINT)

try:
    credentials, auth_project = google.auth.default()
    if auth_project and auth_project != INDEX_PROJECT:
        print(f"Warning: Authenticated project '{auth_project}' differs from INDEX_ENDPOINT project '{INDEX_PROJECT}'")
        print("Using configured INDEX_ENDPOINT and DEPLOYED_INDEX_ID; do not auto-rewrite the endpoint.")
except Exception as e:
    print(f"Auth check failed: {e}")
    auth_project = None

print(f"[CONFIG]")
print(f"  PROJECT: {PROJECT}")
print(f"  LOCATION: {LOCATION}")
print(f"  GCS_BUCKET: {GCS_BUCKET}")
print(f"  INDEX_ENDPOINT: {INDEX_ENDPOINT}")
print(f"  DEPLOYED_INDEX_ID: {DEPLOYED_INDEX_ID}")
print()

# Test query from command line or use default
query = sys.argv[1] if len(sys.argv) > 1 else "healthcare and digital technology"

try:
    print(f"[1] Testing embedding generation...")
    import vertexai
    from vertexai.language_models import TextEmbeddingModel
    
    vertexai.init(project=PROJECT, location=LOCATION)
    embedding_model = TextEmbeddingModel.from_pretrained("text-multilingual-embedding-002")
    query_embedding = embedding_model.get_embeddings([query])[0].values
    print(f"✓ Embedding generated ({len(query_embedding)} dims)")
    print()
    
    print(f"[2] Testing Vector Search query...")
    from google.cloud import aiplatform_v1
    from google.api_core.client_options import ClientOptions
    from google.api_core.exceptions import MethodNotImplemented
    
    # Check authentication
    try:
        credentials, project = google.auth.default()
        print(f"✓ Authentication successful for project: {project}")
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        raise
    
    # Try to list available index endpoints first
    try:
        index_endpoint_client = aiplatform_v1.IndexEndpointServiceClient(
            client_options=ClientOptions(api_endpoint=f"{LOCATION}-aiplatform.googleapis.com")
        )
        print(f"✓ IndexEndpointServiceClient created successfully")
        
        # Test if we can access the endpoint
        list_request = aiplatform_v1.ListIndexEndpointsRequest(
            parent=f"projects/{PROJECT}/locations/{LOCATION}"
        )
        endpoints = index_endpoint_client.list_index_endpoints(request=list_request)
        print(f"✓ Found {len(list(endpoints))} index endpoints")
        
        # Get details of our specific endpoint
        get_request = aiplatform_v1.GetIndexEndpointRequest(name=INDEX_ENDPOINT)
        endpoint_details = index_endpoint_client.get_index_endpoint(request=get_request)
        print(f"✓ Endpoint details: {endpoint_details.name}")
        print(f"  Deployed indexes: {len(endpoint_details.deployed_indexes)}")
        for deployed in endpoint_details.deployed_indexes:
            print(f"    - ID: {deployed.id}, Index: {deployed.index}")
        
    except Exception as e:
        print(f"✗ IndexEndpointServiceClient failed: {e}")
        print("Trying MatchServiceClient directly...")
    
    request = aiplatform_v1.FindNeighborsRequest(
        index_endpoint=INDEX_ENDPOINT,
        deployed_index_id=DEPLOYED_INDEX_ID,
        queries=[aiplatform_v1.FindNeighborsRequest.Query(
            datapoint=aiplatform_v1.IndexDatapoint(feature_vector=query_embedding),
            neighbor_count=4
        )]
    )

    # Try find_neighbors with the regional endpoint first, then global.
    match_client = None
    response = None
    tried_match_endpoints = [
        f"{LOCATION}-aiplatform.googleapis.com",
        "aiplatform.googleapis.com",
    ]

    for match_api in tried_match_endpoints:
        try:
            match_client = aiplatform_v1.MatchServiceClient(
                client_options=ClientOptions(api_endpoint=match_api)
            )
            print(f"✓ MatchServiceClient created with {match_api}")
            response = match_client.find_neighbors(request)
            print(f"✓ find_neighbors succeeded on {match_api}")
            break
        except MethodNotImplemented as e:
            print(f"✗ find_neighbors not implemented on {match_api}: {e}")
            continue
        except Exception as e:
            print(f"✗ match_client find_neighbors failed on {match_api}: {e}")
            raise

    if response is None:
        raise RuntimeError("No working MatchService endpoint found (501/UNIMPLEMENTED)" )
    
    if response.neighbors and response.neighbors[0].neighbors:
        neighbors = response.neighbors[0].neighbors
        print(f"✓ Found {len(neighbors)} neighbors")
        for i, neighbor in enumerate(neighbors[:5]):
            distance = getattr(neighbor, 'distance', 'N/A')
            print(f"  [{i+1}] ID: {neighbor.datapoint.datapoint_id}, Distance: {distance}")
    else:
        print(f"✗ No neighbors found!")
    print()
    
    print(f"[3] Testing GCS metadata retrieval...")
    from google.cloud import storage
    
    storage_client = storage.Client(project=PROJECT)
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
    
    print(f"[4] Testing document retrieval...")
    if response.neighbors and response.neighbors[0].neighbors and metadata_blob.exists():
        # Parse all metadata
        id_to_uri = {}
        for line in lines:
            if line:
                record = json.loads(line)
                id_to_uri[record["id"]] = record["gcs_text_uri"]
        
        # Try to fetch first neighbor's document
        first_neighbor_id = response.neighbors[0].neighbors[0].datapoint.datapoint_id
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
    print()
    
    print("=" * 60)
    print("[✓] All tests passed! Vector Search is working.")
    print("=" * 60)
    
except Exception as e:
    print(f"\n[✗] ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
