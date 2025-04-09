from typing import Optional
import re
import os
import json
import click
import torch
from dotenv import dotenv_values
from tqdm import tqdm
import numpy as np
import itertools
import statistics
from sklearn.metrics.pairwise import cosine_similarity
from wtpsplit import SaT
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput

from chunking_tools import add_overlap, add_ids

config = dotenv_values(".env")


# fmt: off
@click.command()
@click.option("--output", "-o", type=click.Path(dir_okay=False), required=True, help="Output json file to save the chunks")
@click.option("--overlap", "-ol", type=int, default=0, help="How many words will overlap between chunks")
@click.option("--batch-size", "-b", type=click.IntRange(min=1, max_open=True), default=100, help="How many sentences to vectorize in each batch")
@click.option("--dimensionality", "-d", type=click.IntRange(min=1, max_open=True), help="Dimensionality of the generated embeddings (uses model default if not specified)")
@click.option("--similarity", "-s", type=click.FloatRange(min=0.0, max=1.0), default=0.8, help="How similar sentences have to be to be chunked together (smaller number leads to smaller chunk size)")
@click.option("--page-marker", "-pm", default=r"--- (?P<book>.+) --- (?P<chapter>.*) --- (?P<page>\d*) ---", help="Regex string for seperating the pages, needs to include named groups 'book', 'chapter' & 'page'")
@click.option("--no-loose-ends", "-l", is_flag=True, help="Remove leading or trailing half sentences from chunks")
@click.argument("text_path", type=click.Path(dir_okay=False, exists=True))
# fmt: on
def chunk_text_semantic(
    output: str,
    overlap: int,
    batch_size: int,
    dimensionality: Optional[int],
    similarity: float,
    page_marker: str,
    no_loose_ends: bool,
    text_path: str,
) -> None:
    """
    Process and chunk text using semantic similarity-based boundaries.
    """

    # Initialize Vertex AI
    aiplatform.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    # Load embeddings model
    embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")

    with open(text_path, encoding="utf-8") as f:
        text = f.read()

    # Split the input text into individual sentences
    single_sentences_list = split_sentences(text, page_marker)

    # Combine adjacent sentences to form a context window around each sentence
    combined_sentences = combine_sentences(
        [sentence["text"] for sentence in single_sentences_list]
    )

    # Convert the combined sentences into vector representations
    embeddings = convert_to_vector(
        embedding_model, combined_sentences, batch_size, dimensionality
    )

    # Calculate the cosine distances between consecutive combined sentence embeddings to measure similarity
    distances = calculate_cosine_distances(embeddings)

    # Determine the threshold distance for identifying breakpoints
    breakpoint_percentile_threshold = similarity * 100
    breakpoint_distance_threshold = np.percentile(
        distances, breakpoint_percentile_threshold
    )

    # Find all indices where the distance exceeds the calculated threshold, indicating a potential chunk breakpoint
    indices_above_thresh = [
        i
        for i, distance in enumerate(distances)
        if distance > breakpoint_distance_threshold
    ]

    # Initialize the list of chunks and a variable to track the start of the next chunk
    chunks = []
    start_index = 0

    def chunk_from_sentences(sentences: list[dict[str, list]]) -> dict[str, list]:
        """
        Create a chunk from a list of sentences with metadata.

        Args:
            sentences: List of sentence dictionaries with text and metadata

        Returns:
            Dictionary containing the combined text and consolidated metadata
        """
        return {
            "text": " ".join([sentence["text"] for sentence in sentences]),
            "book": [sentence["book"] for sentence in sentences][0],
            "chapter": [sentence["chapter"] for sentence in sentences][0],
            "page": list({page for sentence in sentences for page in sentence["page"]}),
        }

    # Loop through the identified breakpoints and create chunks accordingly
    for index in indices_above_thresh:
        chunk_sentences = single_sentences_list[start_index : index + 1]
        chunk = chunk_from_sentences(chunk_sentences)
        chunks.append(chunk)
        start_index = index + 1

    # If there are any sentences left after the last breakpoint, add them as the final chunk
    if start_index < len(single_sentences_list):
        chunk_sentences = single_sentences_list[start_index:]
        chunk = chunk_from_sentences(chunk_sentences)
        chunks.append(chunk)

    chunks = add_overlap(chunks, overlap, no_loose_ends)

    chunks = add_ids(chunks)

    # Print statistics
    click.echo(
        f"Split the text into {len(chunks)} chunks with an average length of {statistics.fmean([len(chunk['text'].split()) for chunk in chunks]):.1f} words."
    )

    # Saving chunks to file
    click.echo(f"Saving text to {output}")

    if os.path.dirname(output):
        os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False)

    click.echo(click.style("Text chunking complete.", fg="green"))


