import click
from dotenv import dotenv_values
from vertexai import rag
import vertexai

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
@click.option("--corpus-name", "-n", type=str, help="Name for the RAG corpus (format: projects/\{\}/locations/\{\}/ragCorpora/\{\})", requires=True)
@click.argument("files", nargs=-1)
# fmt: on
def delete_rag_files(corpus_name, files) -> None:
    """
    Deletes specified files from a RAG corpus in Vertex AI.

    This function removes the specified files from the given RAG corpus
    and provides confirmation messages for each deletion.
    """
    # Initialize Vertex AI API once per session
    vertexai.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    # Delete Files from the RagCorpus
    for file in files:
        rag.delete_file(file, corpus_name)
        click.echo(f"Deleted file {file} from corpus.")


if __name__ == "__main__":
    delete_rag_files()
