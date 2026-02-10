"""Interactive HTML graph renderer using vis.js via Jinja2 templates."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
from jinja2 import Environment, FileSystemLoader

from ..graph import assign_colors, compute_generation, compute_node_sizes, compute_tree_membership
from ..models import ColorBy, EnrichedData, LayoutEngine, ThemeConfig

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _make_node_label(
    name: str,
    institution: str | None,
    year: int | None,
    flag_url: str | None = None,
) -> str:
    """Build a multi-line HTML label for a vis.js node."""
    parts = [f"<b>{name}</b>"]
    sub_parts: list[str] = []
    if institution:
        sub_parts.append(institution)
    if year:
        sub_parts.append(f"({year})")
    if sub_parts:
        parts.append(" ".join(sub_parts))
    return "\n".join(parts)


def _layout_name(layout: LayoutEngine) -> str:
    """Map our layout enum to the vis.js layout type string."""
    if layout == LayoutEngine.HIERARCHICAL:
        return "hierarchical"
    elif layout == LayoutEngine.FORCE:
        return "force"
    else:
        return "radial"


def _sidebar_colors(theme: ThemeConfig) -> tuple[str, str, str]:
    """Derive sidebar background, border, and search-box colors from theme."""
    bg = theme.bg_color.lstrip("#")
    r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)

    # Determine if theme is dark or light
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance < 128:
        # Dark theme: slightly lighter sidebar
        sidebar_bg = f"#{min(r+15, 255):02x}{min(g+15, 255):02x}{min(b+15, 255):02x}"
        sidebar_border = f"#{min(r+30, 255):02x}{min(g+30, 255):02x}{min(b+30, 255):02x}"
        search_bg = f"#{min(r+25, 255):02x}{min(g+25, 255):02x}{min(b+25, 255):02x}"
    else:
        # Light theme: slightly darker sidebar
        sidebar_bg = f"#{max(r-8, 0):02x}{max(g-8, 0):02x}{max(b-8, 0):02x}"
        sidebar_border = f"#{max(r-30, 0):02x}{max(g-30, 0):02x}{max(b-30, 0):02x}"
        search_bg = "#ffffff"

    return sidebar_bg, sidebar_border, search_bg


def render_interactive(
    G: nx.DiGraph,
    theme: ThemeConfig,
    color_by: ColorBy,
    layout: LayoutEngine,
    output_path: str,
    title: str = "Genealogy",
    start_node_ids: list[int] | None = None,
    enriched: EnrichedData | None = None,
) -> str:
    """Render an interactive HTML graph and write it to output_path.

    Args:
        G: The NetworkX digraph with node metadata.
        theme: The visual theme to apply.
        color_by: How to color-code nodes.
        layout: The layout algorithm to use.
        output_path: Where to write the HTML file.
        title: Title for the page header.
        start_node_ids: List of starting node IDs (for multi-tree separation).
        enriched: Optional Wikidata enrichment data (Wikipedia links, flags).

    Returns:
        The absolute path to the written file.
    """
    if enriched is None:
        enriched = EnrichedData()
    node_colors, legend = assign_colors(G, color_by, theme.node_colors)
    node_sizes = compute_node_sizes(G)
    node_generations = compute_generation(G)
    layout_type = _layout_name(layout)

    # Multi-tree membership (for combined graphs)
    start_ids = start_node_ids or []
    num_trees = len(start_ids)
    if num_trees > 1:
        tree_memberships = compute_tree_membership(G, start_ids)
    else:
        tree_memberships = {n: [0] for n in G.nodes()}

    max_depth = max(node_generations.values()) if node_generations else 0

    # Collect century boundaries from node years
    years = [data.get("year") for _, data in G.nodes(data=True) if data.get("year")]
    if years:
        min_year = min(years)
        max_year = max(years)
        # Generate century boundaries that fall within (or near) the data range
        first_century = (min_year // 100) * 100
        last_century = ((max_year // 100) + 1) * 100
        century_years = list(range(first_century, last_century + 1, 100))
    else:
        century_years = []

    # Build vis.js node objects
    vis_nodes = []
    for node_id, data in G.nodes(data=True):
        name = data.get("name", "Unknown")
        institution = data.get("institution", "Unknown")
        year = data.get("year")
        color = node_colors.get(node_id, theme.node_colors[0])

        # Enrichment lookups
        wiki_url = enriched.wikipedia_url_for(name)
        flag_url = enriched.flag_url_for(institution, year) if institution else None
        country = enriched.country_for(institution) if institution else None

        # Multi-tree: determine tree index
        # -1 = shared (belongs to 2+ trees), 0..N = exclusive to that tree
        trees = tree_memberships.get(node_id, [])
        if len(trees) == 1:
            tree_index = trees[0]
        elif len(trees) > 1:
            tree_index = -1  # shared ancestor
        else:
            tree_index = -1  # orphan, treat as shared

        # Shared ancestors get a highlighted border to stand out
        is_shared = tree_index == -1 and num_trees > 1
        border_color = theme.highlight_color if is_shared else theme.node_border_color
        border_width = theme.node_border_width + 1 if is_shared else theme.node_border_width

        vis_nodes.append(
            {
                "id": node_id,
                "label": _make_node_label(name, institution, year, flag_url),
                "color": {
                    "background": color,
                    "border": border_color,
                    "highlight": {
                        "background": color,
                        "border": theme.highlight_color,
                    },
                    "hover": {
                        "background": color,
                        "border": theme.highlight_color,
                    },
                },
                "borderWidth": border_width,
                "font": {
                    "color": theme.font_color,
                    "size": theme.font_size,
                },
                "size": node_sizes.get(node_id, 20),
                # Custom data for search, detail panel, and overlays
                "fullName": name,
                "institution": institution,
                "year": year,
                "numAdvisors": data.get("num_advisors", 0),
                "numDescendants": data.get("num_descendants", 0),
                "groupLabel": _get_group_label(node_id, G, color_by, legend, node_colors),
                "depth": node_generations.get(node_id, 0),
                "treeIndex": tree_index,
                "wikipediaUrl": wiki_url,
                "flagUrl": flag_url,
                "country": country,
            }
        )

    # Build vis.js edge objects
    vis_edges = []
    for source, target in G.edges():
        vis_edges.append(
            {
                "from": source,
                "to": target,
            }
        )

    # Color-by label for the legend header
    color_by_labels = {
        ColorBy.INSTITUTION: "By Institution",
        ColorBy.ERA: "By Era",
        ColorBy.DEPTH: "By Depth",
    }

    sidebar_bg, sidebar_border, search_bg = _sidebar_colors(theme)

    # Render template
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
    )
    template = env.get_template("interactive.html.j2")

    html = template.render(
        title=title,
        theme=theme,
        sidebar_bg=sidebar_bg,
        sidebar_border=sidebar_border,
        search_bg=search_bg,
        nodes_json=json.dumps(vis_nodes),
        edges_json=json.dumps(vis_edges),
        legend=legend,
        color_by_label=color_by_labels.get(color_by, "Color"),
        node_count=G.number_of_nodes(),
        edge_count=G.number_of_edges(),
        layout_type=layout_type,
        max_depth=max_depth,
        century_years_json=json.dumps(century_years),
        num_trees=num_trees,
    )

    output = Path(output_path)
    output.write_text(html, encoding="utf-8")
    return str(output.resolve())


def _get_group_label(
    node_id: int,
    G: nx.DiGraph,
    color_by: ColorBy,
    legend: dict[str, str],
    node_colors: dict[int, str],
) -> str:
    """Get the group label for a node (used for legend click highlighting)."""
    color = node_colors.get(node_id)
    for label, lcolor in legend.items():
        if lcolor == color:
            return label
    return "Other"
