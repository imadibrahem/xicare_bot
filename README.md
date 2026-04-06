# Berlin Chat Dev Interface

A dev interface for the new Berlin Administration chatbot using pocketbase and a sveltekit SPA.

## Setup

- Login with `gcloud auth application-default login` before starting scripts that use google vertex ai.

## Production

- Rename env.production to .env and fill in values
- Create a superuser in pocketbase using `pocketbase superuser create EMAIL PASS`

## Notes

- Current pocketbase version: v0.28.1

## Integration Tests

Two test scripts verify that the retrieval backends are working correctly. Both read configuration from `.env` and PocketBase automatically.

### Vector Search Test

Tests the full Vector Search retrieval pipeline: embedding generation, findNeighbors query, GCS metadata lookup, and document retrieval.

**Locally:**
```bash
python test_vector_search.py
python test_vector_search.py "your test query"
```

**On the VM (Docker):**
```bash
docker compose cp test_vector_search.py generation:/app/generation/test_vector_search.py
docker compose exec generation python test_vector_search.py
```

Required `.env` vars: `PROJECT_ID`, `LOCATION`, `GCS_BUCKET`, `VECTOR_SEARCH_PUBLIC_ENDPOINT`, `VECTOR_SEARCH_PROJECT_ID`, `VECTOR_SEARCH_DEPLOYED_INDEX_ID`. The `vector_search_index_endpoint` is fetched from PocketBase config.

### Vertex AI Search Test

Tests the Vertex AI Search (Discovery Engine) integration: PocketBase config fetch, datastore verification, Gemini grounding with datastore, and direct Discovery Engine search API.

**Locally:**
```bash
python test_vertex_ai_search.py
python test_vertex_ai_search.py "your test query"
```

**On the VM (Docker):**
```bash
docker compose cp test_vertex_ai_search.py generation:/app/generation/test_vertex_ai_search.py
docker compose exec generation python test_vertex_ai_search.py
```

Required `.env` vars: `PROJECT_ID`, `LOCATION`, `GENERATION_PB_URL`, `PB_API_USER_EMAIL`, `PB_API_USER_PASSWORD`. The `datastore` value is fetched from PocketBase config.

### Switching Retrieval Backends

Configure which backend is active in the PocketBase **configurations** collection:

| Backend | Set this field | Clear these fields |
|---|---|---|
| **Vertex AI Search** | `datastore` | `vector_search_index_endpoint`, `rag_corpus` |
| **Vector Search** | `vector_search_index_endpoint` | `datastore`, `rag_corpus` |

After changing, either wait 5 minutes (config cache TTL) or restart:
```bash
docker compose restart generation
```

