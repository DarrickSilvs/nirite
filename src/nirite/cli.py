import json
from pathlib import Path, PurePath, PureWindowsPath
from typing import Optional, Sequence
from openai import OpenAIError

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from nirite.campaign.llm.providers import build_analysis_providers, build_parser_provider
from nirite.ingestion.normalizer import normalise_file
from nirite.ingestion.company_normalizer import normalise_company_file
from nirite.models.prospect import Prospect
from nirite.models.company import CompanyProspect

from nirite.campaign.analyser import CampaignAnalyser
from nirite.campaign.parser import CampaignParser
from nirite.retrieval.pipeline import run
from nirite.retrieval.models import RetrievalOutput
from nirite.models.campaign import CampaignDefinition

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

def save_prospects(
    prospects: Sequence[Prospect | CompanyProspect], destination: Path
) -> None:
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
        help="Path to save the processed JSON file.",
    ),
    kind: str = typer.Option(
        "individual",
        "--kind",
        "-k",
        help="Prospect kind to ingest: individual or company.",
    ),
):
    if output_path is None:
        output_path = Path(f"data/processed/{get_filename(input_path.stem)}.json")

    kind_normalized = kind.strip().lower()
    if kind_normalized == "individual":
        prospects = normalise_file(input_path)
    elif kind_normalized == "company":
        prospects = normalise_company_file(input_path)
    else:
        console.print(
            f"[red]Error:[/red] unknown kind '{kind}'. Use 'individual' or 'company'."
        )
        raise typer.Exit(code=1)

    save_prospects(prospects, output_path)

    table = Table(title="Nirite Import Summary")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Input", input_path.name)
    table.add_row("Records", str(len(prospects)))
    table.add_row("Output", str(output_path))

    console.print(table)

def _display_available_fields(console: Console, available_fields: list) -> None:
    console.print("\n[bold]Available fields[/bold]")
    for index, (_, _, label) in enumerate(available_fields, start=1):
        console.print(f"{index}. {label}")


def _display_actions_menu(console: Console) -> None:
    console.print("\n[bold]Actions[/bold]")
    console.print("1. Reassign or swap fields")
    console.print("2. Delete an extra field")
    console.print("0. Finish")


def _handle_reassign_action(
    console: Console,
    prospects: list,
    available_fields: list,
    destination,
) -> None:
    source_index = typer.prompt("Select source field number", type=int)
    if not 1 <= source_index <= len(available_fields):
        console.print("[red]Invalid field number.[/red]")
        return

    target_index = typer.prompt("Select destination field number", type=int)

    if target_index < 1:
        console.print("[red]Invalid field number.[/red]")
        return
    elif target_index > len(available_fields):
        if not typer.confirm("Create a new extra field and move it there?"):
            return
        target_label = typer.prompt("Name the new field", type=str).lower().strip()
        if not target_label:
            console.print("[red]Field name cannot be empty.[/red]")
            return
        target_kind = "extra"
        target_key = target_label
    else:
        target_kind, target_key, target_label = available_fields[target_index - 1]

    source_kind, source_key, source_label = available_fields[source_index - 1]

    try:
        reassign_field(
            prospects,
            source_kind,
            source_key,
            target_kind,
            target_key,
        )
        console.print(f"Reassigned '{source_label}' and '{target_label}'.")
        save_prospects(prospects, destination)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")


def _handle_delete_extra_action(
    console: Console,
    prospects: list,
    extra_fields: list,
    destination,
) -> None:
    if not extra_fields:
        console.print("No extra fields available.")
        return

    console.print("\n[bold]Extra fields[/bold]")
    for index, field in enumerate(extra_fields, start=1):
        console.print(f"{index}. {field}")

    field_index = typer.prompt("Select extra field number", type=int)
    if not 1 <= field_index <= len(extra_fields):
        console.print("[red]Invalid field number.[/red]")
        return

    field_name = extra_fields[field_index - 1]

    if typer.confirm(f"Delete '{field_name}' from all records?"):
        delete_extra_field(prospects, field_name)
        save_prospects(prospects, destination)
        console.print(f"Deleted '{field_name}'.")


# Company-only canonical fields (present in CompanyProspect but not Prospect).
# Pydantic ignores unknown fields, so an individual record also validates as
# CompanyProspect; field presence is what tells the two record types apart.
_COMPANY_ONLY_FIELDS = frozenset(
    set(CompanyProspect.model_fields) - set(Prospect.model_fields)
)


