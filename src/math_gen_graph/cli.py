"""Typer CLI entry point for math-gen-graph."""

from __future__ import annotations

import asyncio
import sys
from typing import Annotated, Optional

import typer
from rich.console import Console

from .cache import EnrichmentCache
from .client import fetch_graph
from .enrichment import enrich_graph
from .graph import build_digraph
from .models import (
    ColorBy,
    EnrichedData,
    LayoutEngine,
    OutputFormat,
    StartNodeArg,
    ThemeName,
)
from .renderers.interactive import render_interactive
from .renderers.static import render_static
from .themes import get_theme

app = typer.Typer(
    name="math-gen-graph",
    help=(
        "Build beautiful visualizations of mathematician advisor-advisee "
        "genealogies from the Mathematics Genealogy Project."
    ),
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def _parse_start_node(value: str) -> StartNodeArg:
    """Parse a start node argument like '18231:a'."""
    try:
        return StartNodeArg.from_string(value)
    except ValueError as e:
        raise typer.BadParameter(str(e))


def _default_output_path(fmt: OutputFormat) -> str:
    """Generate a default output filename based on format."""
    ext_map = {
        OutputFormat.HTML: "genealogy.html",
        OutputFormat.PNG: "genealogy.png",
        OutputFormat.SVG: "genealogy.svg",
    }
    return ext_map[fmt]


@app.command()
def main(
    ids: Annotated[
        list[str],
        typer.Argument(
            help=(
                "Mathematician record IDs with traversal direction. "
                "Format: ID:DIRECTION where DIRECTION is 'a' (advisors), "
                "'d' (descendants), or 'ad' (both). "
                "Example: 18231:a"
            ),
        ),
    ],
    format: Annotated[
        OutputFormat,
        typer.Option(
            "--format", "-f",
            help="Output format.",
        ),
    ] = OutputFormat.HTML,
    theme: Annotated[
        ThemeName,
        typer.Option(
            "--theme", "-t",
            help="Visual theme.",
        ),
    ] = ThemeName.LIGHT,
    color_by: Annotated[
        ColorBy,
        typer.Option(
            "--color-by", "-c",
            help="How to color-code nodes.",
        ),
    ] = ColorBy.INSTITUTION,
    layout: Annotated[
        LayoutEngine,
        typer.Option(
            "--layout", "-l",
            help="Graph layout algorithm.",
        ),
    ] = LayoutEngine.HIERARCHICAL,
    output: Annotated[
        Optional[str],
        typer.Option(
            "--output", "-o",
            help="Output file path. Defaults to 'genealogy.{format}'.",
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet", "-q",
            help="Suppress progress display.",
        ),
    ] = False,
    no_enrich: Annotated[
        bool,
        typer.Option(
            "--no-enrich",
            help="Skip Wikidata enrichment (Wikipedia links, flags).",
        ),
    ] = False,
    clear_cache: Annotated[
        bool,
        typer.Option(
            "--clear-cache",
            help="Clear the enrichment cache before running.",
        ),
    ] = False,
) -> None:
    """Fetch and visualize a math genealogy graph."""
    # Parse start nodes
    start_nodes: list[StartNodeArg] = []
    for id_str in ids:
        start_nodes.append(_parse_start_node(id_str))

    if not start_nodes:
        console.print("[red]Error:[/red] At least one start node ID is required.")
        raise typer.Exit(1)

    # Handle cache clearing
    if clear_cache:
        EnrichmentCache.clear()
        if not quiet:
            console.print("[yellow]Enrichment cache cleared.[/yellow]")

    # Determine output path
    output_path = output or _default_output_path(format)

    # Fetch data
    if not quiet:
        console.print(
            f"[bold]Fetching genealogy data for "
            f"{len(start_nodes)} starting node(s)...[/bold]"
        )

    try:
        geneagraph = asyncio.run(fetch_graph(start_nodes, quiet=quiet))
    except ConnectionError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not quiet:
        console.print(
            f"[green]Received {len(geneagraph.nodes)} records[/green] "
            f"(status: {geneagraph.status})"
        )

    # Enrich with Wikidata (Wikipedia links + flags)
    enriched = EnrichedData()
    if not no_enrich:
        if not quiet:
            console.print("[bold]Enriching with Wikidata (Wikipedia links, flags)...[/bold]")
        try:
            enriched = asyncio.run(enrich_graph(geneagraph))
            if not quiet:
                wiki_count = sum(
                    1 for p in enriched.people.values() if p.wikipedia_url
                )
                flag_count = sum(
                    1 for i in enriched.institutions.values() if i.flag_url
                )
                console.print(
                    f"[green]Enriched:[/green] {wiki_count} Wikipedia links, "
                    f"{flag_count} institution flags"
                )
        except Exception as e:
            if not quiet:
                console.print(
                    f"[yellow]Enrichment failed (graph will render without it):[/yellow] {e}"
                )

    # Build NetworkX graph
    G = build_digraph(geneagraph)

    # Get theme config
    theme_config = get_theme(theme)

    # Build a title from start node names
    start_names = [
        geneagraph.nodes[sn.record_id].name
        for sn in start_nodes
        if sn.record_id in geneagraph.nodes
    ]
    title = " & ".join(start_names) if start_names else "Math Genealogy"

    # Render
    if not quiet:
        console.print(
            f"[bold]Rendering {format.value.upper()} "
            f"with [cyan]{theme.value}[/cyan] theme...[/bold]"
        )

    try:
        if format == OutputFormat.HTML:
            result_path = render_interactive(
                G=G,
                theme=theme_config,
                color_by=color_by,
                layout=layout,
                output_path=output_path,
                title=title,
                start_node_ids=[sn.record_id for sn in start_nodes],
                enriched=enriched,
            )
        else:
            result_path = render_static(
                G=G,
                theme=theme_config,
                color_by=color_by,
                layout=layout,
                output_format=format,
                output_path=output_path,
                title=title,
                enriched=enriched,
            )
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold green]Done![/bold green] Output written to [cyan]{result_path}[/cyan]")


if __name__ == "__main__":
    app()
