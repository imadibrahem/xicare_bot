import os
from typing import Awaitable
from google import genai
from google.genai import types
from google.genai.types import HttpOptions


class VertexAISearch:
    def __init__(
        self,
        system_prompt: str,
        project: str,
        location: str | None = None,
        datastore: str | None = None,
    ):
        # Initialize client
        self._client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=HttpOptions(api_version="v1"),
        )

        # Setup system prompt
        self._system_instruction = types.Part.from_text(text=system_prompt)

        self._datastore = datastore

    def generate_content(
        self,
        history: list[dict[str, str]],
        user_role="user",
        model_name="gemini-2.0-flash-001",
        temp=1.0,
        top_p=1.0,
        top_k: int | None = None,
        max_output_tokens=8192,
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
            config=self._make_config(temp, top_p, top_k, max_output_tokens, seed),
        )
        return response.text

    async def generate_content_async(
        self,
        history: list[dict[str, str]],
        user_role="user",
        model_name="gemini-2.0-flash-001",
        temp=1.0,
        top_p=1.0,
        top_k: int | None = None,
        max_output_tokens=8192,
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
            config=self._make_config(temp, top_p, top_k, max_output_tokens, seed),
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
        temp: float,
        top_p: float | None,
        top_k: int | None,
        max_output_tokens: int,
        seed: int | None,
    ) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            temperature=temp,
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
            tools=[
                types.Tool(
                    retrieval=types.Retrieval(
                        vertex_ai_search=types.VertexAISearch(
                            datastore=os.environ.get("DATASTORE")
                        )
                    )
                )
            ],
            system_instruction=[self.system_instruction],
        )
