import click
from dotenv import dotenv_values
from vertexai import rag
import vertexai

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
@click.argument("corpus_name", nargs=1)
# fmt: on
def delete_rag_corpus(corpus_name):

    # Initialize Vertex AI API once per session
    vertexai.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    rag.delete_corpus(corpus_name)

    click.echo(f"RAG corpus deleted successfully!")


if __name__ == "__main__":
    delete_rag_corpus()
