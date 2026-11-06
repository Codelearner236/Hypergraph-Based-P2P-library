#!/usr/bin/env python3
"""
Hypergraph Visualization using Matplotlib & NetworkX.
Renders both:
1. Bipartite Graph Projection (Physical Nodes as circles, Hyperedges as square hubs).
2. Euler / Convex Polygon Enclosure (Translucent colored boundaries grouping member nodes).

Reads data directly from hypergraph.csv and connections.csv.
"""

import sys
import os

# ---------------------------------------------------------------------------
# Auto-detect and switch to .venv if running with system python without matplotlib
# ---------------------------------------------------------------------------
try:
    import matplotlib
    import networkx
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(script_dir, ".venv", "bin", "python")
    if os.path.exists(venv_python) and sys.executable != venv_python:
        os.execv(venv_python, [venv_python] + sys.argv)
    else:
        print("Error importing plotting libraries: No module named 'matplotlib' or 'networkx'")
        print("Please activate the virtual environment:")
        print("    source .venv/bin/activate")
        print("    python3 visualize_hypergraph.py")
        print("Or directly execute with .venv python:")
        print("    .venv/bin/python visualize_hypergraph.py")
        sys.exit(1)

import csv
import math
import subprocess
import argparse
from typing import Dict, List, Tuple, Set

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D
import networkx as nx


# Color palette for distinct hyperedges
HYPEREDGE_COLORS = [
    "#FF9800",  # Amber/Orange
    "#00BCD4",  # Cyan/Teal
    "#E91E63",  # Pink/Magenta
    "#9C27B0",  # Purple
    "#4CAF50",  # Green
    "#3F51B5",  # Indigo
]


