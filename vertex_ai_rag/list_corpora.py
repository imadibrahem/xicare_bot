import click
from dotenv import dotenv_values
from vertexai import rag
import vertexai

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
# fmt: on
def delete_rag_corpus():
    """
    Delete a RAG (Retrieval-Augmented Generation) corpus from Vertex AI.

    This function initializes the Vertex AI client using project and location
    credentials from the .env file, then permanently deletes the specified
    corpus. This operation cannot be undone.
    """
    # Initialize Vertex AI API once per session
    vertexai.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    corpora = list(rag.list_corpora().pages)[0].rag_corpora

    for corpus in corpora:
        click.echo(f"{corpus.display_name}: {corpus.name}")


if __name__ == "__main__":
    delete_rag_corpus()
