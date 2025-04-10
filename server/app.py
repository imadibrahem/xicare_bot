from typing import Optional
import click
import chromadb
import json
from dotenv import dotenv_values
import vertexai
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
@click.option("--dimensionality", "-d", type=click.IntRange(min=1, max_open=True), help="Dimensionality of the generated embeddings (uses model default if not specified)")
@click.argument("data_path", type=click.Path(dir_okay=False, exists=True), nargs=-1)
# fmt: on
def awaken_norbert(dimensionality: Optional[int], data_path: str) -> None:
    # Load embedded data
    data = []
    for path in data_path:
        with open(path, encoding="utf-8") as f:
            data.extend(json.load(f))

    # Initialize Vertex AI with project and location from config
    vertexai.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    # Load the text embedding model from Google Vertex AI
    embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")
    # Set dimensionality parameter only if explicitly provided
    kwargs = dict(output_dimensionality=dimensionality) if dimensionality else {}

    # Initiate chroma vector database & collection
    chroma_client = chromadb.Client()

    collection = chroma_client.create_collection(
        name="norbert-wiener-books",
        metadata={
            "hnsw:space": "cosine",
            "hnsw:construction_ef": 150,
            "hnsw:search_ef": 300,
            "hnsw:M": 32,
        },
    )

    metadata_keys = ["book", "chapter"]
    collection.add(
        documents=[item["text"] for item in data],
        embeddings=[item["embedding"] for item in data],
        metadatas=[
            {
                **{key: item[key] for key in item if key in metadata_keys},
                "page": ", ".join(item["page"]),
            }
            for item in data
        ],
        ids=[item["id"] for item in data],
    )

    # Query RAG
    query = "What is your earliest memory?"

    # TODO:
    # - Query Expansion: Use an LLM to generate variations or related terms
    #   for the original query and search for all of them.
    # - Hypothetical Document Embeddings (HyDE): Use an LLM to generate a
    #   hypothetical answer to the user's query first. Then, embed this
    #   hypothetical answer and use that embedding to search for similar real
    #   document chunks in ChromaDB. This often aligns the query embedding
    #   better with the document embedding space.

    # Convert query to embedding
    inputs = [TextEmbeddingInput(query, "RETRIEVAL_QUERY")]
    query_embeddings = embedding_model.get_embeddings(inputs, **kwargs)

    results = collection.query(
        query_embeddings=[embedding.values for embedding in query_embeddings],
        n_results=25,  # TODO: Maybe as high as 50
    )

    # TODO: Implement re-ranking

    click.echo(results)


if __name__ == "__main__":
    awaken_norbert()
