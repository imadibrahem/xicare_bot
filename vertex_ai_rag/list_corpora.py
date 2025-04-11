import click
from dotenv import dotenv_values
from vertexai import rag
import vertexai

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
# fmt: on
def list_corpora() -> None:
    """
    Lists all RAG corpora available in the Vertex AI project.

    This function retrieves and displays all RAG corpora in the configured
    project, showing both their display names and full resource names.
    """
    # Initialize Vertex AI API once per session
    vertexai.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    corpora = list(rag.list_corpora().pages)[0].rag_corpora

    for corpus in corpora:
        click.echo(f"{corpus.display_name}: {corpus.name}")


if __name__ == "__main__":
    list_corpora()
