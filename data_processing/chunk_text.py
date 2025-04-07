import re
import os
import json
import click
from dotenv import dotenv_values
from tqdm import tqdm
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from wtpsplit import SaT
from google.cloud import aiplatform
from vertexai.preview.language_models import TextEmbeddingModel

config = dotenv_values(".env")


# fmt: off
@click.command()
@click.option("--output", "-o", type=click.Path(dir_okay=False), required=True, help="Output json file to save the chunks")
@click.option("--overlap", "-ol", type=int, default=0, help="How many words will overlap between chunks")
@click.option("--page-marker", "-pm", default=r"--- (?P<book>.+) --- (?P<chapter>.*) --- (?P<page>\d*) ---", help="Regex string for seperating the pages, needs to include named groups 'book', 'chapter' & 'page'")
@click.argument("text_path", type=click.Path(dir_okay=False, exists=True))
# fmt: on
def chunk_text(
    output: str, overlap: int, page_marker: str, text_path: str
) -> list[str]:
    # Initialize Vertex AI
    aiplatform.init(project=config["PROJECT_ID"], location=config["LOCATION"])

    # Load embeddings model
    embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")

    with open(text_path) as f:
        text = f.read()

    click.echo("Splitting the input text into individual sentences...")
    single_sentences_list = split_sentences(text, page_marker)

    # Combine adjacent sentences to form a context window around each sentence
    combined_sentences = combine_sentences(single_sentences_list)

    click.echo(
        "Convert the combined sentences into vector representations using a neural network model..."
    )
    embeddings = convert_to_vector(embedding_model, combined_sentences)

    # Calculate the cosine distances between consecutive combined sentence embeddings to measure similarity
    distances = calculate_cosine_distances(embeddings)

    # Determine the threshold distance for identifying breakpoints based on the 80th percentile of all distances
    breakpoint_percentile_threshold = 80
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

    # Loop through the identified breakpoints and create chunks accordingly
    for index in indices_above_thresh:
        chunk = " ".join(single_sentences_list[start_index : index + 1])
        chunks.append(chunk)
        start_index = index + 1

    # If there are any sentences left after the last breakpoint, add them as the final chunk
    if start_index < len(single_sentences_list):
        chunk = " ".join(single_sentences_list[start_index:])
        chunks.append(chunk)

    # Saving chunks to file
    click.echo(f"Saving text to {output}")

    if os.path.dirname(output):
        os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(chunks, f)

    click.echo(click.style("Text chunking complete.", fg="green"))


def split_with_named_groups(pattern: str, text: str) -> tuple[str, dict]:
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


def split_sentences(text: str, page_marker: str) -> list[dict[str]]:
    # Split the text into pages while preserving page information
    pages_text, pages_metadata = split_with_named_groups(page_marker, text)

    # Split each page into sentences
    sentences = []
    sat = SaT("sat-3l-sm")
    for page_text, page_metadata in tqdm(
        zip(pages_text, pages_metadata), total=len(pages_text)
    ):
        sentences_split = sat.split(page_text)
        if page_text:
            sentences = [
                *sentences,
                *[
                    {"text": sentence.strip()} | page_metadata
                    for sentence in sentences_split
                    if sentence
                ],
            ]
    # Combine sentences that span multiple pages
    combined_sentences = []
    while len(sentences):
        # Get a sentence including meatadata and turn page into a list
        current_sentence = sentences.pop(0)
        current_sentence = {
            "text": current_sentence["text"],
            "book": current_sentence["book"],
            "chapter": current_sentence["chapter"],
            "page": [current_sentence["page"]],
        }
        # If the sentence is the last on the page and does not end
        # there, add the next and append the page number
        if (
            len(sentences)
            and sentences[0]["page"] != current_sentence["page"][0]
            and not (
                current_sentence["text"][-1] in [".", ";", "!", "?"]
                or current_sentence["text"][-2:] in ['."', ';"', '!"', '?"']
            )
        ):
            next_sentence = sentences.pop(0)
            current_sentence["text"] += f" {next_sentence["text"]}"
            current_sentence["page"].append(next_sentence["page"])
        combined_sentences.append(current_sentence)

    return combined_sentences


def combine_sentences(sentences: list[dict[str]]) -> list[dict[str]]:
    # Create a buffer by combining each sentence with its previous and next sentence to provide a wider context
    combined_sentences = []
    for i in range(len(sentences)):
        combined_sentence = sentences[i]
        if i > 0:
            combined_sentence = sentences[i - 1] + " " + combined_sentence
        if i < len(sentences) - 1:
            combined_sentence += " " + sentences[i + 1]
        combined_sentences.append(combined_sentence)
    return combined_sentences


def convert_to_vector(embedding_model, texts: str) -> np.ndarray:
    # Try to generate embeddings for a list of texts using a pre-trained model and handle any exceptions
    try:
        embeddings = embedding_model.get_embeddings(texts)
        embeddings = np.array([embedding.values for embedding in embeddings])
        return embeddings
    except Exception as e:
        click.echo(click.style(f"Error converting to vector: {e}", fg="red"))
        return np.array([])  # Return an empty array in case of an error


def calculate_cosine_distances(embeddings: np.ndarray) -> list[np.ndarray]:
    # Calculate the cosine distance (1 - cosine similarity) between consecutive embeddings
    distances = []
    for i in range(len(embeddings) - 1):
        similarity = cosine_similarity([embeddings[i]], [embeddings[i + 1]])[0][0]
        distance = 1 - similarity
        distances.append(distance)
    return distances


if __name__ == "__main__":
    chunk_text()
