"""Static image renderer using the Graphviz Python bindings."""

from __future__ import annotations

from pathlib import Path

import graphviz
import networkx as nx

from ..graph import assign_colors, compute_node_sizes
from ..models import ColorBy, EnrichedData, LayoutEngine, OutputFormat, ThemeConfig


def _graphviz_engine(layout: LayoutEngine) -> str:
    """Map our layout enum to a Graphviz engine name."""
    mapping = {
        LayoutEngine.HIERARCHICAL: "dot",
        LayoutEngine.FORCE: "neato",
        LayoutEngine.RADIAL: "twopi",
    }
    return mapping.get(layout, "dot")


def _output_format_str(fmt: OutputFormat) -> str:
    """Map our output format to a Graphviz format string."""
    if fmt == OutputFormat.SVG:
        return "svg"
    return "png"


def _contrast_text_color(hex_bg: str) -> str:
    """Choose black or white text based on background color luminance."""
    bg = hex_bg.lstrip("#")
    if len(bg) < 6:
        return "#000000"
    r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#ffffff" if luminance < 140 else "#000000"


def _make_node_html_label(
    name: str,
    institution: str | None,
    year: int | None,
    font_family: str,
    text_color: str,
    flag_url: str | None = None,
    wiki_url: str | None = None,
    output_svg: bool = False,
) -> str:
    """Build an HTML-like label for a Graphviz node with styled name and subtitle.

    For SVG output, flag images and Wikipedia hyperlinks are embedded.
    """
    lines = [
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="2">',
    ]

    # Name row -- with optional hyperlink for SVG
    name_html = f"<B>{_escape_html(name)}</B>"
    lines.append(
        f'<TR><TD><FONT FACE="{font_family}" POINT-SIZE="12" COLOR="{text_color}">{name_html}</FONT></TD></TR>'
    )

    # Subtitle row: optional flag + institution + year
    sub_parts: list[str] = []
    if institution:
        sub_parts.append(_escape_html(institution))
    if year:
        sub_parts.append(f"({year})")
    if sub_parts:
        subtitle = " ".join(sub_parts)
        # Prepend flag image for SVG output
        flag_html = ""
        if flag_url and output_svg:
            flag_html = f'<IMG SRC="{flag_url}" SCALE="FALSE"/> '
        lines.append(
            f'<TR><TD>{flag_html}<FONT FACE="{font_family}" POINT-SIZE="9" COLOR="{text_color}80">{subtitle}</FONT></TD></TR>'
        )

    lines.append("</TABLE>>")
    return "\n".join(lines)


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Graphviz HTML labels."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_static(
    G: nx.DiGraph,
    theme: ThemeConfig,
    color_by: ColorBy,
    layout: LayoutEngine,
    output_format: OutputFormat,
    output_path: str,
    title: str = "Genealogy",
    dpi: int = 150,
    enriched: EnrichedData | None = None,
) -> str:
    """Render a static graph image (PNG or SVG) and write it to output_path.

    Args:
        G: The NetworkX digraph with node metadata.
        theme: The visual theme to apply.
        color_by: How to color-code nodes.
        layout: The layout algorithm to use.
        output_format: PNG or SVG.
        output_path: Where to write the image.
        title: Graph title (used as a label).
        dpi: Resolution for PNG output.
        enriched: Optional Wikidata enrichment data (Wikipedia links, flags).

    Returns:
        The absolute path to the written file.
    """
    if enriched is None:
        enriched = EnrichedData()
    node_colors, legend = assign_colors(G, color_by, theme.node_colors)
    node_sizes = compute_node_sizes(G, min_size=10, max_size=30)
    engine = _graphviz_engine(layout)
    fmt = _output_format_str(output_format)

    # Strip hex alpha from edge color (Graphviz doesn't support 8-char hex well)
    edge_color = theme.edge_color[:7] if len(theme.edge_color) > 7 else theme.edge_color

    dot = graphviz.Digraph(
        name="genealogy",
        engine=engine,
        format=fmt,
    )

    # Global graph attributes
    dot.attr(
        "graph",
        bgcolor=theme.bg_color,
        fontname=theme.font_family.split(",")[0].strip(),
        fontcolor=theme.font_color,
        fontsize=str(theme.font_size),
        label=f"  {title}  ",
        labelloc="t",
        labeljust="l",
        pad="0.5",
        ranksep="1.2",
        nodesep="0.6",
        dpi=str(dpi),
        splines="true" if layout == LayoutEngine.HIERARCHICAL else "curved",
        overlap="false",
    )

    # Global node defaults
    dot.attr(
        "node",
        shape="box",
        style="filled,rounded",
        fontname=theme.font_family.split(",")[0].strip(),
        fontsize="11",
        margin="0.15,0.08",
        penwidth=str(theme.node_border_width),
    )

    # Global edge defaults
    dot.attr(
        "edge",
        color=edge_color,
        penwidth="1.2",
        arrowsize="0.6",
        arrowhead="vee",
    )

    output_svg = output_format == OutputFormat.SVG

    # Add nodes
    for node_id, data in sorted(G.nodes(data=True), key=lambda x: x[0]):
        name = data.get("name", "Unknown")
        institution = data.get("institution")
        year = data.get("year")
        bg_color = node_colors.get(node_id, theme.node_colors[0])
        text_color = _contrast_text_color(bg_color)

        # Enrichment lookups
        flag_url = enriched.flag_url_for(institution, year) if institution else None
        wiki_url = enriched.wikipedia_url_for(name)

        label = _make_node_html_label(
            name,
            institution,
            year,
            theme.font_family.split(",")[0].strip(),
            text_color,
            flag_url=flag_url,
            wiki_url=wiki_url,
            output_svg=output_svg,
        )

        node_attrs: dict[str, str] = {
            "label": label,
            "fillcolor": bg_color,
            "color": theme.node_border_color[:7] if len(theme.node_border_color) > 7 else theme.node_border_color,
            "fontcolor": text_color,
        }

        # For SVG: add a hyperlink so clicking the node goes to Wikipedia
        if output_svg and wiki_url:
            node_attrs["URL"] = wiki_url
            node_attrs["target"] = "_blank"
            node_attrs["tooltip"] = f"{name} on Wikipedia"

        dot.node(str(node_id), **node_attrs)

    # Add edges
    for source, target in G.edges():
        dot.edge(str(source), str(target))

    # Render
    output = Path(output_path)
    # graphviz.render appends the format extension, so we strip it if present
    stem = str(output.with_suffix(""))

    try:
        dot.render(filename=stem, cleanup=True)
    except graphviz.backend.execute.ExecutableNotFound:
        raise RuntimeError(
            "Graphviz 'dot' executable not found. "
            "Static image rendering (PNG/SVG) requires the Graphviz system "
            "package to be installed.\n"
            "  - Windows: winget install graphviz   (or download from https://graphviz.org/download/)\n"
            "  - macOS:   brew install graphviz\n"
            "  - Linux:   sudo apt install graphviz\n\n"
            "For interactive HTML output (no Graphviz needed), use --format html"
        )

    # The output file will be at stem + "." + fmt
    rendered_path = Path(f"{stem}.{fmt}")
    # If the user-specified path has the extension, rename to match exactly
    if rendered_path != output and output.suffix:
        rendered_path.rename(output)
        return str(output.resolve())

    return str(rendered_path.resolve())