def load_hypergraph_csv(filepath: str = "hypergraph.csv") -> Dict[str, dict]:
    """Load hyperedge definitions from CSV."""
    hyperedges = {}
    if not os.path.exists(filepath):
        # Default sample hyperedges if file not present
        return {
            "H1": {"name": "Consensus_Quorum", "members": ["Node-1", "Node-2", "Node-3"], "description": "3-Node Quorum"},
            "H2": {"name": "Storage_Shard", "members": ["Node-2", "Node-3", "Node-4", "Node-5"], "description": "4-Node Replica Set"},
        }

    with open(filepath, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            edge_id = row.get("hyperedge_id", "").strip()
            if not edge_id:
                continue
            name = row.get("group_name", "").strip() or f"Group-{edge_id}"
            raw_members = row.get("member_nodes", "").split(",")
            members = [m.strip() for m in raw_members if m.strip()]
            desc = row.get("description", "").strip()
            hyperedges[edge_id] = {
                "name": name,
                "members": members,
                "description": desc,
            }
    return hyperedges


def load_connections_csv(filepath: str = "connections.csv") -> List[Tuple[str, str]]:
    """Load physical TCP socket links from CSV."""
    links = []
    if not os.path.exists(filepath):
        return []

    with open(filepath, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            src = row.get("source_node", "").strip()
            tgt = row.get("target_node", "").strip()
            if src and tgt:
                links.append((src, tgt))
    return links


def compute_convex_hull(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Compute 2D convex hull of a set of points (Graham Scan)."""
    pts = sorted(set(map(tuple, points)))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def expand_polygon(points: List[Tuple[float, float]], scale: float = 1.35, offset: float = 0.12) -> List[Tuple[float, float]]:
    """Expand polygon outward from centroid so it nicely encloses circular node markers."""
    if len(points) == 1:
        # Single node: create a small circle-like diamond
        cx, cy = points[0]
        r = 0.22
        return [(cx - r, cy), (cx, cy + r), (cx + r, cy), (cx, cy - r)]

    if len(points) == 2:
        # Line segment: expand into an elongated capsule polygon
        (x1, y1), (x2, y2) = points
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / dist * 0.18, dx / dist * 0.18
        return [
            (x1 + nx - (dx / dist) * 0.1, y1 + ny - (dy / dist) * 0.1),
            (x2 + nx + (dx / dist) * 0.1, y2 + ny + (dy / dist) * 0.1),
            (x2 - nx + (dx / dist) * 0.1, y2 - ny + (dy / dist) * 0.1),
            (x1 - nx - (dx / dist) * 0.1, y1 - ny - (dy / dist) * 0.1),
        ]

    # 3+ points: expand from centroid
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    expanded = []
    for x, y in points:
        dx = x - cx
        dy = y - cy
        dist = math.hypot(dx, dy) or 1.0
        ex = x + (dx / dist) * offset + dx * (scale - 1.0)
        ey = y + (dy / dist) * offset + dy * (scale - 1.0)
        expanded.append((ex, ey))
    return expanded


def plot_hypergraph(
    hypergraph_csv: str = "hypergraph.csv",
    connections_csv: str = "connections.csv",
    output_png: str = "hypergraph_plot.png",
    show_gui: bool = True,
):
    """Generate high-resolution dual-panel visualization of the hypergraph."""
    hyperedges = load_hypergraph_csv(hypergraph_csv)
    physical_links = load_connections_csv(connections_csv)

    # Determine unique physical nodes
    all_nodes_set: Set[str] = set()
    for e in hyperedges.values():
        all_nodes_set.update(e["members"])
    for src, tgt in physical_links:
        all_nodes_set.add(src)
        all_nodes_set.add(tgt)

    if not all_nodes_set:
        all_nodes_set = {f"Node-{i}" for i in range(1, 6)}

    nodes = sorted(all_nodes_set)
    num_nodes = len(nodes)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8.5), dpi=150)
    fig.patch.set_facecolor("#0F172A")  # Modern dark background

    # -----------------------------------------------------------------------
    # PANEL 1: Bipartite Graph Projection
    # -----------------------------------------------------------------------
    ax1.set_facecolor("#1E293B")
    ax1.set_title("1. Bipartite Projection (Hub View)", fontsize=16, fontweight="bold", color="#F8FAFC", pad=15)

    B = nx.Graph()
    B.add_nodes_from(nodes, bipartite=0)

    edge_colors_map = {}
    hyperedge_nodes = []
    for idx, (h_id, h_data) in enumerate(hyperedges.items()):
        color = HYPEREDGE_COLORS[idx % len(HYPEREDGE_COLORS)]
        edge_colors_map[h_id] = color
        h_label = f"{h_id}\n({h_data['name']})"
        B.add_node(h_label, bipartite=1)
        hyperedge_nodes.append((h_label, color))
        for member in h_data["members"]:
            B.add_edge(member, h_label)

    # Layout for bipartite graph
    pos1 = nx.spring_layout(B, k=1.2, seed=42)

    # Draw physical mesh connections as subtle dashed lines
    mesh_edges = []
    for src, tgt in physical_links:
        if src in pos1 and tgt in pos1:
            mesh_edges.append((src, tgt))
    if mesh_edges:
        nx.draw_networkx_edges(
            B, pos1, edgelist=mesh_edges, ax=ax1,
            edge_color="#475569", style="dashed", width=1.5, alpha=0.5
        )

    # Draw hyperedge bipartite membership links
    for h_label, color in hyperedge_nodes:
        star_edges = [(u, v) for u, v in B.edges() if u == h_label or v == h_label]
        nx.draw_networkx_edges(
            B, pos1, edgelist=star_edges, ax=ax1,
            edge_color=color, width=2.5, alpha=0.85
        )

    # Draw physical nodes (circles)
    nx.draw_networkx_nodes(
        B, pos1, nodelist=nodes, ax=ax1,
        node_color="#38BDF8", node_shape="o", node_size=1100,
        edgecolors="#F8FAFC", linewidths=2.0
    )
    nx.draw_networkx_labels(
        B, pos1, labels={n: n for n in nodes}, ax=ax1,
        font_size=10, font_weight="bold", font_color="#0F172A"
    )

    # Draw hyperedges (squares)
    for h_label, color in hyperedge_nodes:
        nx.draw_networkx_nodes(
            B, pos1, nodelist=[h_label], ax=ax1,
            node_color=color, node_shape="s", node_size=1600,
            edgecolors="#FFFFFF", linewidths=2.0
        )
    nx.draw_networkx_labels(
        B, pos1, labels={h_label: h_label for h_label, _ in hyperedge_nodes}, ax=ax1,
        font_size=8, font_weight="bold", font_color="#0F172A"
    )

    ax1.axis("off")

    # -----------------------------------------------------------------------
    # PANEL 2: Euler / Convex Polygon Enclosure View
    # -----------------------------------------------------------------------
    ax2.set_facecolor("#1E293B")
    ax2.set_title("2. Euler Enclosure (Convex Hull Blobs)", fontsize=16, fontweight="bold", color="#F8FAFC", pad=15)

    # Arrange physical nodes in a regular circle
    pos2: Dict[str, Tuple[float, float]] = {}
    radius = 2.0
    for i, node_name in enumerate(nodes):
        angle = 2 * math.pi * i / num_nodes + (math.pi / 2)
        pos2[node_name] = (radius * math.cos(angle), radius * math.sin(angle))

    # Draw physical TCP connections in background
    for src, tgt in physical_links:
        if src in pos2 and tgt in pos2:
            x_vals = [pos2[src][0], pos2[tgt][0]]
            y_vals = [pos2[src][1], pos2[tgt][1]]
            ax2.plot(x_vals, y_vals, color="#334155", linestyle="--", linewidth=1.2, zorder=1)

    # Draw colored convex hulls for each hyperedge
    legend_elements = []
    for idx, (h_id, h_data) in enumerate(hyperedges.items()):
        color = HYPEREDGE_COLORS[idx % len(HYPEREDGE_COLORS)]
        member_coords = [pos2[m] for m in h_data["members"] if m in pos2]
        if not member_coords:
            continue

        hull_pts = compute_convex_hull(member_coords)
        expanded_pts = expand_polygon(hull_pts, scale=1.12 + 0.05 * idx, offset=0.18 + 0.04 * idx)

        poly = patches.Polygon(
            expanded_pts,
            closed=True,
            facecolor=color,
            edgecolor=color,
            alpha=0.22,
            linewidth=2.5,
            zorder=2,
            linestyle="-",
        )
        ax2.add_patch(poly)

        label_txt = f"{h_id}: {h_data['name']} ({len(h_data['members'])} nodes)"
        legend_elements.append(
            patches.Patch(facecolor=color, edgecolor=color, alpha=0.5, label=label_txt)
        )

    # Draw nodes on top
    for node_name, (x, y) in pos2.items():
        circle = plt.Circle((x, y), 0.28, facecolor="#38BDF8", edgecolor="#F8FAFC", linewidth=2.5, zorder=4)
        ax2.add_patch(circle)
        ax2.text(x, y, node_name, color="#0F172A", fontsize=9, fontweight="bold", ha="center", va="center", zorder=5)

    ax2.set_xlim(-3.2, 3.2)
    ax2.set_ylim(-3.2, 3.2)
    ax2.set_aspect("equal")
    ax2.axis("off")

    if legend_elements:
        leg = ax2.legend(
            handles=legend_elements,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.08),
            ncol=min(len(legend_elements), 3),
            frameon=True,
            facecolor="#0F172A",
            edgecolor="#475569",
            fontsize=9,
            labelcolor="#F8FAFC",
        )

    plt.tight_layout()
    plt.savefig(output_png, dpi=200, facecolor=fig.get_facecolor(), bbox_inches="tight")
    print(f"✓ High-resolution Hypergraph plot saved to: {output_png}")

    if show_gui:
        try:
            # On macOS, open the generated PNG directly in Preview/Default Viewer
            if sys.platform == "darwin":
                subprocess.Popen(["open", output_png])
            else:
                plt.show()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="P2P Hypergraph Visualizer")
    parser.add_argument("--hypergraph", "-H", default="hypergraph.csv", help="Path to hypergraph.csv")
    parser.add_argument("--connections", "-c", default="connections.csv", help="Path to connections.csv")
    parser.add_argument("--output", "-o", default="hypergraph_plot.png", help="Output PNG path")
    parser.add_argument("--no-gui", action="store_true", help="Do not open image viewer automatically")
    args = parser.parse_args()

    plot_hypergraph(
        hypergraph_csv=args.hypergraph,
        connections_csv=args.connections,
        output_png=args.output,
        show_gui=not args.no_gui,
    )


if __name__ == "__main__":
    main()

