import click
from dotenv import dotenv_values
from google import genai
from google.genai import types
from pathlib import Path
import re

# Load environment variables from .env file
config = dotenv_values(".env")


# fmt: off
@click.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--model", "-m", default="gemini-2.0-flash-001", help="LLM model to use")
@click.option("--output-file", "-o", type=click.Path(), help="Output file path (defaults to input_file with _corrected suffix)")
@click.option("--input-price", "-ip", default=0.15, type=float, help="Price for 1M input text tokens in US$")
@click.option("--output-price", "-op", default=0.60, type=float, help="Price for 1M output text tokens in US$")
# fmt: on
def correct_ocr(
    input_file: str,
    model: str,
    output_file: str,
    input_price: float,
    output_price: float,
):
    """Correct OCR errors in a markdown file using Google's Gemini models."""

    # Set default output file if not provided
    if not output_file:
        input_path = Path(input_file)
        output_file = str(input_path.with_stem(f"{input_path.stem}_corrected"))

    click.echo(f"Processing {input_file}...")

    # Initialize Google AI client
    client = genai.Client(
        vertexai=True, project=config["PROJECT_ID"], location=config["LOCATION"]
    )

    system_prompt = """
You are a text corrector who fixes errors that occurred during OCR. You will get text chunks of markdown and respond with the corrected versions, keeping the markdown formatting intact.

Most common errors are:
- Words that have become split (e.g., \"dis­ tribution\", which you will fix to \"distribution\")
- Issues that result from difficult-to-read kerning, which most commonly occurs as \"rn\" having been read as \"nn\" by OCR (e.g., \"fonn\", which you will correct to \"form\") or whole words being split by each letter (e.g., \"N o te\", which you will correct to \"Note\")
- Characters like \"l\" or \"i\" that sometimes got misread by the OCR as \"!\" (e.g., \"G!bbs\", which you will correct to \"Gibbs\")
- Charactlers like \"l\" that got misread as \"i\" (e.g., \"guii\", which you will correct to \"Gull\")
- Characters like \"-\" that got misinterpreted as * (or \\* in markdown notation)
- Character groups like \"fi\" that got misinterpreted as \"£\"
- Incorrect spacing between quotation marks and text (e.g., \"' thickness '\", which you will correct to \"'thickness'\")
- Weird characters like e.g. \"·\" are left between words, because of marks on the page that were scanned and interpreted as writing
"""

    generate_content_config = types.GenerateContentConfig(
        temperature=1,
        top_p=0.95,
        max_output_tokens=8192,
        response_modalities=["TEXT"],
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(
                category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"
            ),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
        ],
        system_instruction=[types.Part.from_text(text=system_prompt)],
    )

    # Read the input markdown file
    with open(input_file, "r", encoding="utf-8") as f:
        text = f.read()

    # Split text into paragraphs (split by double newlines)
    paragraphs = text.split("\n\n")
    corrected_paragraphs = []

    # Count system prompt tokens
    # Create content for the request
    contents = [
        types.Content(role="system", parts=[types.Part.from_text(text=system_prompt)])
    ]

    # Call the API to count the system prompt tokens
    system_prompt_tokens = 0
    errors_recorded = False
    try:
        response = client.models.count_tokens(
            model=model,
            contents=contents,
        )
        system_prompt_tokens = response.total_tokens
    except Exception as e:
        click.echo(f"Error counting tokens system prompt: {e}")
        errors_recorded = True

    with click.progressbar(paragraphs, label="Counting tokens") as bar:
        input_token_count = 0
        output_token_count = 0
        last_token_count = 0
        for paragraph in bar:
            # Skip empty paragraphs
            if not paragraph.strip():
                corrected_paragraphs.append(paragraph)
                continue

            # Create content for the request
            contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=paragraph)])
            ]

            # Call the API to count the paragraph tokens
            try:
                response = client.models.count_tokens(
                    model=model,
                    contents=contents,
                )
                last_token_count = response.total_tokens
            except Exception as e:
                click.echo(f"Error counting tokens paragraph: {e}")
                errors_recorded = True

            input_token_count += (
                system_prompt_tokens + last_token_count
            )  # Add previous on failure
            output_token_count += last_token_count

    estimated_cost = (
        input_token_count / 1_000_000 * input_price
        + output_token_count / 1_000_000 * output_price
    )
    click.echo(
        f"Estimated cost: ${estimated_cost:.2f}"
        + (
            ". Not exactly accurate, since errors were recorded during counting"
            if errors_recorded
            else ""
        )
    )
    input("Press Enter to continue...")

    with click.progressbar(paragraphs, label="Correcting paragraphs") as bar:
        for paragraph in bar:
            # Skip empty paragraphs
            if not paragraph.strip():
                corrected_paragraphs.append(paragraph)
                continue

            # Create content for the request
            contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=paragraph)])
            ]

            # Call the API to correct the paragraph
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=generate_content_config,
                )
                corrected_paragraphs.append(response.text)
            except Exception as e:
                click.echo(f"Error processing paragraph: {e}")
                corrected_paragraphs.append(paragraph)  # Use original on failure

    # Join the corrected paragraphs back together
    corrected_text = "\n\n".join(corrected_paragraphs)

    # remove excess newlines
    corrected_text = re.sub(r"\n{3,}", "\n\n", corrected_text)

    # Save the result to the output file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(corrected_text)

    click.echo(f"Corrected text saved to {output_file}")


if __name__ == "__main__":
    correct_ocr()
