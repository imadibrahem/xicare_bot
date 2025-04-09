import click
import json


@click.command()
@click.argument("json_files", type=click.Path(exists=True, dir_okay=False), nargs=-1)
@click.option(
    "--output",
    type=click.Path(dir_okay=False),
    default="merged.json",
    help="Output file name for the merged JSON",
)
def merge_jsonl(json_files, output):
    """
    Merge multiple JSON files into a single JSON file.
    """

    data = []
    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as infile:
            data.extend(json.load(infile))

    with open(output, "w", encoding="utf-8") as outfile:
        json.dump(data, outfile, ensure_ascii=False)

    click.echo(
        click.style(
            f"Merged {len(json_files)} files into {output}.",
            fg="green",
        )
    )


if __name__ == "__main__":
    merge_jsonl()
