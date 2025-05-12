"""
Vertex AI RAG Module

This module provides a wrapper class for Google's Vertex AI with Retrieval-Augmented Generation (RAG) capabilities.
It allows for integration with Google's Gemini models, configured with a RAG corpus for retrieval
context during generation.
"""

import vertexai
from vertexai import rag
from vertexai.generative_models import (
    GenerativeModel,
    Tool,
    GenerationConfig,
    Part,
    SafetySetting,
    Content,
)


class VertexAIRAG:
    """
    A class for interacting with Google Vertex AI's Gemini model with RAG capabilities.

    This class initializes a Gemini 2.0 Flash model configured with a Retrieval Augmented Generation
    corpus that allows the model to fetch and use relevant information during generation.

    Safety settings for harmful content are turned off by default.
    """

    def __init__(
        self,
        system_prompt: str,
        project: str,
        rag_corpus: str,
        model_name="gemini-2.0-flash-001",
        location: str | None = None,
        temp=1.0,
        top_p=1.0,
        top_k: int | None = None,
        max_output_tokens=8192,
    ) -> None:
        """
        Initialize the VertexAIRAG instance.

        Args:
            system_prompt (str): The system prompt to guide the model's behavior.
            project (str): The Google Cloud project ID.
            rag_corpus (str): The name of the RAG corpus to use for retrieval.
            model_name (str): The name of the model from Vertex AI. Defaults to "gemini-2.0-flash-001".
            location (str | None, optional): The Google Cloud region. Defaults to None.
            temp (float, optional): Temperature for sampling. Higher values increase randomness. Defaults to 1.0.
            top_p (float, optional): Nucleus sampling parameter. Defaults to 1.0.
            top_k (int | None, optional): Top-k sampling parameter. Defaults to None.
            max_output_tokens (int, optional): Maximum number of tokens in the response. Defaults to 8192.
        """
        # Initialize Vertex AI with project and location from config
        vertexai.init(project=project, location=location)

        # Get RAG corpus
        rag_corpus = rag.get_corpus(rag_corpus)

        # Direct context retrieval
        rag_retrieval_config = rag.RagRetrievalConfig(
            top_k=3,  # Optional
            filter=rag.Filter(vector_distance_threshold=0.5),  # Optional
        )

        # Create a RAG retrieval tool
        rag_retrieval_tool = Tool.from_retrieval(
            retrieval=rag.Retrieval(
                source=rag.VertexRagStore(
                    rag_resources=[
                        rag.RagResource(
                            rag_corpus=rag_corpus.name,  # Currently only 1 corpus is allowed.
                            # Optional: supply IDs from `rag.list_files()`.
                            # rag_file_ids=["rag-file-1", "rag-file-2", ...],
                        )
                    ],
                    rag_retrieval_config=rag_retrieval_config,
                ),
            )
        )

        # Create generation config
        generate_content_config = GenerationConfig(
            temperature=temp,
            top_p=top_p,
            top_k=top_k,
            max_output_tokens=max_output_tokens,
        )

        # Create a Gemini model instance
        self.model = GenerativeModel(
            model_name=model_name,
            tools=[rag_retrieval_tool],
            system_instruction=Part.from_text(text=system_prompt),
            generation_config=generate_content_config,
            safety_settings=[
                SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"
                ),
                SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"
                ),
                SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            ],
        )

    def generate_content(self, history: list[dict[str, str]], user_role="user") -> str:
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
        # Create content from list of {"role": ... , "text": ...}
        contents = [
            Content(
                role="user" if item["role"] == user_role else "model",
                parts=[Part.from_text(text=item["text"])],
            )
            for item in history
        ]

        # Generate and parse response
        response = self.model.generate_content(contents)
        return response.candidates[0].content.parts[0].text
