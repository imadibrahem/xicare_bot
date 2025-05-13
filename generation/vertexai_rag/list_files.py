import click
from dotenv import dotenv_values
from vertexai import rag
import vertexai

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
@click.argument("corpus-name", type=str)
# fmt: on
def list_rag_files(corpus_name: str) -> None:
    """
    Lists all files in a specified RAG corpus using Vertex AI.

    This function retrieves and displays all files stored in the specified
    RAG corpus, showing both their display names and full resource names.

    Note:
        Requires PROJECT_ID and LOCATION to be set in the .env file.
    """
    # Initialize Vertex AI API once per session
    vertexai.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    # Get all files and list them
    files = rag.list_files(corpus_name)

    for file in list(files.pages)[0].rag_files:
        click.echo(f"{file.display_name}: {file.name}")


if __name__ == "__main__":
    list_rag_files()
