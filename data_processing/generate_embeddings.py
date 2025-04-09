from typing import Optional, Dict, Any, List
import click
import json
import itertools
from tqdm import tqdm
from dotenv import dotenv_values
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
@click.option("--output", "-o", type=click.Path(dir_okay=False), required=True, help="Output json lines file to save the data and embeddings")
@click.option("--batch-size", "-b", type=click.IntRange(min=1, max_open=True), default=10, help="How many sentences to vectorize in each batch")
@click.option("--dimensionality", "-d", type=click.IntRange(min=1, max_open=True), help="Dimensionality of the generated embeddings (uses model default if not specified)")
@click.argument("json_path", type=click.Path(dir_okay=False, exists=True))
# fmt: on
def generate_embeddings(
    output: str, batch_size: int, dimensionality: Optional[int], json_path: str
) -> None:
    """
    Generate text embeddings for chunks of text using Google Vertex AI.

    This script loads text data from a JSON file, generates vector embeddings
    for each text chunk using Google's text-embedding-005 model, and saves
    the results to a JSONL file.

    Args:
        output: Path to save the output JSONL file with text and embeddings
        batch_size: Number of text chunks to process in each API call batch
        dimensionality: Optional embedding vector size (default is model's default)
        json_path: Path to input JSON file containing text chunks to embed
    """
    # Initialize Vertex AI with project and location from config
    aiplatform.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    # Load the text embedding model from Google Vertex AI
    embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")

    # Load source text data from JSON file
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    try:
        # Convert data items to TextEmbeddingInput objects optimized for retrieval
        inputs = [
            TextEmbeddingInput(item["text"], "RETRIEVAL_DOCUMENT") for item in data
        ]

        # Set dimensionality parameter only if explicitly provided
        kwargs = dict(output_dimensionality=dimensionality) if dimensionality else {}

        # Generate embeddings in batches to avoid API limits
        embeddings_batches = []
        for inputs_batch in tqdm(
            list(itertools.batched(inputs, batch_size)),
            desc="Generating embeddings for batches",
        ):
            # Get embeddings for current batch and add to results
            embeddings = embedding_model.get_embeddings(inputs_batch, **kwargs)
            embeddings_batches.append(embeddings)
    except Exception as e:
        # Handle and display any errors during embedding generation
        click.echo(click.style(f"Error converting to vector: {e}", fg="red"))
    else:
        # Combine original data with corresponding embeddings
        data_embeddings = [
            {**item, "embedding": embedding.values}
            for item, embedding in zip(
                data, itertools.chain.from_iterable(embeddings_batches)
            )
        ]

        # Save combined data+embeddings to JSONL format for efficient storage
        # Write each JSON object as a separate line in the output file
        with open(output, "w", encoding="utf-8") as f:
            for item in data_embeddings:
                # Convert each item to a JSON string and write with newline
                json_line = json.dumps(item, ensure_ascii=False)
                f.write(json_line + "\n")

        click.echo(
            click.style(
                f"Successfully saved {len(data_embeddings)} embeddings to {output}",
                fg="green",
            )
        )


if __name__ == "__main__":
    generate_embeddings()
