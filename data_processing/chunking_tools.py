import torch
import uuid
import copy
import re
from tqdm import tqdm
from wtpsplit import SaT


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


def add_overlap(
    chunks: list[dict[str, list]], overlap: int, trim_loose_ends: bool = False
) -> list[dict[str, list]]:
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
                [word for word in sentence.strip(" ").split(" ")]
                for sentence in paragraph["text"]
            ],
        }
        for paragraph in split_paragraphs
    ]

    # Add overlap
    overlapped_paragraphs = []
    for index, paragraph in enumerate(
        tqdm(split_paragraphs_words, desc="Overlapping paragraphs")
    ):
        current_overlap = overlap
        current_paragraph_index = index
        current_paragraph = copy.deepcopy(paragraph)
        while current_overlap > 0 and current_paragraph_index > 0:
            current_paragraph_index -= 1
            current_sentence_index = (
                len(split_paragraphs_words[current_paragraph_index]["text"]) - 1
            )
            while current_overlap > 0 and current_sentence_index > 0:
                overlap_sentence_length = len(
                    split_paragraphs_words[current_paragraph_index]["text"][
                        current_sentence_index
                    ]
                )
                current_paragraph["text"] = [
                    split_paragraphs_words[current_paragraph_index]["text"][
                        current_sentence_index
                    ][-min(current_overlap, overlap_sentence_length) :],
                    *current_paragraph["text"],
                ]
                current_overlap -= overlap_sentence_length
                current_paragraph["page"].extend(
                    split_paragraphs_words[current_paragraph_index]["page"]
                )
                current_sentence_index -= 1

        current_overlap = overlap
        current_paragraph_index = index
        while (
            current_overlap > 0
            and current_paragraph_index < len(split_paragraphs_words) - 1
        ):
            current_paragraph_index += 1
            current_sentence_index = 0
            while (
                current_overlap > 0
                and current_sentence_index
                < len(split_paragraphs_words[current_paragraph_index]["text"]) - 1
            ):
                overlap_sentence_length = len(
                    split_paragraphs_words[current_paragraph_index]["text"][
                        current_sentence_index
                    ]
                )
                current_paragraph["text"] = [
                    *current_paragraph["text"],
                    split_paragraphs_words[current_paragraph_index]["text"][
                        current_sentence_index
                    ][: min(current_overlap, overlap_sentence_length)],
                ]
                current_overlap -= overlap_sentence_length
                current_paragraph["page"].extend(
                    split_paragraphs_words[current_paragraph_index]["page"]
                )
                current_sentence_index += 1

        overlapped_paragraphs.append(
            {**current_paragraph, "page": list(set(current_paragraph["page"]))}
        )

    # Recombine sentences
    overlapped_paragraphs = [
        {
            **paragraph,
            "text": [" ".join(sentence).strip(" ") for sentence in paragraph["text"]],
        }
        for paragraph in overlapped_paragraphs
    ]

    # Trim loose ends
    def detect_loose_end(sentence: str, start: bool) -> bool:
        if not sentence:
            return False
        if start and sentence[0].islower():
            return False
        if not start:
            return is_paragraph_complete(sentence)
        return True

    if trim_loose_ends:
        overlapped_paragraphs = [
            {
                **paragraph,
                "text": [
                    " ".join(
                        [
                            sentence
                            for index, sentence in enumerate(paragraph["text"])
                            if index > 0
                            and index < len(paragraph) - 1
                            or detect_loose_end(sentence.strip(), index == 0)
                        ]
                    ).strip()
                ],
            }
            for paragraph in overlapped_paragraphs
        ]

    # Comine chunks
    overlapped_paragraphs = [
        {
            **paragraph,
            "text": " ".join(paragraph["text"]).strip(),
        }
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
