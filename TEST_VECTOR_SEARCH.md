# Vector Search Testing Guide

## Option 1: Standalone Component Test (No API needed)

This tests each piece independently without needing the service running.

```bash
# On your server, inside xicare_bot directory:
cd ~/xicare_bot  # or wherever xicare_bot is deployed

# Test with default query
python3 test_vector_search.py

# Test with specific query
python3 test_vector_search.py "dementia care digital technology"
```

**What it checks:**
1. ✓ Embedding generation (768-dim multilingual)
2. ✓ Vector Search index connectivity
3. ✓ Neighbor retrieval from index
4. ✓ GCS metadata file existence
5. ✓ Document download from GCS

**Expected output:**
```
[CONFIG]
  PROJECT: sqlxpert
  LOCATION: europe-west4
  GCS_BUCKET: xicare-rag-corpus
  INDEX_ENDPOINT: projects/655677396893/locations/europe-west4/indexEndpoints/5132986471388545024
  DEPLOYED_INDEX_ID: xicare_rag_endpoint_europe_1772032015024

[1] Testing embedding generation...
✓ Embedding generated (768 dims)

[2] Testing Vector Search query...
✓ Found 3 neighbors
  [1] ID: document_id_1, Distance: 0.45
  [2] ID: document_id_2, Distance: 0.52
  [3] ID: document_id_3, Distance: 0.58

[3] Testing GCS metadata retrieval...
✓ Metadata retrieved (124 records)

[4] Testing document retrieval...
✓ Document retrieved (3245 chars)
  Preview: This is the document content...

============================================================
[✓] All tests passed! Vector Search is working.
============================================================
```

---

## Option 2: Full API Integration Test

This tests the actual endpoint behavior with Vector Search config.

```bash
# Start xicare_bot service first:
docker-compose up -d generation  # or your start command

# Then run API test:
python3 test_api_vector_search.py "your test question"

# Example:
python3 test_api_vector_search.py "Was sind Pflegeleistungen bei Demenz?"
```

**What it checks:**
1. API connectivity
2. Auth token validation
3. Full generation pipeline with Vector Search context
4. Response quality

**Setup required:**
```bash
# In .env on server:
GENERATION_API_URL=http://localhost:8000  # or your actual URL
TEST_TOKEN=your-actual-auth-token
```

---

## Troubleshooting

### "No neighbors found"
- Index endpoint or deployed index ID is wrong
- No vectors have been pushed to the index yet
- Run xicare_rag pipeline first

### "Metadata file not found"
- xicare_rag hasn't run the `push_vector_gcs` step
- Wrong GCS bucket name
- Check: `gsutil ls gs://xicare-rag-corpus/corpus_latest/`

### "Document blob not found"
- Document ID in metadata doesn't match actual GCS files
- Documents weren't uploaded properly
- Check: `gsutil ls gs://xicare-rag-corpus/corpus_latest/`

### "Connection refused" error
- Are you inside a Python venv? If yes, activate it first: `source venv/bin/activate`
- Are credentials loaded? Check: `echo $GOOGLE_APPLICATION_CREDENTIALS`

---

## Quick Diagnostic

If test fails, run this to show your actual config:

```bash
cd ~/xicare_bot
python3 << 'EOF'
import os
from dotenv import load_dotenv
load_dotenv()

print("Environment Check:")
print(f"  PROJECT_ID: {os.getenv('PROJECT_ID')}")
print(f"  LOCATION: {os.getenv('LOCATION')}")
print(f"  GCS_BUCKET: {os.getenv('GCS_BUCKET')}")
print(f"  INDEX_ENDPOINT: {os.getenv('INDEX_ENDPOINT')}")
print(f"  DEPLOYED_INDEX_ID: {os.getenv('DEPLOYED_INDEX_ID')}")
print(f"  GOOGLE_APPLICATION_CREDENTIALS: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")
print(f"  Creds file exists: {os.path.exists(os.getenv('GOOGLE_APPLICATION_CREDENTIALS', ''))}")
EOF
```

---

## In Docker Container

If xicare_bot runs in Docker:

```bash
# Find container ID
docker ps | grep generation

# Run test inside:
docker exec <container-id> python3 test_vector_search.py "test query"

# Or shell in and run:
docker exec -it <container-id> /bin/sh
cd /app/generation
python3 test_vector_search.py
```
