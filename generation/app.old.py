import click
from dotenv import dotenv_values
from vertexai import rag
import vertexai

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
# fmt: on
def awaken_norbert() -> None:
    # Initialize Vertex AI with project and location from config
    vertexai.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    rag_corpus = rag.get_corpus(config["RAG_CORPUS"])

    # TODO
    query = "What is your earliest memory?"
    # query = "Thank you that is very interesting and gives me things to think about. I wonder how that relates to robotics as well. Now please a different topic. Could you tell me of your earliest memory?"

    # Direct context retrieval
    rag_retrieval_config = rag.RagRetrievalConfig(
        top_k=10,  # Optional
        filter=rag.Filter(vector_distance_threshold=0.5),  # Optional
    )
    results = rag.retrieval_query(
        rag_resources=[
            rag.RagResource(
                rag_corpus=rag_corpus.name,
            )
        ],
        text=query,
        rag_retrieval_config=rag_retrieval_config,
    )

    click.echo(results)


if __name__ == "__main__":
    awaken_norbert()
