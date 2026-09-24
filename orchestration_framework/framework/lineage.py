"""
Lineage visualization — draws the asset dependency graph and colors
each node by its latest run status.

Uses networkx + matplotlib only (no Graphviz binary required, so this
runs on a plain Windows Python install with no extra software).
"""

import networkx as nx
import matplotlib.pyplot as plt

from .core import get_registry

STATUS_COLORS = {
    "success": "#3B6D11",
    "failed": "#A32D2D",
    "skipped": "#5F5E5A",
    "running": "#185FA5",
    "pending": "#B4B2A9",
}


def build_graph():
    """Build a networkx DiGraph from the current asset registry."""
    registry = get_registry()
    g = nx.DiGraph()
    for a in registry.values():
        g.add_node(a.name)
    for a in registry.values():
        for dep in a.deps:
            g.add_edge(dep.name, a.name)
    return g


def _layered_positions(g):
    """Left-to-right layered layout — upstream assets on the left."""
    pos = {}
    for x, layer in enumerate(nx.topological_generations(g)):
        layer = list(layer)
        for y, node in enumerate(layer):
            pos[node] = (x, -y + (len(layer) - 1) / 2)
    return pos


def draw_lineage(status_by_asset=None, output_path="lineage.png", title=None):
    """Render the dependency graph to a PNG, colored by status.

    status_by_asset: optional {asset_name: status} dict, e.g. from
    Orchestrator.latest_statuses(). Assets not in the dict render gray
    ("pending" — never materialized, or not part of the latest run).
    """
    g = build_graph()
    if g.number_of_nodes() == 0:
        raise ValueError("No assets registered — import your pipeline module before calling this.")

    pos = _layered_positions(g)
    status_by_asset = status_by_asset or {}
    colors = [STATUS_COLORS.get(status_by_asset.get(n, "pending"), "#B4B2A9") for n in g.nodes]

    plt.figure(figsize=(max(6, g.number_of_nodes() * 1.6), 4))
    nx.draw(
        g, pos, with_labels=True, node_color=colors, node_size=2600,
        font_size=8, font_color="white", font_weight="bold",
        arrows=True, arrowsize=15, edgecolors="#2C2C2A", linewidths=1,
        connectionstyle="arc3,rad=0.0",
    )
    if title:
        plt.title(title, fontsize=11)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    return output_path
