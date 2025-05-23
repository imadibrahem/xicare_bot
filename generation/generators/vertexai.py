from typing import Awaitable
from google import genai
from google.genai import types
from google.genai.types import HttpOptions


class VertexAIRAG:
    def __init__(
        self,
        project: str,
        location: str,
    ):
        # Initialize client
        self._client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=HttpOptions(api_version="v1"),
        )

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
            ),
        )
        return response.text

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
                                    rag_corpus="projects/convis/locations/europe-west4/ragCorpora/2305843009213693952"
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
                    threshold="BLOCK_LOW_AND_ABOVE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_LOW_AND_ABOVE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="BLOCK_LOW_AND_ABOVE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_LOW_AND_ABOVE"
                ),
            ],
            tools=tools,
            system_instruction=[types.Part.from_text(text=system_prompt)],
        )
