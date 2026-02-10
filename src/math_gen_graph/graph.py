"""Build and analyze a NetworkX graph from Geneagraph data."""

from __future__ import annotations

from collections import Counter

import networkx as nx

from .models import ColorBy, Geneagraph, Record


def build_digraph(geneagraph: Geneagraph) -> nx.DiGraph:
    """Convert a Geneagraph into a NetworkX DiGraph with rich node metadata.

    Edges go from advisor -> advisee (parent -> child).

    Each node gets attributes:
        - name, institution, year (from Record)
        - num_advisors, num_descendants (degree info)
    """
    G = nx.DiGraph()

    for record in geneagraph.nodes.values():
        G.add_node(
            record.id,
            name=record.name,
            institution=record.institution or "Unknown",
            year=record.year,
            num_advisors=len(record.advisors),
            num_descendants=len(record.descendants),
        )

    # Add edges: advisor -> advisee
    for record in geneagraph.nodes.values():
        for advisor_id in record.advisors:
            if advisor_id in geneagraph.nodes:
                G.add_edge(advisor_id, record.id)

    return G


def compute_depth(G: nx.DiGraph) -> dict[int, int]:
    """Compute depth from root nodes (nodes with no incoming edges).

    Roots have depth 0. Each step along an edge increases depth by 1.
    For nodes reachable via multiple paths, the minimum depth is used.
    """
    roots = [n for n in G.nodes() if G.in_degree(n) == 0]
    depths: dict[int, int] = {}

    for root in roots:
        for node, depth in nx.single_source_shortest_path_length(G, root).items():
            if node not in depths or depth < depths[node]:
                depths[node] = depth

    # Assign depth to any remaining unreachable nodes
    for node in G.nodes():
        if node not in depths:
            depths[node] = 0

    return depths


def compute_generation(G: nx.DiGraph) -> dict[int, int]:
    """Compute generation number counting upward from leaf nodes.

    Leaves (out_degree == 0, i.e., no students in the graph) are Gen 0.
    Their advisors are Gen 1, those advisors' advisors are Gen 2, etc.

    Uses **longest** path from any leaf to each node, computed via
    topological sort on the reversed graph. This ensures that a parent
    (advisor) always has a higher generation than any of its children
    (students), matching the vis.js hierarchical layout levels.
    """
    # Reverse the graph: edges go advisee -> advisor
    R = G.reverse()

    generations: dict[int, int] = {}

    try:
        for node in nx.topological_sort(R):
            # Predecessors in R = students/advisees in original graph
            pred_gens = [
                generations[p] for p in R.predecessors(node) if p in generations
            ]
            if pred_gens:
                # This node's generation = 1 + max generation of its students
                generations[node] = max(pred_gens) + 1
            else:
                # No predecessors in R = leaf in original graph
                generations[node] = 0
    except nx.NetworkXUnfeasible:
        # Graph has a cycle (shouldn't happen, but fall back gracefully)
        # Use BFS longest-path approximation instead
        leaves = [n for n in G.nodes() if G.out_degree(n) == 0]
        for leaf in leaves:
            for node, dist in nx.single_source_shortest_path_length(R, leaf).items():
                if node not in generations or dist > generations[node]:
                    generations[node] = dist

    # Assign gen 0 to any remaining unreachable nodes
    for node in G.nodes():
        if node not in generations:
            generations[node] = 0

    return generations


def compute_tree_membership(
    G: nx.DiGraph, start_node_ids: list[int]
) -> dict[int, list[int]]:
    """Determine which starting-node tree(s) each graph node belongs to.

    For each start node, finds all ancestors reachable from it by traversing
    edges backward (advisee -> advisor). Returns a mapping of
    node_id -> list of tree indices (0-based) that node belongs to.

    Nodes appearing in multiple lists are shared/common ancestors.
    """
    R = G.reverse()  # edges: advisee -> advisor
    memberships: dict[int, list[int]] = {n: [] for n in G.nodes()}

    for tree_idx, start_id in enumerate(start_node_ids):
        if start_id not in G:
            continue
        # All nodes reachable from start_id in the reversed graph = ancestors
        ancestors = nx.descendants(R, start_id)
        ancestors.add(start_id)
        for node in ancestors:
            if node in memberships:
                memberships[node].append(tree_idx)

    return memberships


