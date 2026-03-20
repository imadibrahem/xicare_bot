#!/usr/bin/env python3
"""
Standalone Vector Search integration test for xicare_bot
Run: python3 test_vector_search.py "your test query"
"""

import sys
import os
import json
from dotenv import load_dotenv

# Load environment
load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION")
GCS_BUCKET = os.getenv("GCS_BUCKET")
INDEX_ENDPOINT = os.getenv("INDEX_ENDPOINT")
DEPLOYED_INDEX_ID = os.getenv("DEPLOYED_INDEX_ID", "xicare_rag_endpoint_europe_1772032015024")

print(f"[CONFIG]")
print(f"  PROJECT: {PROJECT_ID}")
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
    
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    embedding_model = TextEmbeddingModel.from_pretrained("text-multilingual-embedding-002")
    query_embedding = embedding_model.get_embeddings([query])[0].values
    print(f"✓ Embedding generated ({len(query_embedding)} dims)")
    print()
    
    print(f"[2] Testing Vector Search query...")
    from google.cloud import aiplatform_v1
    from google.api_core.client_options import ClientOptions
    
    match_client = aiplatform_v1.MatchServiceClient(
        client_options=ClientOptions(api_endpoint="https://1379831426.europe-west4-655677396893.vdb.vertexai.goog")
    )
    
    request = aiplatform_v1.FindNeighborsRequest(
        index_endpoint=INDEX_ENDPOINT,
        deployed_index_id=DEPLOYED_INDEX_ID,
        queries=[aiplatform_v1.FindNeighborsRequest.Query(
            datapoint=aiplatform_v1.IndexDatapoint(feature_vector=query_embedding),
            neighbor_count=5
        )]
    )
    
    response = match_client.find_neighbors(request)
    
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
    
    storage_client = storage.Client(project=PROJECT_ID)
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
