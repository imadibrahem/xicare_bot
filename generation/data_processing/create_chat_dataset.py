import click
import json
import re


# fmt: off
@click.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.argument("output_file", type=click.Path(dir_okay=False))
@click.option("--user-prefix", default="Q:", help="Prefix for user messages in the input file")
@click.option("--model-prefix", default="A:", help="Prefix for model messages in the input file")
@click.option("--pairs-per-object", default=1, type=int, help="Number of Q&A pairs per JSONL object")
# fmt: on
def convert_to_jsonl(
    input_file, output_file, user_prefix, model_prefix, pairs_per_object
):
    """
    Convert a text file with Q&A format into a JSONL file for chat models.

    The input file should contain questions and answers in the format:
    Q: Some question.

    A: Some answer.

    The output will be a JSONL file with each line containing a JSON object.
    """
    # Read the input file
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Create a pattern that matches user/model pairs
    pattern = rf"{re.escape(user_prefix)}\s*(.*?)[\n\s]*{re.escape(model_prefix)}\s*(.*?)(?=[\n\s]*{re.escape(user_prefix)}|\Z)"

    # Find all matches in the content
    pairs = re.findall(pattern, content, re.DOTALL)

    # Write pairs to JSONL format
    with open(output_file, "w", encoding="utf-8") as out:
        for i in range(0, len(pairs), pairs_per_object):
            batch = pairs[i : i + pairs_per_object]
            messages = []

            for user_content, model_content in batch:
                messages.append({"role": "user", "content": user_content.strip()})
                messages.append({"role": "model", "content": model_content.strip()})

            json_obj = {"messages": messages}
            out.write(json.dumps(json_obj, ensure_ascii=False) + "\n")

    click.echo(f"Conversion complete: {len(pairs)} Q&A pairs processed")
    click.echo(f"Output written to {output_file}")


if __name__ == "__main__":
    convert_to_jsonl()
