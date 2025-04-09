import re
import os
import json
import click
from tqdm import tqdm
import statistics

from chunking_tools import add_overlap, add_ids, is_paragraph_complete


# fmt: off
@click.command()
@click.option("--output", "-o", type=click.Path(dir_okay=False), required=True, help="Output json file to save the chunks")
@click.option("--overlap", "-ol", type=int, default=0, help="How many words will overlap between chunks")
@click.option("--page-marker", "-pm", default=r"--- (?P<book>.+) --- (?P<chapter>.*) --- (?P<page>\d*) ---", help="Regex string for seperating the pages, needs to include named groups 'book', 'chapter' & 'page'")
@click.option("--no-loose-ends", "-l", is_flag=True, help="Remove leading or trailing half sentences from chunks")
@click.argument("text_path", type=click.Path(dir_okay=False, exists=True))
# fmt: on
def chunk_text_paragraph(
    output: str,
    overlap: int,
    page_marker: str,
    no_loose_ends: bool,
    text_path: str,
) -> None:
    """
    Process text files by splitting them into paragraphs with configurable word overlap. and saves it to a json file.
    """

    with open(text_path, encoding="utf-8") as f:
        text = f.read()

    # Split the input text into individual paragraphs
    chunks = split_paragraphs(text, page_marker)

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


if __name__ == "__main__":
    chunk_text_paragraph()