def split_with_named_groups(pattern: str, text: str) -> tuple[list[str], list[dict]]:
    """
    Splits a string using a regex pattern, including the named groups
    of the delimiter matches in the result list.

    Args:
        pattern: The regex pattern string. Must contain named groups
                 using the (?P<name>...) syntax if you want them captured.
        text: The string to split.

    Returns:
        A tuple of a list containing segments of text (strings) and
        a list of dictionaries of named groups from the delimiters.
        Returns a list containing only the original text and an empty
        list for the named groups if no matches are found.
    """
    splits = []
    groups = []
    last_end = 0
    compiled_pattern = re.compile(pattern)  # Compile for potential efficiency

    for match in compiled_pattern.finditer(text):
        # Add the text segment *before* the current match
        start_span, end_span = match.span()
        splits.append(text[last_end:start_span])

        # Add the dictionary of named groups from the current match
        groups.append(match.groupdict())

        # Update the position for the next segment
        last_end = end_span

    # Add the remaining text segment *after* the last match
    splits.append(text[last_end:])

    # Optional: Filter out empty strings if desired, though standard
    # split often keeps them. Example: remove empty strings resulting
    # from adjacent delimiters or delimiters at start/end.
    splits = [item for item in splits if item != ""]

    return splits, groups


def is_sentence_complete(text: str) -> bool:
    """
    Determines if a sentence appears to be complete based on ending punctuation.

    Args:
        text: The sentence text to check

    Returns:
        True if the sentence appears complete, False otherwise
    """
    # Strip whitespace to handle trailing spaces
    text = text.strip()

    # Empty text can't be complete
    if not text:
        return False

    # Check for common sentence ending patterns
    # This handles:
    # - Standard ending punctuation (., !, ?, ;)
    # - Quotes following punctuation (single or double)
    pattern = r'([.!?;…]|(?<=[.!?;…])["\']|\.{3})$'

    return bool(re.search(pattern, text))


