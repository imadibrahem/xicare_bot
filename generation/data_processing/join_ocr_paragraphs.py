from typing import Optional
import re
import click


def join_paragraphs(input_text):
    """
    Join paragraph breaks where the next line doesn't start with a capital letter or #.
    This helps fix OCR text where paragraphs were incorrectly split.

    Args:
        input_text (str): The text to process

    Returns:
        str: The processed text with appropriate paragraph breaks joined
    """
    pattern = r"\n\n([^A-Z#])"
    # Replace newlines with a single space followed by the character that was matched
    return re.sub(pattern, r" \1", input_text)


# fmt: off
@click.command(help="Join incorrectly split paragraphs in OCR text files.")
@click.argument('input_file', type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option('-o', '--output', help='Path to the output file. If not specified, output is printed to stdout.')
# fmt: on
def process_file(input_file: str, output: Optional[str]):
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            content = f.read()

        processed_content = join_paragraphs(content)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(processed_content)
            click.echo(f"Processed text saved to: {output}")
        else:
            click.echo(processed_content)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit


if __name__ == "__main__":
    process_file()
