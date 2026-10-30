import json
from pathlib import Path, PurePath, PureWindowsPath
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from nirite.ingestion.normalizer import normalise_file
from nirite.models.prospect import Prospect
from nirite.ingestion.reassignment import (
    delete_extra_field,
    get_all_fields,
    get_extra_fields,
    reassign_field,
)

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

@app.command()
def map(
    input_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to save the updated JSON."
    ),
):
    try:
        records = json.loads(input_path.read_text(encoding="utf-8"))
        prospects = [
            Prospect.model_validate(record)
            for record in records
        ]
    except (OSError, json.JSONDecodeError, ValueError) as e:
        console.print(f"[red]Error loading input:[/red] {e}")
        raise typer.Exit(code=1) from e

    while True:
        available_fields = get_all_fields(prospects)
        extra_fields = get_extra_fields(prospects)

        console.print("\n[bold]Available fields[/bold]")
        for index, (_, _, label) in enumerate(
            available_fields, start=1
        ):
            console.print(f"{index}. {label}")

        console.print("\n[bold]Actions[/bold]")
        console.print("1. Reassign or swap fields")
        console.print("2. Delete an extra field")
        console.print("0. Finish")

        action = typer.prompt("Choose an action", type=int)

        if action == 0:
            break

        if action == 1:
            source_index = typer.prompt(
                "Select source field number", type=int
            )

            if not 1 <= source_index <= len(available_fields):
                console.print("[red]Invalid field number.[/red]")
                continue

            target_index = typer.prompt(
                "Select destination field number", type=int
            )
            
            if target_index < 1:
                console.print("[red]Invalid field number.[/red]")
                continue
            elif target_index > len(available_fields):
                if typer.confirm(
                    "Create a new extra field and move it there?"
                ):
                    target_label = typer.prompt(
                        "Name the new field", type=str
                    )

                    target_kind = "extra"
                    target_label = target_label.lower().strip()
                    target_key = target_label
            else:
                target_kind, target_key, target_label = (
                    available_fields[target_index - 1]
                )

            source_kind, source_key, source_label = (
                available_fields[source_index - 1]
            )

            try:
                reassign_field(
                    prospects,
                    source_kind,
                    source_key,
                    target_kind,
                    target_key
                )
                console.print(
                    f"Reassigned '{source_label}' and '{target_label}'."
                )
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")

        elif action == 2:
            if not extra_fields:
                console.print("No extra fields available.")
                continue

            console.print("\n[bold]Extra fields[/bold]")
            for index, field in enumerate(extra_fields, start=1):
                console.print(f"{index}. {field}")

            field_index = typer.prompt(
                "Select extra field number", type=int
            )

            if not 1 <= field_index <= len(extra_fields):
                console.print("[red]Invalid field number.[/red]")
                continue

            field_name = extra_fields[field_index - 1]

            if typer.confirm(
                f"Delete '{field_name}' from all records?"
            ):
                delete_extra_field(prospects, field_name)
                console.print(f"Deleted '{field_name}'.")

        else:
            console.print("[red]Invalid action number.[/red]")

    destination = output_path or input_path

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                [
                    prospect.model_dump(mode="json")
                    for prospect in prospects
                ],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        console.print(f"[red]Error saving output:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"Saved updated records to {destination}")

if __name__ == "__main__":
    app()