import re
import os
import json
import click
import torch
from tqdm import tqdm
import numpy as np
import itertools
import statistics
from wtpsplit import SaT


# fmt: off
@click.command()
@click.option("--output", "-o", type=click.Path(dir_okay=False), required=True, help="Output json file to save the chunks")
@click.option("--overlap", "-ol", type=int, default=0, help="How many words will overlap between chunks")
@click.option("--page-marker", "-pm", default=r"--- (?P<book>.+) --- (?P<chapter>.*) --- (?P<page>\d*) ---", help="Regex string for seperating the pages, needs to include named groups 'book', 'chapter' & 'page'")
@click.argument("text_path", type=click.Path(dir_okay=False, exists=True))
# fmt: on
def chunk_text_paragraph(
    output: str,
    overlap: int,
    page_marker: str,
    text_path: str,
) -> None:
    """
    Process text files by splitting them into paragraphs with configurable word overlap. and saves it to a json file.

    Args:
        output: Path to save the JSON output file
        overlap: Number of words to overlap between chunks
        page_marker: Regex for identifying page breaks with named groups (book, chapter, page)
        text_path: Path to the input text file
    """

    with open(text_path, encoding="utf-8") as f:
        text = f.read()

    # Split the input text into individual paragraphs
    single_paragraphs_list = split_paragraphs(text, page_marker)

    chunks = add_overlap(single_paragraphs_list, overlap)

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


def is_paragraph_complete(text: str) -> bool:
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


def split_paragraphs(text: str, page_marker: str) -> list[dict[str, list]]:
    """
    Splits text into paragraphs while preserving page metadata.

    This function handles splitting text across multiple pages, and will combine
    paragraphs that span page boundaries.

    Args:
        text: The complete text to process
        page_marker: Regex pattern for identifying page markers with named groups
                     'book', 'chapter', and 'page'

    Returns:
        List of paragraph dictionaries, each containing:
        - 'text': The paragraph content
        - 'book': Book identifier
        - 'chapter': Chapter identifier
        - 'page': List of page numbers where the paragraph appears
    """
    # Split the text into pages while preserving page information
    pages_text, pages_metadata = split_with_named_groups(page_marker, text)

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

    # Combine paragraphs that span multiple pages
    combined_paragraphs = []
    while len(paragraphs):
        # Extract paragraph with metadata and convert page to a list
        current_paragraph = paragraphs.pop(0)
        current_paragraph = {
            "text": current_paragraph["text"],
            "book": current_paragraph["book"],
            "chapter": current_paragraph["chapter"],
            "page": [current_paragraph["page"]],
        }
        # If the paragraph continues on the next page (incomplete + different page number)
        # merge it with the next paragraph and track both page numbers
        if (
            len(paragraphs)
            and paragraphs[0]["page"] != current_paragraph["page"][0]
            and not is_paragraph_complete(current_paragraph["text"])
        ):
            next_sentence = paragraphs.pop(0)
            current_paragraph["text"] += f" {next_sentence['text']}"
            current_paragraph["page"].append(next_sentence["page"])
        combined_paragraphs.append(current_paragraph)

    return combined_paragraphs


def add_overlap(chunks: list[dict[str, list]], overlap: int) -> list[dict[str, list]]:
    """
    Adds overlapping words between chunks to improve context continuity.

    This function:
    1. Splits chunk into sentences using the SaT model
    2. Converts sentences to word tokens
    3. For each chunk, adds 'overlap' words from adjacent paragraphs
       (both before and after)

    Args:
        chunks: List of chunks dictionaries with text and metadata
        overlap: Number of words to overlap between paragraphs

    Returns:
        List of chunks with overlapping words added, maintaining the
        same structure but with extended text content
    """
    # Load sentence splitter
    sat = SaT("sat-3l-sm")

    # Use GPU acceleration if available
    if torch.cuda.is_available():
        sat.half().to("cuda")

    # Split paragraphs into sentences
    split_paragraphs = [
        {
            **paragraph,
            "text": [
                sentence.strip()
                for sentence in sat.split(paragraph["text"])
                if sentence
            ],
        }
        for paragraph in chunks
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
    # Split sentences into words
    split_paragraphs_words = [
        {
            **paragraph,
            "text": list(
                itertools.chain.from_iterable(
                    [sentence.strip(" ").split(" ") for sentence in paragraph["text"]]
                )
            ),
        }
        for paragraph in split_paragraphs
    ]

    overlapped_paragraphs = []
    for index, paragraph in enumerate(
        tqdm(split_paragraphs_words, desc="Overlapping paragraphs")
    ):
        current_overlap = overlap
        current_index = index
        current_paragraph = paragraph.copy()
        while current_overlap > 0 and current_index > 0:
            current_index -= 1
            overlap_paragraph_length = len(
                split_paragraphs_words[current_index]["text"]
            )
            current_paragraph["text"] = [
                *split_paragraphs_words[current_index]["text"][
                    -min(current_overlap, overlap_paragraph_length) :
                ],
                *current_paragraph["text"],
            ]
            current_overlap -= overlap_paragraph_length
            current_paragraph["page"] = list(
                set(
                    [
                        *current_paragraph["page"],
                        *split_paragraphs_words[current_index]["page"],
                    ]
                )
            )

        current_overlap = overlap
        current_index = index
        while current_overlap > 0 and current_index < len(split_paragraphs_words) - 1:
            current_index += 1
            overlap_paragraph_length = len(
                split_paragraphs_words[current_index]["text"]
            )
            current_paragraph["text"] = [
                *current_paragraph["text"],
                *split_paragraphs_words[current_index]["text"][
                    : min(current_overlap, overlap_paragraph_length)
                ],
            ]
            current_overlap -= overlap_paragraph_length
            current_paragraph["page"] = list(
                set(
                    [
                        *current_paragraph["page"],
                        *split_paragraphs_words[current_index]["page"],
                    ]
                )
            )

        overlapped_paragraphs.append(current_paragraph)

    overlapped_paragraphs = [
        {**paragraph, "text": " ".join(paragraph["text"]).strip()}
        for paragraph in overlapped_paragraphs
    ]
    return overlapped_paragraphs


if __name__ == "__main__":
    chunk_text_paragraph()
