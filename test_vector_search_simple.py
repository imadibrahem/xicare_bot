#!/usr/bin/env python3
"""
Simple Vector Search test using Vertex AI SDK
Run: python3 test_vector_search_simple.py
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION")
INDEX_ENDPOINT = os.getenv("INDEX_ENDPOINT")
DEPLOYED_INDEX_ID = os.getenv("DEPLOYED_INDEX_ID", "xicare_rag_endpoint_europe_1772032015024")

print(f"[CONFIG]")
print(f"  PROJECT: {PROJECT_ID}")
print(f"  LOCATION: {LOCATION}")
print(f"  INDEX_ENDPOINT: {INDEX_ENDPOINT}")
print(f"  DEPLOYED_INDEX_ID: {DEPLOYED_INDEX_ID}")
print()

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
    
    print(f"[2] Testing Vector Search query (Vertex AI SDK)...")
    from vertexai.preview import aiplatform_v1
    
    # Use the deployed index endpoint
    index_endpoint_client = aiplatform_v1.IndexEndpointServiceClient(
        client_options={"api_endpoint": f"{LOCATION}-aiplatform.googleapis.com"}
    )
    
    # Find neighbors
    request = aiplatform_v1.FindNeighborsRequest(
        index_endpoint=INDEX_ENDPOINT,
        deployed_index_id=DEPLOYED_INDEX_ID,
        queries=[aiplatform_v1.FindNeighborsRequest.Query(
            datapoint=aiplatform_v1.IndexDatapoint(
                feature_vector=query_embedding
            ),
            neighbor_count=5
        )]
    )
    
    response = index_endpoint_client.find_neighbors(request)
    
    if response.neighbors and response.neighbors[0].neighbors:
        neighbors = response.neighbors[0].neighbors
        print(f"✓ Found {len(neighbors)} neighbors")
        for i, neighbor in enumerate(neighbors[:5]):
            distance = getattr(neighbor, 'distance', 'N/A')
            print(f"  [{i+1}] ID: {neighbor.datapoint.datapoint_id}, Distance: {distance}")
    else:
        print(f"✗ No neighbors found!")
    print()
    
    print("=" * 60)
    print("[✓] Vertex AI SDK test completed!")
    print("=" * 60)
    
except Exception as e:
    print(f"\n[✗] ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
