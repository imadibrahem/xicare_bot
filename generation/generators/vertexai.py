from typing import Awaitable, AsyncIterator  
from google import genai
from google.genai import types
from google.genai.types import HttpOptions, HarmBlockThreshold

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
        block_hate_speech=0,
        block_dangerous_content=0,
        block_sexually_explicit_content=0,
        block_harassment_content=0,
        seed: int | None = None,
    ) -> AsyncIterator[str]:
        
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
