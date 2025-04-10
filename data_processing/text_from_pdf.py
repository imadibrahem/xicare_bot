from typing import Optional
import click
import os
import pypdf
from tqdm import tqdm


# fmt: off
@click.command()
@click.option('--output', '-o', type=click.Path(dir_okay=False), required=True, help="Output file to save the extracted text")
@click.argument('pdf_path', type=click.Path(dir_okay=False, exists=True))
# fmt: on
def extract_text_from_pdf(
    output: Optional[str],
    pdf_path: str,
) -> None:
    """
    Extract embedded text from a PDF file using only PyPDF.
    """

    click.echo(f"Processing PDF: {pdf_path}")

    full_text = ""

    try:
        with open(pdf_path, "rb") as file:
            reader = pypdf.PdfReader(file)
            num_pages = len(reader.pages)

            click.echo(f"Extracting text from {num_pages} pages...")

            for page_num in tqdm(range(num_pages)):
                page = reader.pages[page_num]
                page_text = page.extract_text() or ""
                full_text += f"\n\n{page_text}"

    except Exception as e:
        click.echo(click.style(f"Error processing PDF: {e}", fg="red"))
        return ""

    # Save to file
    click.echo(f"Saving text to {output}")

    if os.path.dirname(output):
        os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(full_text)

    click.echo(click.style("Text extraction complete.", fg="green"))


if __name__ == "__main__":
    extract_text_from_pdf()
