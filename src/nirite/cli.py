import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from nirite.ingestion.normalizer import normalise_file

app = typer.Typer()
console = Console()

@app.command()
def ingest(
    input_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
    ),
    output_path: Path = typer.Option(
        Path("data/processed/prospects.json"),
        "--output",
        "-o",
    ),
):
    prospects = normalise_file(input_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            [p.model_dump(mode="json") for p in prospects],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    table = Table(title="Nirite Import Summary")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Input", input_path.name)
    table.add_row("Records", str(len(prospects)))
    table.add_row("Output", str(output_path))

    console.print(table)

if __name__ == "__main__":
    app()