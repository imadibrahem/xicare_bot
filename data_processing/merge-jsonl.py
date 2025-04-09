import click


@click.command()
@click.argument("jsonl_files", type=click.Path(exists=True, dir_okay=False), nargs=-1)
@click.option(
    "--output",
    type=click.Path(dir_okay=False),
    default="merged.json",
    help="Output file name for the merged JSONL",
)
def merge_jsonl(jsonl_files, output):
    """Merge multiple JSONL files into a single JSONL file."""
    with open(output, "w", encoding="utf-8") as outfile:
        for jsonl_file in jsonl_files:
            with open(jsonl_file, "r", encoding="utf-8") as infile:
                for line in infile:
                    outfile.write(line)

    click.echo(f"Merged {len(jsonl_files)} files into {output}.")


if __name__ == "__main__":
    merge_jsonl()
