""" """

from typing import Awaitable
from langchain.chat_models import init_chat_model
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_chroma import Chroma


class VertexAIRAG:
    """ """

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
        vector_store_persist: str | None = None,
        documents: list[str] | None = None,
    ) -> None:
        """ """

        assert documents or vector_store_persist

        self.llm = init_chat_model(model_name, model_provider="google_vertexai")

        self.embeddings = VertexAIEmbeddings(
            model="text-embedding-005", location=location
        )

        self.vector_store = Chroma(
            collection_name="store",
            embedding_function=self.embeddings,
            persist_directory=vector_store_persist,  # Where to save data locally, remove if not necessary
        )

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
        """ """
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

    async def generate_content_async(
        self, history: list[dict[str, str]], user_role="user"
    ) -> Awaitable[str]:
        """ """
        # Create content from list of {"role": ... , "text": ...}
        contents = [
            Content(
                role="user" if item["role"] == user_role else "model",
                parts=[Part.from_text(text=item["text"])],
            )
            for item in history
        ]

        # Generate and parse response
        response = await self.model.generate_content_async(contents)
        return response.candidates[0].content.parts[0].text
