import os
import json
from google.cloud import aiplatform_v1 as aiplatform
from google.cloud.aiplatform_v1.services.match_service import MatchServiceClient
from google.cloud import storage
from vertexai.language_models import TextEmbeddingModel
import requests

# Configuration - hardcoded for testing since PocketBase config is now available
PROJECT = "sqlXpert"
LOCATION = "europe-west4"
GCS_BUCKET = "xicare-rag-bucket"  # Update if different
INDEX_ENDPOINT = "projects/655677396893/locations/europe-west4/indexEndpoints/5132986471388545024"
DEPLOYED_INDEX_ID = "xicare_rag_endpoint_europe_1772032015024"  # Update if different

print("[CONFIG]")
print(f"  PROJECT: {PROJECT}")
print(f"  LOCATION: {LOCATION}")
print(f"  GCS_BUCKET: {GCS_BUCKET}")
print(f"  INDEX_ENDPOINT: {INDEX_ENDPOINT}")
print(f"  DEPLOYED_INDEX_ID: {DEPLOYED_INDEX_ID}")
print()

def test_embedding():
    print("[1] Testing embedding generation...")
    try:
        model = TextEmbeddingModel.from_pretrained("text-multilingual-embedding-002")
        embeddings = model.get_embeddings(["test query"])
        embedding = embeddings[0].values
        print(f"✓ Embedding generated ({len(embedding)} dims)")
        return embedding
    except Exception as e:
        print(f"[✗] ERROR: {e}")
        return None

def test_vector_search(embedding):
    print("[2] Testing Vector Search query...")
    try:
        # Initialize client with correct regional endpoint
        match_client = MatchServiceClient(
            client_options={"api_endpoint": f"{LOCATION}-aiplatform.googleapis.com"}
        )

        # Create request
        request = aiplatform.FindNeighborsRequest(
            index_endpoint=INDEX_ENDPOINT,
            deployed_index_id=DEPLOYED_INDEX_ID,
            queries=[
                aiplatform.FindNeighborsRequest.Query(
                    datapoint=aiplatform.IndexDatapoint(
                        feature_vector=embedding,
                    ),
                    neighbor_count=4,  # Using the value from config
                )
            ],
        )

        response = match_client.find_neighbors(request)
        neighbors = response.nearest_neighbors[0].neighbors
        print(f"✓ Found {len(neighbors)} neighbors")
        return neighbors
    except Exception as e:
        print(f"[✗] ERROR: {e}")
        return None

def test_gcs_retrieval(neighbors):
    print("[3] Testing GCS document retrieval...")
    try:
        storage_client = storage.Client(project=PROJECT)
        bucket = storage_client.bucket(GCS_BUCKET)

        for i, neighbor in enumerate(neighbors[:2]):  # Test first 2
            vector_id = neighbor.datapoint.datapoint_id
            print(f"  Neighbor {i+1}: vector_id={vector_id}")

            # Load metadata
            metadata_blob = bucket.blob("corpus_latest/metadata.jsonl")
            metadata_content = metadata_blob.download_as_text()
            metadata_lines = metadata_content.strip().split('\n')

            doc_uri = None
            for line in metadata_lines:
                if line.strip():
                    metadata = json.loads(line)
                    if str(metadata.get('id')) == str(vector_id):
                        doc_uri = metadata.get('uri')
                        break

            if doc_uri:
                print(f"    ✓ Found document URI: {doc_uri}")
                # Optionally download and show snippet
                doc_blob = bucket.blob(doc_uri)
                content = doc_blob.download_as_text()
                snippet = content[:200] + "..." if len(content) > 200 else content
                print(f"    Content snippet: {snippet}")
            else:
                print(f"    [✗] No document URI found for vector_id {vector_id}")

        return True
    except Exception as e:
        print(f"[✗] ERROR: {e}")
        return False

if __name__ == "__main__":
    embedding = test_embedding()
    if embedding:
        neighbors = test_vector_search(embedding)
        if neighbors:
            test_gcs_retrieval(neighbors)
        else:
            print("Skipping GCS test due to Vector Search failure")
    else:
        print("Skipping Vector Search test due to embedding failure")