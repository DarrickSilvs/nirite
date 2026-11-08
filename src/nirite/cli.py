from copy import error
import json
from pathlib import Path, PurePath, PureWindowsPath
from typing import Optional
from openai import OpenAIError

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from nirite.campaign.llm.providers import build_analysis_providers, build_parser_provider
from nirite.ingestion.normalizer import normalise_file
from nirite.models.prospect import Prospect

from nirite.campaign.analyser import CampaignAnalyser
from nirite.campaign.parser import CampaignParser

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

    return path

def save_prospects(prospects: list[Prospect], destination: Path) -> None:
    """Write prospects atomically so a crash cannot leave a half-written file."""
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_name(destination.name + ".tmp")
        tmp.write_text(
            json.dumps(
                [p.model_dump(mode="json") for p in prospects],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        tmp.replace(destination)
    except OSError as exc:
        console.print(f"[red]Error saving output:[/red] {exc}")
        raise typer.Exit(code=1) from exc


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

    destination = output_path or input_path

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
                if not typer.confirm(
                    "Create a new extra field and move it there?"
                ):
                    continue

                target_label = typer.prompt(
                    "Name the new field", type=str
                ).lower().strip()

                if not target_label:
                    console.print("[red]Field name cannot be empty.[/red]")
                    continue

                target_kind = "extra"
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
                save_prospects(prospects, destination)
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
                save_prospects(prospects, destination)
                console.print(f"Deleted '{field_name}'.")

        else:
            console.print("[red]Invalid action number.[/red]")

    save_prospects(prospects, destination)
    console.print(f"Saved updated records to {destination}")

@app.command()
def campaign(
    prompt: str = typer.Argument(
        ...,
        help="Natural language campaign description"
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to save the campaign definition JSON file."
    ),
):
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            # Pass 1: Campaign Analysis
            task = progress.add_task(
                description="Analysing campaign with lightweight models...",
                total=None
            )

            analyser = CampaignAnalyser(
                providers=build_analysis_providers()
            )

            try:
                analyses = analyser.analyse(prompt)

                progress.update(
                    task,
                    description="[green]Campaign analysis complete!"
                )

                # Pass 2: Campaign Parsing
                progress.update(
                    task,
                    description="[bold cyan]Generating campaign definition...",
                )

                parser = CampaignParser(
                    providers=build_parser_provider()
                )

                result = parser.parse(prompt, analyses)
                progress.update(
                    task, 
                    description="[green]Campaign parsing complete!"
                )
            except RuntimeError as e:
                console.print(f"[red]{e}[/red]")
                raise typer.Exit(code=1)
    except (RuntimeError, ValueError, OpenAIError) as e:
        console.print(f"[red]Campaign processing failed:[/red] {e}")
        raise typer.Exit(code=1) from e

     # Campaign summary
    console.print("\n[bold cyan]Campaign Summary[/bold cyan]")
    console.print(f"Status: {result.status.value}")
    console.print(f"Target: {result.spec.target_type.value}")
    console.print(f"Objective: {result.spec.objective}")
    console.print(f"Description: {result.spec.target_description}")

    # Criteria
    criteria_table = Table(title="Campaign Criteria")
    criteria_table.add_column("ID")
    criteria_table.add_column("Kind")
    criteria_table.add_column("Mode")
    criteria_table.add_column("Description")
    criteria_table.add_column("Predicate")

    for criterion in result.spec.criteria:
        predicate = (
            criterion.predicate.model_dump_json()
            if criterion.predicate
            else "-"
        )

        criteria_table.add_row(
            criterion.id,
            criterion.kind.value,
            criterion.evaluation_mode.value,
            criterion.description,
            predicate,
        )

    console.print(criteria_table)

    # Search queries
    query_table = Table(title="Generated Search Queries")
    query_table.add_column("ID")
    query_table.add_column("Facet")
    query_table.add_column("Query")
    query_table.add_column("Rationale")

    for query in result.query_plan.queries:
        query_table.add_row(
            query.id,
            query.facet.value,
            query.query,
            query.rationale,
        )

    console.print(query_table)

    # Clarifications
    if result.clarifications:
        console.print("\n[bold yellow]Clarification Questions[/bold yellow]")

        for index, clarification in enumerate(
            result.clarifications, start=1
        ):
            console.print(
                f"{index}. {clarification.question}"
            )
            console.print(
                f"   Reason: {clarification.reason}"
            )

    # Optional JSON persistence
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )

        console.print(
            f"\n[green]Saved campaign to {output_path}[/green]"
        )

if __name__ == "__main__":
    app()