def _detect_prospect_model_class(
    records: list[dict],
) -> type[Prospect] | type[CompanyProspect]:
    """Detect whether loaded records are companies or individuals.

    Company records carry company-only fields (industry, company_size,
    region, linkedin_url, description); individual records do not. Falls back
    to Prospect for empty or ambiguous input, so existing Prospect behaviour
    is unchanged.
    """
    if not records:
        return Prospect
    if any(field in records[0] for field in _COMPANY_ONLY_FIELDS):
        return CompanyProspect
    return Prospect


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
        help="Path to save the updated JSON.",
    ),
):
    try:
        records = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        console.print(f"[red]Error loading input:[/red] {e}")
        raise typer.Exit(code=1) from e

    model_class = _detect_prospect_model_class(records)

    try:
        prospects: list[Prospect | CompanyProspect] = [
            model_class.model_validate(record)
            for record in records
        ]
    except ValueError as e:
        console.print(f"[red]Error loading input:[/red] {e}")
        raise typer.Exit(code=1) from e

    destination = output_path or input_path

    while True:
        available_fields = get_all_fields(prospects)
        extra_fields = get_extra_fields(prospects)

        _display_available_fields(console, available_fields)
        _display_actions_menu(console)

        action = typer.prompt("Choose an action", type=int)

        if action == 0:
            break
        elif action == 1:
            _handle_reassign_action(console, prospects, available_fields, destination)
        elif action == 2:
            _handle_delete_extra_action(console, prospects, extra_fields, destination)
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


@app.command()
def retrieve(
    prospects_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to ingested prospects JSON file (Layer 0 output).",
    ),
    campaign_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to campaign definition JSON file (Layer 1 output).",
    ),
    top_n: int = typer.Option(
        20,
        "--top-n",
        "-n",
        help="Maximum number of candidates to return.",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to save the results JSON file.",
    ),
):
    """Run Layer 2 retrieval: match ingested prospects against a campaign definition."""

    # Load prospects JSON
    try:
        prospects_data = json.loads(prospects_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        console.print(f"[red]Error loading prospects file:[/red] {e}")
        raise typer.Exit(code=1) from e

    # Load campaign JSON
    try:
        campaign_data = json.loads(campaign_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        console.print(f"[red]Error loading campaign file:[/red] {e}")
        raise typer.Exit(code=1) from e

    # Build Prospect objects
    prospects = []
    for record in prospects_data:
        try:
            prospects.append(Prospect.model_validate(record))
        except ValueError as e:
            console.print(
                f"[yellow]Warning:[/yellow] Skipping invalid prospect record: {e}"
            )

    if not prospects:
        console.print("[red]No valid prospects found in the input file.[/red]")
        raise typer.Exit(code=1)

    # Build CampaignDefinition
    try:
        campaign = CampaignDefinition.model_validate(campaign_data)
    except ValueError as e:
        console.print(f"[red]Invalid campaign definition:[/red] {e}")
        raise typer.Exit(code=1) from e

    # Run Layer 2 retrieval pipeline
    output = run(prospects, campaign, top_n=top_n)

    # Display summary table
    console.print(f"\n[bold cyan]Layer 2 Retrieval Results[/bold cyan]")
    console.print(f"Prospects scanned: {output.total_scanned}")
    console.print(f"Tier 1 passed: {output.tier1_passed}")
    console.print(f"Queries executed: {output.queries_executed}")
    console.print(f"Candidates returned: {len(output.candidates)}")

    if output.candidates:
        types = {candidate.prospect_type for candidate in output.candidates}
        show_company = "company" in types
        show_individual = "individual" in types

        results_table = Table(title="Qualified Prospects")
        results_table.add_column("Rank", style="cyan")
        if show_company:
            for header, style in (
                ("Company", "blue"),
                ("Industry", "blue"),
                ("Description", "blue"),
                ("Region", "blue"),
                ("LinkedIn", "blue"),
            ):
                results_table.add_column(header, style=style)
        if show_individual:
            for header, style in (
                ("Name", "green"),
                ("Company", "blue"),
                ("Role", "magenta"),
                ("Location", "yellow"),
            ):
                results_table.add_column(header, style=style)
        results_table.add_column("Score", style="red")
        results_table.add_column("Queries Found", style="white")

        for candidate in output.candidates:
            data = candidate.prospect_data
            if candidate.prospect_type == "company":
                values = [
                    data.get("company_name", "-"),
                    data.get("industry", "-"),
                    data.get("description", "-"),
                    data.get("region", "-"),
                    data.get("linkedin_url", "-"),
                ]
                if show_individual:
                    values.extend(["-"] * 4)
            else:
                values = ["-"] * (5 if show_company else 0)
                values.extend(
                    [
                        data.get("full_name", "-"),
                        data.get("company_name", "-"),
                        data.get("job_title", "-"),
                        f'{data.get("city", "-")}, {data.get("country", "-")}',
                    ]
                )
            results_table.add_row(
                str(candidate.rank),
                *values,
                f"{candidate.final_score:.4f}",
                ", ".join(candidate.queries_found),
            )

        console.print(results_table)

    # Optional JSON persistence
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            output.model_dump_json(indent=2),
            encoding="utf-8",
        )
        console.print(f"\n[green]Saved results to {output_path}[/green]")


if __name__ == "__main__":
    app()