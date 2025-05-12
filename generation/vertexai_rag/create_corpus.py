import click
from dotenv import dotenv_values
from vertexai import rag
import vertexai

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
@click.option("--chunk-size", "-s", type=int, default=1024, help="Size of the embedded chunks (in tokens)")
@click.option("--chunk-overlap", "-o", type=int, default=200, help="Overlap between embedded chunks (in tokens)")
@click.option("--max-requests", "-m", type=int, default=1000, help="Maximum amount of embedding requests to make to the Vertex AI API per minute")
@click.option("--display-name", "-n", type=str, help="Display name for the RAG corpus", required=True)
@click.argument("paths", nargs=-1)
# fmt: on
def create_rag_corpus(
    chunk_size, chunk_overlap, max_requests, display_name, paths
) -> None:
    """
    Create a RAG corpus with the given display name and data urls (Google Cloud Storage bucket and Google Drive Links).
    """

    # Initialize Vertex AI API once per session
    vertexai.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    # Configure embedding model, for example "text-embedding-005".
    embedding_model_config = rag.RagEmbeddingModelConfig(
        vertex_prediction_endpoint=rag.VertexPredictionEndpoint(
            publisher_model="publishers/google/models/text-embedding-005"
        )
    )

    rag_corpus = rag.create_corpus(
        display_name=display_name,
        backend_config=rag.RagVectorDbConfig(
            rag_embedding_model_config=embedding_model_config
        ),
    )

    # Import Files to the RagCorpus
    if paths:
        click.echo("Importing files to RAG corpus...")
        rag.import_files(
            rag_corpus.name,
            paths,
            # Optional
            transformation_config=rag.TransformationConfig(
                chunking_config=rag.ChunkingConfig(
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                ),
            ),
            max_embedding_requests_per_min=max_requests,  # Optional
        )
    else:
        click.echo("Importing files to RAG corpus...")

    click.echo(f"RAG corpus created successfully!")
    click.echo(f"RAG corpus name: {rag_corpus.name}")


if __name__ == "__main__":
    create_rag_corpus()
