from typing import Awaitable, AsyncIterator  
from google import genai
from google.genai import types
from google.genai.types import HttpOptions, HarmBlockThreshold
from google.cloud import aiplatform_v1
from google.api_core.client_options import ClientOptions
from google.cloud import storage
import vertexai
import json
import os
import httpx
import google.auth

harm_thresholds = [
    "BLOCK_NONE",
    "BLOCK_ONLY_HIGH",
    "BLOCK_MEDIUM_AND_ABOVE",
    "BLOCK_LOW_AND_ABOVE",
]


class VertexAIRAG:
    def __init__(
        self,
        project: str,
        location: str,
    ):
        # Initialize genai client
        self._client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=HttpOptions(api_version="v1"),
        )
        
        # Initialize Vector Search and GCS clients
        self._project = project
        self._location = location
        vertexai.init(project=project, location=location)
        self._match_client = aiplatform_v1.IndexEndpointServiceClient(
            client_options=ClientOptions(api_endpoint=f"{location}-aiplatform.googleapis.com")
        )
        self._storage_client = storage.Client(project=project)
        self._gcs_bucket = os.getenv("GCS_BUCKET")

    def _retrieve_vector_search_context(self, query: str, index_endpoint: str, top_k: int = 20) -> str:
        """Retrieve relevant documents from Vector Search (REST API) and return as context."""
        try:
            # Embed the query
            from vertexai.language_models import TextEmbeddingModel
            embedding_model = TextEmbeddingModel.from_pretrained("text-multilingual-embedding-002")
            query_embedding = embedding_model.get_embeddings([query])[0].values
            
            # Parse index_endpoint to extract public REST endpoint
            # Expected format: projects/655677396893/locations/europe-west4/indexEndpoints/4998863644985917440
            # Deployed index ID from configuration: xicare_rag_endpoint_europe
            # Index ID: 8473144466897633280
            
            # For now, hardcode these from config (should be parameterized)
            public_endpoint_domain = os.getenv("VECTOR_SEARCH_PUBLIC_ENDPOINT", "1905681392.europe-west4-655677396893.vdb.vertexai.goog")
            project_id = self._project.split("@")[0] if "@" in self._project else "655677396893"  # fallback to numeric ID
            index_id = os.getenv("VECTOR_SEARCH_INDEX_ID", "8473144466897633280")
            deployed_index_id = os.getenv("VECTOR_SEARCH_DEPLOYED_INDEX_ID", "xicare_rag_endpoint_europe")
            
            # Construct REST URL for Vertex AI Vector Search using PUBLIC endpoint (Streaming Index)
            # Use indexEndpoints path as discovered in working curl command
            rest_url = f"https://{public_endpoint_domain}/v1/projects/{project_id}/locations/{self._location}/indexEndpoints/{index_endpoint.split('/')[-1]}:findNeighbors"
            
            # Get auth token (refresh if needed)
            from google.auth.transport.requests import Request
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            if not credentials.valid:
                credentials.refresh(Request())
            auth_token = credentials.token
            
            # Prepare request
            request_body = {
                "deployed_index_id": deployed_index_id,
                "queries": [
                    {
                        "datapoint": {
                            "feature_vector": query_embedding
                        },
                        "neighbor_count": top_k
                    }
                ]
            }
            
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }
            
            # Make REST request (blocking call within async context is OK for retrieval)
            response = httpx.post(rest_url, json=request_body, headers=headers, timeout=30.0)
            
            if response.status_code != 200:
                print(f"Vector Search REST API error: {response.status_code} - {response.text}")
                return ""
            
            result = response.json()
            neighbor_ids = []
            
            # Parse neighbors from REST response
            nearest = result.get("nearestNeighbors", [])
            if nearest and len(nearest) > 0 and "neighbors" in nearest[0]:
                for neighbor in nearest[0]["neighbors"]:
                    neighbor_id = neighbor.get("datapoint", {}).get("datapointId")
                    if neighbor_id:
                        neighbor_ids.append(neighbor_id)
            
            if not neighbor_ids:
                return ""
            
            # Download metadata.jsonl from GCS
            if not self._gcs_bucket:
                return ""
                
            metadata_blob = self._storage_client.bucket(self._gcs_bucket).blob("corpus_latest/metadata.jsonl")
            metadata_content = metadata_blob.download_as_text()
            
            # Parse metadata and map IDs to GCS URIs
            id_to_uri = {}
            for line in metadata_content.strip().split('\n'):
                if line:
                    record = json.loads(line)
                    id_to_uri[record["id"]] = record["gcs_text_uri"]
            
            # Retrieve and concatenate relevant documents
            context_parts = []
            for neighbor_id in neighbor_ids[:top_k]:
                gcs_uri = id_to_uri.get(neighbor_id)
                if gcs_uri:
                    # Parse GCS URI: gs://bucket/path
                    bucket_name, blob_path = gcs_uri.replace("gs://", "").split("/", 1)
                    blob = self._storage_client.bucket(bucket_name).blob(blob_path)
                    text_content = blob.download_as_text()
                    context_parts.append(f"Document: {neighbor_id}\n{text_content}\n")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            print(f"Error retrieving vector search context: {e}")
            import traceback
            traceback.print_exc()
            return ""

    def generate_content(
        self,
        history: list[dict[str, str]],
        system_prompt: str,
        user_role="user",
        model_name="gemini-2.0-flash-001",
        temperature=1.0,
        top_p=1.0,
        top_k: int | None = None,
        max_output_tokens=8192,
        datastore: str | None = None,
        rag_corpus: str | None = None,
        rag_similarity_top_k: int | None = 20,
        rag_vector_distance_threshold: float | None = 0.5,
        vector_search_index_endpoint: str | None = None,
        vector_search_similarity_top_k: int | None = 20,
        block_hate_speech=0,
        block_dangerous_content=0,
        block_sexually_explicit_content=0,
        block_harassment_content=0,
        seed: int | None = None,
    ) -> str:
        """
        Generate content using the configured Gemini model with RAG.

        Takes a conversation history and generates the next response, leveraging
        the RAG corpus to retrieve and incorporate relevant context.

        Args:
            history (list[dict[str, str]]): List of conversation turns as dictionaries
                with 'role' and 'text' keys. Each dictionary represents one turn in the conversation.
            user_role (str, optional): The role identifier for user messages. Defaults to "user".

        Returns:
            str: The generated text response from the model.
        """
        # Handle Vector Search context retrieval
        if vector_search_index_endpoint:
            # Get the last user message as query
            user_messages = [msg["text"] for msg in history if msg.get("role") == user_role]
            query = user_messages[-1] if user_messages else ""
            
            if query:
                vector_context = self._retrieve_vector_search_context(
                    query, vector_search_index_endpoint, vector_search_similarity_top_k or 20
                )
                if vector_context:
                    system_prompt = f"{system_prompt}\n\nContext from knowledge base:\n{vector_context}"
        
        # Generate and parse response
        response = self._client.models.generate_content(
            model=model_name,
            contents=self._create_contents(history, user_role),
            config=self._make_config(
                system_prompt,
                temperature,
                top_p,
                top_k,
                max_output_tokens,
                seed,
                datastore,
                rag_corpus,
                rag_similarity_top_k,
                rag_vector_distance_threshold,
                block_hate_speech,
                block_dangerous_content,
                block_sexually_explicit_content,
                block_harassment_content,
            ),
        )
        return response.text

    async def generate_content_async(
        self,
        history: list[dict[str, str]],
        system_prompt: str,
        user_role="user",
        model_name="gemini-2.0-flash-001",
        temperature=1.0,
        top_p=1.0,
        top_k: int | None = None,
        max_output_tokens=8192,
        datastore: str | None = None,
        rag_corpus: str | None = None,
        rag_similarity_top_k: int | None = 20,
        rag_vector_distance_threshold: float | None = 0.5,
        vector_search_index_endpoint: str | None = None,
        vector_search_similarity_top_k: int | None = 20,
        block_hate_speech=0,
        block_dangerous_content=0,
        block_sexually_explicit_content=0,
        block_harassment_content=0,
        seed: int | None = None,
    ) -> Awaitable[str]:
        """
        Generate content using the configured Gemini model with RAG asynchronously.

        Takes a conversation history and generates the next response, leveraging
        the RAG corpus to retrieve and incorporate relevant context.

        Args:
            history (list[dict[str, str]]): List of conversation turns as dictionaries
                with 'role' and 'text' keys. Each dictionary represents one turn in the conversation.
            user_role (str, optional): The role identifier for user messages. Defaults to "user".

        Returns:
            str: The generated text response from the model.
        """
        # Handle Vector Search context retrieval
        if vector_search_index_endpoint:
            # Get the last user message as query
            user_messages = [msg["text"] for msg in history if msg.get("role") == user_role]
            query = user_messages[-1] if user_messages else ""
            
            if query:
                vector_context = self._retrieve_vector_search_context(
                    query, vector_search_index_endpoint, vector_search_similarity_top_k or 20
                )
                if vector_context:
                    system_prompt = f"{system_prompt}\n\nContext from knowledge base:\n{vector_context}"
        
        # Generate and parse response
        response = await self._client.aio.models.generate_content(
            model=model_name,
            contents=self._create_contents(history, user_role),
            config=self._make_config(
                system_prompt,
                temperature,
                top_p,
                top_k,
                max_output_tokens,
                seed,
                datastore,
                rag_corpus,
                rag_similarity_top_k,
                rag_vector_distance_threshold,
                block_hate_speech,
                block_dangerous_content,
                block_sexually_explicit_content,
                block_harassment_content,
            ),
        )
        return response.text
    
    async def astream_content(
        self,
        history: list[dict[str, str]],
        system_prompt: str,
        user_role="user",
        model_name="gemini-2.0-flash-001",
        temperature=1.0,
        top_p=1.0,
        top_k: int | None = None,
        max_output_tokens=8192,
        datastore: str | None = None,
        rag_corpus: str | None = None,
        rag_similarity_top_k: int | None = 20,
        rag_vector_distance_threshold: float | None = 0.5,
        vector_search_index_endpoint: str | None = None,
        vector_search_similarity_top_k: int | None = 20,
        block_hate_speech=0,
        block_dangerous_content=0,
        block_sexually_explicit_content=0,
        block_harassment_content=0,
        seed: int | None = None,
    ) -> AsyncIterator[str]:
        
        # Handle Vector Search context retrieval
        if vector_search_index_endpoint:
            # Get the last user message as query
            user_messages = [msg["text"] for msg in history if msg.get("role") == user_role]
            query = user_messages[-1] if user_messages else ""
            
            if query:
                vector_context = self._retrieve_vector_search_context(
                    query, vector_search_index_endpoint, vector_search_similarity_top_k or 20
                )
                if vector_context:
                    system_prompt = f"{system_prompt}\n\nContext from knowledge base:\n{vector_context}"
        
        cfg = self._make_config(
            system_prompt,
            temperature,
            top_p,
            top_k,
            max_output_tokens,
            seed,
            datastore,
            rag_corpus,
            rag_similarity_top_k,
            rag_vector_distance_threshold,
            block_hate_speech,
            block_dangerous_content,
            block_sexually_explicit_content,
            block_harassment_content,
        )

        # iterate Google stream and yield text deltas
        # print("contents", self._create_contents(history, user_role))
        # print("cfg", cfg)
        async for chunk in await self._client.aio.models.generate_content_stream(
            model=model_name,
            contents=self._create_contents(history, user_role),
            config=cfg,
        ):
            # print(chunk.text)
            # chunk.text may be None; guard & only yield real deltas
            t = getattr(chunk, "text", "") or ""
            if t:
                yield t # “pause here, send this piece out, I’ll resume where I left off and send the next piece later”
                

    def _create_contents(
        self, history: list[dict[str, str]], user_role="user"
    ) -> list[types.Content]:
        return [
            types.Content(
                role="user" if item["role"] == user_role else "model",
                parts=[types.Part.from_text(text=item["text"])],
            )
            for item in history
        ]

    def _make_config(
        self,
        system_prompt: str,
        temperature: float,
        top_p: float | None,
        top_k: int | None,
        max_output_tokens: int,
        seed: int | None,
        datastore: str | None,
        rag_corpus: str | None,
        rag_similarity_top_k: int | None,
        rag_vector_distance_threshold: float | None,
        block_hate_speech: int,
        block_dangerous_content: int,
        block_sexually_explicit_content: int,
        block_harassment_content: int,
    ) -> types.GenerateContentConfig:
        tools = None
        if datastore:
            tools = [
                types.Tool(
                    retrieval=types.Retrieval(
                        vertex_ai_search=types.VertexAISearch(datastore=datastore)
                    )
                )
            ]
        elif rag_corpus:
            tools = [
                types.Tool(
                    retrieval=types.Retrieval(
                        vertex_rag_store=types.VertexRagStore(
                            rag_resources=[
                                types.VertexRagStoreRagResource(
                                    rag_corpus=rag_corpus
                                )
                            ],
                            similarity_top_k=rag_similarity_top_k,
                            vector_distance_threshold=rag_vector_distance_threshold,
                        )
                    )
                )
            ]
        return types.GenerateContentConfig(
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_output_tokens=max_output_tokens,
            seed=seed,
            response_modalities=["TEXT"],
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold=harm_thresholds[block_hate_speech],
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold=harm_thresholds[block_dangerous_content],
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold=harm_thresholds[block_sexually_explicit_content],
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold=harm_thresholds[block_harassment_content],
                ),
            ],
            tools=tools,
            system_instruction=[types.Part.from_text(text=system_prompt)],
        )
