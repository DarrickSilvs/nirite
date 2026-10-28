import json
from pathlib import Path, PurePath, PureWindowsPath
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from nirite.ingestion.normalizer import normalise_file

app = typer.Typer()
console = Console()

def get_filename(path_string):
    path = PurePath(path_string)
    
    # If it didn't split backslashes (e.g., a Windows path parsed on Linux)
    if '\\' in path.name and not '/' in path_string:
        path = PureWindowsPath(path_string)
        
    return path.name

@app.command()
def ingest(
    input_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
    ),
    output_path: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to save the processed JSON file."
    ),
    mapping_path: Optional[Path] = typer.Option(
        None,
        "--mapping",
        "-m",
    )
):
    if output_path is None:
        output_path = Path(f"data/processed/{get_filename(input_path.stem)}.json")
    
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