def split_sentences(text: str, page_marker: str) -> list[dict[str, list]]:
    """
    Split text into sentences while preserving page/chapter/book metadata.

    This function processes a text that contains page markers, splits each page
    into individual sentences using a neural splitter, and combines sentences
    that span across page boundaries.

    Args:
        text: The input text containing page markers
        page_marker: Regex pattern to identify page boundaries and extract metadata

    Returns:
        List of dictionaries, each containing a sentence and its metadata
        (book, chapter, page list)
    """
    # Split the text into pages while preserving page information
    pages_text, pages_metadata = split_with_named_groups(page_marker, text)

    # Load sentence splitter
    sat = SaT("sat-3l-sm")

    # Use GPU acceleration if available
    if torch.cuda.is_available():
        sat.half().to("cuda")

    # Split each page into paragraphs and preserve metadata
    paragraphs = []
    for page_text, page_metadata in tqdm(
        zip([page.strip() for page in pages_text], pages_metadata),
        total=len(pages_text),
        desc="Splitting pages into paragraphs",
    ):
        paragraphs_split = re.split(r"\n+", page_text)
        if page_text:
            paragraphs = [
                *paragraphs,
                *[
                    {"text": paragraph.strip()} | page_metadata
                    for paragraph in paragraphs_split
                    if paragraph
                ],
            ]

    # Split paragraphs into sentences
    split_paragraphs = [
        {**paragraph, "text": sat.split(paragraph["text"])} for paragraph in paragraphs
    ]

    # Add newline to the beginning of previous paragraphs, so that they are preserved
    split_paragraphs = [
        {
            **paragraph,
            "text": [
                f"\n{sentence}" if index == 0 else sentence
                for index, sentence in enumerate(paragraph["text"])
            ],
        }
        for paragraph in split_paragraphs
    ]

    # Unpack the sentences, so each has proper metadata
    sentences = list(
        itertools.chain.from_iterable(
            [
                [{**paragraph, "text": sentence} for sentence in paragraph["text"]]
                for paragraph in split_paragraphs
            ]
        )
    )

    # Combine sentences that span multiple pages
    combined_sentences = []
    while len(sentences):
        # Extract sentence with metadata and convert page to a list
        current_sentence = sentences.pop(0)
        current_sentence = {
            **current_sentence,
            "page": [current_sentence["page"]],
        }
        # If the sentence continues on the next page (incomplete + different page number)
        # merge it with the next sentence and track both page numbers
        if (
            len(sentences)
            and sentences[0]["page"] != current_sentence["page"][0]
            and not is_sentence_complete(current_sentence["text"])
        ):
            next_sentence = sentences.pop(0)
            current_sentence["text"] += f" {next_sentence['text']}"
            current_sentence["page"].append(next_sentence["page"])
        combined_sentences.append(current_sentence)

    return combined_sentences


def combine_sentences(sentences: list[str]) -> list[str]:
    """Create context windows by combining each sentence with its neighbors."""
    result = []
    for i in range(len(sentences)):
        # Build context with previous, current, and next sentence
        parts = []
        if i > 0:
            parts.append(sentences[i - 1])
        parts.append(sentences[i])
        if i < len(sentences) - 1:
            parts.append(sentences[i + 1])
        result.append(" ".join(parts))
    return result


def convert_to_vector(
    embedding_model, texts: list[str], batch_size=250, dimensionality: int | None = None
) -> np.ndarray:
    """
    Convert text to vector embeddings using a pre-trained model.

    Takes a list of texts and generates vector embeddings in batches to
    efficiently process large datasets while managing memory usage.

    Args:
        embedding_model: The text embedding model to use
        texts: List of text strings to convert to vectors
        batch_size: Number of texts to process in each batch
        dimensionality: Optional output dimension size (None uses model default)

    Returns:
        NumPy array of embedding vectors, one per input text
        Empty array if embedding generation fails
    """
    try:
        inputs = [TextEmbeddingInput(text, "SEMANTIC_SIMILARITY") for text in texts]

        kwargs = dict(output_dimensionality=dimensionality) if dimensionality else {}

        embeddings_batches = []
        for inputs_batch in tqdm(
            list(itertools.batched(inputs, batch_size)),
            desc="Converting batches into vectors",
        ):
            embeddings = embedding_model.get_embeddings(inputs_batch, **kwargs)
            embeddings_batches.append(embeddings)

        return np.array([item.values for batch in embeddings_batches for item in batch])
    except Exception as e:
        click.echo(click.style(f"Error converting to vector: {e}", fg="red"))
        return np.array([])  # Return an empty array in case of an error


def calculate_cosine_distances(embeddings: np.ndarray) -> list[np.ndarray]:
    """
    Calculate the semantic distance between consecutive sentences.

    Computes the cosine distance (1 - cosine similarity) between each
    embedding and the next one in sequence, which measures how much the
    topic changes between sentences.

    Args:
        embeddings: NumPy array of embedding vectors

    Returns:
        List of cosine distances between consecutive embeddings.
        Higher values indicate greater semantic difference.
    """
    distances = []
    for i in range(len(embeddings) - 1):
        similarity = cosine_similarity([embeddings[i]], [embeddings[i + 1]])[0][0]
        distance = 1 - similarity
        distances.append(distance)
    return distances


if __name__ == "__main__":
    chunk_text_semantic()