def compute_era_buckets(G: nx.DiGraph) -> dict[int, str]:
    """Assign each node to an era bucket based on its year.

    Returns a mapping of node_id -> era label string.
    """
    eras: dict[int, str] = {}
    for node, data in G.nodes(data=True):
        year = data.get("year")
        if year is None:
            eras[node] = "Unknown"
        elif year < 1600:
            eras[node] = "Before 1600"
        elif year < 1700:
            eras[node] = "1600s"
        elif year < 1800:
            eras[node] = "1700s"
        elif year < 1850:
            eras[node] = "1800-1849"
        elif year < 1900:
            eras[node] = "1850-1899"
        elif year < 1950:
            eras[node] = "1900-1949"
        elif year < 2000:
            eras[node] = "1950-1999"
        else:
            eras[node] = "2000+"
    return eras


def compute_institution_groups(
    G: nx.DiGraph, max_groups: int = 12
) -> dict[int, str]:
    """Assign each node to an institution group.

    The top `max_groups - 1` institutions by frequency get their own color.
    All remaining institutions are grouped as "Other".

    Returns a mapping of node_id -> institution group label.
    """
    institutions = [
        data.get("institution", "Unknown") for _, data in G.nodes(data=True)
    ]
    counter = Counter(institutions)
    top_institutions = {inst for inst, _ in counter.most_common(max_groups - 1)}

    groups: dict[int, str] = {}
    for node, data in G.nodes(data=True):
        inst = data.get("institution", "Unknown")
        groups[node] = inst if inst in top_institutions else "Other"
    return groups


def assign_colors(
    G: nx.DiGraph,
    color_by: ColorBy,
    palette: list[str],
) -> tuple[dict[int, str], dict[str, str]]:
    """Assign a color from the palette to each node based on the color_by strategy.

    Returns:
        - node_colors: mapping of node_id -> hex color
        - legend: mapping of label -> hex color (for the legend)
    """
    if color_by == ColorBy.INSTITUTION:
        groups = compute_institution_groups(G, max_groups=len(palette))
    elif color_by == ColorBy.ERA:
        groups = compute_era_buckets(G)
    elif color_by == ColorBy.DEPTH:
        depths = compute_depth(G)
        groups = {node: str(d) for node, d in depths.items()}
    else:
        groups = {node: "default" for node in G.nodes()}

    # Build sorted unique labels and map to palette colors
    unique_labels = sorted(set(groups.values()), key=_era_sort_key)
    label_to_color: dict[str, str] = {}
    for i, label in enumerate(unique_labels):
        label_to_color[label] = palette[i % len(palette)]

    node_colors = {node: label_to_color[label] for node, label in groups.items()}
    return node_colors, label_to_color


def _era_sort_key(label: str) -> tuple[int, str]:
    """Sort era labels chronologically, with 'Unknown' and 'Other' last."""
    if label == "Unknown":
        return (9999, label)
    if label == "Other":
        return (9998, label)
    # Try to extract a leading number for chronological sort
    try:
        num = int(label.split("-")[0].split("+")[0].replace("Before ", "").strip())
        return (num, label)
    except ValueError:
        return (5000, label)


def compute_node_sizes(G: nx.DiGraph, min_size: int = 15, max_size: int = 40) -> dict[int, int]:
    """Compute node sizes proportional to total degree (advisors + descendants).

    Nodes with more connections appear larger.
    """
    if len(G) == 0:
        return {}

    degrees = {node: G.in_degree(node) + G.out_degree(node) for node in G.nodes()}
    max_deg = max(degrees.values()) if degrees else 1
    min_deg = min(degrees.values()) if degrees else 0
    span = max_deg - min_deg if max_deg > min_deg else 1

    sizes: dict[int, int] = {}
    for node, deg in degrees.items():
        normalized = (deg - min_deg) / span
        sizes[node] = int(min_size + normalized * (max_size - min_size))
    return sizes
