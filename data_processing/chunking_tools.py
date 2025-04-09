import torch
import uuid
from tqdm import tqdm
from wtpsplit import SaT


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
            "text": [
                word
                for sentence in paragraph["text"]
                for word in sentence.strip(" ").split(" ")
            ],
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


def add_ids(chunks: list[dict[str, list]]) -> list[dict[str, list]]:
    """
    Add sequential identifiers to each chunk in a list of chunks.

    Args:
        chunks: A list of dictionaries representing text chunks.

    Returns:
        A list of dictionaries where each dictionary has an additional 'id' key
        with a unique value.
    """
    return [{**chunk, "id": str(uuid.uuid4())} for chunk in chunks]
