from typing import List, Dict

# LLM and Embeddings
from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings

# Document Loading and Splitting
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Vector Store
from langchain_chroma import Chroma

# Chains and Prompts
from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

# Optional: Set Google Cloud Project and Location if not configured elsewhere
# os.environ["GCLOUD_PROJECT"] = "your-gcp-project-id"
# os.environ["GCLOUD_LOCATION"] = "your-gcp-region" # e.g., us-central1


class LangChainRAG:
    def __init__(
        self,
        system_prompt: str,
        model_name: str,  # e.g., "gemini-1.0-pro", "gemini-1.5-flash-001"
        temperature: float,
        top_k: int,
        top_p: float,
        max_output_tokens: int,
        documents_paths: List[str],
        chunk_size: int = 1024,
        chunk_overlap: int = 200,
        embedding_model_name: str = "textembedding-gecko@003",  # Or other Vertex AI embedding models
        vector_persist_directory: str = "./chroma_db_rag",
        # For Gemini models, convert_system_message_to_human can be useful
        # if the model doesn't directly support system messages in the same way.
        # However, ChatPromptTemplate handles formatting messages appropriately.
        # For most up-to-date VertexAI models, explicit system role is often supported.
        project: str | None = None,  # GCP Project ID
        location: str | None = None,  # GCP Location/Region
    ):
        """
        Initializes the LangChainRAG system.

        Args:
            system_prompt: The base system prompt for the RAG.
            model_name: The name of the Vertex AI model to use.
            temperature: The sampling temperature for the model.
            top_k: The top-k sampling parameter for the model.
            top_p: The top-p sampling parameter for the model.
            max_output_tokens: The maximum number of tokens for the model's output.
            documents_paths: A list of file paths to text documents to load.
            chunk_size: The size of chunks for splitting documents.
            chunk_overlap: The overlap between document chunks.
            embedding_model_name: The name of the Vertex AI embedding model.
            vector_persist_directory: Directory to persist ChromaDB data.
            project: GCP project ID. Defaults to GOOGLE_CLOUD_PROJECT env var or gcloud config.
            location: GCP location/region. Defaults to GOOGLE_CLOUD_LOCATION env var or gcloud config.
        """
        # Initialize Vertex AI LLM
        self.llm = ChatVertexAI(
            model_name=model_name,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            max_output_tokens=max_output_tokens,
            safety_settings={
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            },
            project=project,
            location=location,
            # convert_system_message_to_human=True, # Consider for older Gemini versions if system prompt issues arise
        )

        # Initialize Vertex AI Embeddings
        self.embeddings = VertexAIEmbeddings(
            model_name=embedding_model_name,
            project=project,
            location=location,
        )

        # Load and Split Documents
        print(f"Loading documents from paths: {documents_paths}")
        all_loaded_documents = []
        for doc_path in documents_paths:
            try:
                loader = TextLoader(doc_path, encoding="utf-8")
                all_loaded_documents.extend(loader.load())
            except Exception as e:
                print(f"Error loading document {doc_path}: {e}")
                # Optionally, re-raise or handle more gracefully

        if not all_loaded_documents:
            raise ValueError(
                "No documents were successfully loaded. Please check the document paths and content."
            )

        print(f"Splitting {len(all_loaded_documents)} documents into chunks...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        split_documents = text_splitter.split_documents(all_loaded_documents)
        print(f"Created {len(split_documents)} document chunks.")

        # Setup ChromaDB Vectorstore
        # You can choose to persist the DB and load it if it exists,
        # or rebuild it every time. For this example, we rebuild.
        print(f"Initializing ChromaDB vector store in '{vector_persist_directory}'...")
        self.vector_store = Chroma.from_documents(
            documents=split_documents,
            embedding=self.embeddings,
            persist_directory=vector_persist_directory,
            # collection_name="rag_collection" # Optional: good for managing multiple stores
        )
        # Ensure persistence (though from_documents with persist_directory usually handles it)
        # self.vector_store.persist() # Generally not needed if persist_directory is set in constructor/from_documents

        # 5. Create Retriever
        self.retriever = self.vector_store.as_retriever(
            search_type="similarity",  # common options: "similarity", "mmr"
            search_kwargs={"k": 5},  # number of documents to retrieve
        )
        print("Retriever created.")

        # 6. Create History-Aware Retriever (for rephrasing query based on history)
        contextualize_q_system_prompt = (
            "Given a chat history and the latest user question "
            "which might reference context in the chat history, "
            "formulate a standalone question which can be understood "
            "without the chat history. Do NOT answer the question, "
            "just reformulate it if needed and otherwise return it as is."
        )
        contextualize_q_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", contextualize_q_system_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
            ]
        )
        history_aware_retriever = create_history_aware_retriever(
            self.llm, self.retriever, contextualize_q_prompt
        )

        # 7. Create Document Chain (for answering question with context, incorporating the main system_prompt)
        # This prompt is fed the original question and the retrieved documents.
        prompt_template = (
            # The main system prompt from the user is prepended here.
            system_prompt
            + "\n\nUse the following pieces of retrieved context to answer the question. "
            "If you don't know the answer, just say that you don't know. "
            "Don't try to make up an answer."
            "\n\nContext:\n{context}"
        )
        Youtubeing_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", prompt_template),
                MessagesPlaceholder(
                    variable_name="chat_history"
                ),  # To maintain conversational context
                ("human", "{input}"),  # The original user input
            ]
        )
        document_chain = create_stuff_documents_chain(self.llm, Youtubeing_prompt)

        # 8. Create Conversational Retrieval Chain
        # This chain combines the history-aware retriever and the document chain.
        self.rag_chain = create_retrieval_chain(history_aware_retriever, document_chain)
        print("RAG chain created successfully.")

    def generate(self, conversation_history: List[Dict[str, str]]) -> str:
        """
        Generates the next message in the conversation using RAG.

        Args:
            conversation_history: A list of dictionaries, where each dictionary
                                  has "role" (either "user" or "model") and "text".
                                  Example:
                                  [
                                      {"role": "user", "text": "What is AlphaFold?"},
                                      {"role": "model", "text": "AlphaFold is an AI system..."}
                                      {"role": "user", "text": "How does it compare to RoseTTAFold?"}
                                  ]

        Returns:
            The generated text response from the model.
        """
        if not conversation_history:
            # Or raise an error, or handle based on desired behavior for empty history
            return "I need some input to start the conversation!"

        # The last message in the history is the current user query.
        # The rest is the chat history for the chain.
        current_user_input = ""
        if conversation_history[-1]["role"].lower() == "user":
            current_user_input = conversation_history[-1]["text"]
            # Langchain messages history should not include the current input
            history_for_chain_conversion = conversation_history[:-1]
        else:
            # This might happen if generate is called incorrectly, e.g., not after a user turn.
            # Or, if the very first call has a non-user message last (unlikely for this structure).
            print(
                "Warning: The last message in the provided history is not from a 'user'. "
                "Attempting to use it as input, but this might be unintended."
            )
            current_user_input = conversation_history[-1][
                "text"
            ]  # Assuming it's still the query
            history_for_chain_conversion = conversation_history[:-1]
            if not current_user_input:  # if last message was model and empty.
                return "Error: Cannot generate response without a valid user input."

        langchain_chat_history = []
        for message_dict in history_for_chain_conversion:
            if message_dict["role"].lower() == "user":
                langchain_chat_history.append(
                    HumanMessage(content=message_dict["text"])
                )
            elif message_dict["role"].lower() == "model":  # or "assistant", "ai"
                langchain_chat_history.append(AIMessage(content=message_dict["text"]))
            else:
                print(
                    f"Warning: Unknown role '{message_dict['role']}' in conversation history. Skipping."
                )

        # Invoke the RAG chain
        # The chain expects 'input' (current user query) and 'chat_history' (Langchain messages)
        response = self.rag_chain.invoke(
            {"input": current_user_input, "chat_history": langchain_chat_history}
        )

        # The response from create_retrieval_chain is a dictionary,
        # typically with an 'answer' key for the final response.
        # It might also contain 'context' (the retrieved documents).
        return response.get("answer", "Sorry, I couldn't generate a response.")
