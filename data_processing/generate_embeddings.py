from typing import Optional
import click
import json
import itertools
import time
import uuid
from tqdm import tqdm
from dotenv import dotenv_values
from langchain_text_splitters import RecursiveCharacterTextSplitter
import vertexai
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
@click.option("--output", "-o", type=click.Path(dir_okay=False), required=True, help="Output json lines file to save the data and embeddings")
@click.option("--chunk-size", "-c", type=click.IntRange(min=1, max_open=True), default=512, help="How many characters in a chunk")
@click.option("--chunk-overlap", "-co", type=click.IntRange(min=1, max_open=True), default=512, help="How many characters overlap between chunks")
@click.option("--batch-size", "-b", type=click.IntRange(min=1, max_open=True), default=30, help="How many sentences to vectorize in each batch")
@click.option("--batch-size", "-b", type=click.IntRange(min=1, max_open=True), default=30, help="How many sentences to vectorize in each batch")
@click.option("--dimensionality", "-d", type=click.IntRange(min=1, max_open=True), help="Dimensionality of the generated embeddings (uses model default if not specified)")
@click.option("--minute-rate", "-m", type=click.IntRange(min=1, max_open=True), help="How many requests to generate embeddings to make per minute")
@click.argument("textfile_path", type=click.Path(dir_okay=False, exists=True))
# fmt: on
def generate_embeddings(
    output: str,
    chunk_size: int,
    chunk_overlap: int,
    batch_size: int,
    dimensionality: Optional[int],
    minute_rate: Optional[int],
    textfile_path: str,
) -> None:
    """
    Chunk a text file and generate text embeddings for chunks of text using Google Vertex AI.

    This script loads text data from a file, chunks it and generates vector
    embeddings for each text chunk using Google's text-embedding-005 model,
    and saves the results to a JSON file.
    """
    # Initialize Vertex AI with project and location from config
    vertexai.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    # Load the text embedding model from Google Vertex AI
    embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")

    # Load source text from text file
    with open(textfile_path, encoding="utf-8") as f:
        text = f.read()

    # Chunk the text
    text_splitter = RecursiveCharacterTextSplitter(
        # Set a really small chunk size, just to show.
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False,
    )

    chunks = [
        {"document": chunk, "id": str(uuid.uuid4())}
        for chunk in text_splitter.create_documents([text])
    ]

    try:
        # Convert chunk texts to TextEmbeddingInput objects optimized for retrieval
        inputs = [
            TextEmbeddingInput(chunk["document"], "RETRIEVAL_DOCUMENT")
            for chunk in chunks
        ]

        # Set dimensionality parameter only if explicitly provided
        kwargs = dict(output_dimensionality=dimensionality) if dimensionality else {}

        # Generate embeddings in batches to avoid API limits
        embeddings_batches = []
        rpm = 0
        for inputs_batch in tqdm(
            list(itertools.batched(inputs, batch_size)),
            desc="Generating embeddings for batches",
        ):
            rpm + len(inputs_batch)
            if minute_rate and rpm > minute_rate:
                time.sleep(60)
                rpm = 0

            # Get embeddings for current batch and add to results
            embeddings = embedding_model.get_embeddings(inputs_batch, **kwargs)
            embeddings_batches.append(embeddings)
    except Exception as e:
        # Handle and display any errors during embedding generation
        click.echo(click.style(f"Error converting to vector: {e}", fg="red"))
    else:
        # Combine original data with corresponding embeddings
        data_embeddings = [
            {**chunk, "embedding": embedding.values}
            for chunk, embedding in zip(
                chunks, itertools.chain.from_iterable(embeddings_batches)
            )
        ]

        # Save combined data+embeddings to JSON format
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data_embeddings, f, ensure_ascii=False)

        click.echo(
            click.style(
                f"Successfully saved {len(data_embeddings)} embeddings to {output}",
                fg="green",
            )
        )


if __name__ == "__main__":
    generate_embeddings()
