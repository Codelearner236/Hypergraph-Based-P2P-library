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
import subprocess

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
        # Attempt to auto-create .venv and install requirements if not present
        req_file = os.path.join(script_dir, "requirements.txt")
        print("Plotting libraries ('matplotlib' or 'networkx') not detected.")
        print(f"Setting up virtual environment at {venv_python}...")
        try:
            subprocess.run([sys.executable, "-m", "venv", os.path.join(script_dir, ".venv")], check=True)
            if os.path.exists(req_file):
                subprocess.run([venv_python, "-m", "pip", "install", "-r", req_file], check=True)
            else:
                subprocess.run([venv_python, "-m", "pip", "install", "matplotlib>=3.8.0", "networkx>=3.0"], check=True)
            print("✓ Environment initialized successfully. Launching visualization...")
            os.execv(venv_python, [venv_python] + sys.argv)
        except Exception as err:
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
import time
from typing import Dict, List, Tuple, Set

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D
from matplotlib.animation import FuncAnimation
import networkx as nx
import numpy as np
import json


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


def draw_bipartite(
    ax,
    nodes: List[str],
    hyperedges: Dict[str, dict],
    physical_links: List[Tuple[str, str]],
    t: float = 0.0,
    anim_packets: bool = False,
):
    """Render Bipartite Projection (Hub View)."""
    ax.set_facecolor("#1E293B")
    ax.set_title("1. Bipartite Projection (Hub View)", fontsize=14, fontweight="bold", color="#F8FAFC", pad=12)

    B = nx.Graph()
    B.add_nodes_from(nodes, bipartite=0)

    hyperedge_nodes = []
    for idx, (h_id, h_data) in enumerate(hyperedges.items()):
        color = HYPEREDGE_COLORS[idx % len(HYPEREDGE_COLORS)]
        h_label = f"{h_id}\n({h_data['name']})"
        B.add_node(h_label, bipartite=1)
        hyperedge_nodes.append((h_label, color))
        for member in h_data["members"]:
            B.add_edge(member, h_label)

    pos1 = nx.spring_layout(B, k=1.2, seed=42)

    # Draw physical mesh connections as subtle dashed lines
    mesh_edges = [(src, tgt) for src, tgt in physical_links if src in pos1 and tgt in pos1]
    if mesh_edges:
        nx.draw_networkx_edges(
            B, pos1, edgelist=mesh_edges, ax=ax,
            edge_color="#475569", style="dashed", width=1.4, alpha=0.5
        )

    # Draw hyperedge bipartite membership links
    for h_label, color in hyperedge_nodes:
        star_edges = [(u, v) for u, v in B.edges() if u == h_label or v == h_label]
        nx.draw_networkx_edges(
            B, pos1, edgelist=star_edges, ax=ax,
            edge_color=color, width=2.4, alpha=0.85
        )

    # Draw animated multicast packets along star edges in live mode
    if anim_packets and t > 0:
        for idx, (h_label, color) in enumerate(hyperedge_nodes):
            star_edges = [(u, v) for u, v in B.edges() if u == h_label or v == h_label]
            for e_idx, (u, v) in enumerate(star_edges):
                if u in pos1 and v in pos1:
                    hub_pt = pos1[h_label]
                    mem_pt = pos1[v if u == h_label else u]
                    prog = (t * 0.9 + idx * 0.35 + e_idx * 0.18) % 1.0
                    px = hub_pt[0] + (mem_pt[0] - hub_pt[0]) * prog
                    py = hub_pt[1] + (mem_pt[1] - hub_pt[1]) * prog
                    ax.scatter([px], [py], s=65, color="#FFFFFF", edgecolors=color, linewidths=2.0, zorder=6)

    # Draw physical nodes (circles)
    nx.draw_networkx_nodes(
        B, pos1, nodelist=nodes, ax=ax,
        node_color="#38BDF8", node_shape="o", node_size=1000,
        edgecolors="#F8FAFC", linewidths=2.0
    )
    nx.draw_networkx_labels(
        B, pos1, labels={n: n for n in nodes}, ax=ax,
        font_size=9, font_weight="bold", font_color="#0F172A"
    )

    # Draw hyperedges (squares)
    for h_label, color in hyperedge_nodes:
        nx.draw_networkx_nodes(
            B, pos1, nodelist=[h_label], ax=ax,
            node_color=color, node_shape="s", node_size=1400,
            edgecolors="#FFFFFF", linewidths=2.0
        )
    nx.draw_networkx_labels(
        B, pos1, labels={h_label: h_label for h_label, _ in hyperedge_nodes}, ax=ax,
        font_size=8, font_weight="bold", font_color="#0F172A"
    )
    ax.axis("off")


def draw_euler(
    ax,
    nodes: List[str],
    hyperedges: Dict[str, dict],
    physical_links: List[Tuple[str, str]],
    t: float = 0.0,
    anim_packets: bool = False,
):
    """Render Euler Enclosure View (Convex Hull Blobs)."""
    ax.set_facecolor("#1E293B")
    ax.set_title("2. Euler Enclosure (Convex Hull Blobs)", fontsize=14, fontweight="bold", color="#F8FAFC", pad=12)

    num_nodes = len(nodes)
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
            ax.plot(x_vals, y_vals, color="#334155", linestyle="--", linewidth=1.2, zorder=1)

    # Draw colored convex hulls for each hyperedge
    legend_elements = []
    for idx, (h_id, h_data) in enumerate(hyperedges.items()):
        color = HYPEREDGE_COLORS[idx % len(HYPEREDGE_COLORS)]
        member_coords = [pos2[m] for m in h_data["members"] if m in pos2]
        if not member_coords:
            continue

        hull_pts = compute_convex_hull(member_coords)
        breathing = 0.025 * math.sin(t * 3.0 + idx * 1.6) if t > 0 else 0.0
        expanded_pts = expand_polygon(
            hull_pts,
            scale=1.12 + 0.04 * idx + (0.012 * math.sin(t * 2.2 + idx) if t > 0 else 0.0),
            offset=0.18 + 0.03 * idx + breathing,
        )

        poly = patches.Polygon(
            expanded_pts,
            closed=True,
            facecolor=color,
            edgecolor=color,
            alpha=0.22,
            linewidth=2.2,
            zorder=2,
            linestyle="-",
        )
        ax.add_patch(poly)

        label_txt = f"{h_id}: {h_data['name']} ({len(h_data['members'])} nodes)"
        legend_elements.append(
            patches.Patch(facecolor=color, edgecolor=color, alpha=0.5, label=label_txt)
        )

    # Draw animated packet propagation along hyperedge chords in live mode
    if anim_packets and t > 0:
        for idx, (h_id, h_data) in enumerate(hyperedges.items()):
            color = HYPEREDGE_COLORS[idx % len(HYPEREDGE_COLORS)]
            member_coords = [m for m in h_data["members"] if m in pos2]
            if len(member_coords) >= 2:
                src = member_coords[0]
                for tgt_idx, tgt in enumerate(member_coords[1:]):
                    prog = (t * 0.8 + idx * 0.35 + tgt_idx * 0.22) % 1.0
                    sx, sy = pos2[src]
                    tx, ty = pos2[tgt]
                    px = sx + (tx - sx) * prog
                    py = sy + (ty - sy) * prog
                    ax.scatter([px], [py], s=70, color="#FFFFFF", edgecolors=color, linewidths=2.2, zorder=6)

    # Draw nodes on top
    for node_name, (x, y) in pos2.items():
        circle = plt.Circle((x, y), 0.28, facecolor="#38BDF8", edgecolor="#F8FAFC", linewidth=2.5, zorder=4)
        ax.add_patch(circle)
        ax.text(x, y, node_name, color="#0F172A", fontsize=9, fontweight="bold", ha="center", va="center", zorder=5)

    ax.set_xlim(-3.2, 3.2)
    ax.set_ylim(-3.2, 3.2)
    ax.set_aspect("equal")
    ax.axis("off")

    if legend_elements:
        ax.legend(
            handles=legend_elements,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.06),
            ncol=min(len(legend_elements), 3),
            frameon=True,
            facecolor="#0F172A",
            edgecolor="#475569",
            fontsize=8,
            labelcolor="#F8FAFC",
        )


def draw_dual_graph(
    ax,
    hyperedges: Dict[str, dict],
    t: float = 0.0,
    anim_packets: bool = False,
):
    """Render Dual Line Graph (Inter-Hyperedge Routing & Quorum Bridges)."""
    ax.set_facecolor("#1E293B")
    ax.set_title("3. Dual Line Graph (Inter-Hyperedge Routing)", fontsize=14, fontweight="bold", color="#F8FAFC", pad=12)

    D = nx.Graph()
    for h_id, h_data in hyperedges.items():
        D.add_node(h_id, name=h_data["name"], count=len(h_data["members"]))

    h_keys = list(hyperedges.keys())
    for i in range(len(h_keys)):
        for j in range(i + 1, len(h_keys)):
            h1, h2 = h_keys[i], h_keys[j]
            shared = set(hyperedges[h1]["members"]) & set(hyperedges[h2]["members"])
            if shared:
                D.add_edge(h1, h2, shared=sorted(shared), weight=len(shared))

    if len(D) <= 1:
        ax.text(0.5, 0.5, "Single hyperedge defined.\nNeed ≥ 2 hyperedges for dual graph.",
                ha="center", va="center", color="#94A3B8", fontsize=11, transform=ax.transAxes)
        ax.axis("off")
        return

    pos_d = nx.spring_layout(D, k=1.8, seed=42) if len(D) > 2 else nx.circular_layout(D)

    # Draw edges with weight-based width
    for u, v, data in D.edges(data=True):
        nx.draw_networkx_edges(
            D, pos_d, edgelist=[(u, v)], ax=ax,
            width=2.5 + data["weight"] * 1.2,
            edge_color="#38BDF8", alpha=0.8, style="solid"
        )

    # Animated packets traveling along shared quorum bridges
    if anim_packets and t > 0 and len(D.edges()) > 0:
        for e_idx, (u, v, data) in enumerate(D.edges(data=True)):
            if u in pos_d and v in pos_d:
                prog = (t * 0.7 + e_idx * 0.28) % 1.0
                ux, uy = pos_d[u]
                vx, vy = pos_d[v]
                px = ux + (vx - ux) * prog
                py = uy + (vy - uy) * prog
                ax.scatter([px], [py], s=65, color="#38BDF8", edgecolors="#FFFFFF", linewidths=1.8, zorder=6)

    # Edge labels showing shared member count & node names
    edge_labels = {}
    for u, v, data in D.edges(data=True):
        shared_list = data["shared"]
        display_nodes = ", ".join(shared_list[:3]) + ("..." if len(shared_list) > 3 else "")
        edge_labels[(u, v)] = f"Shared ({data['weight']}):\n{display_nodes}"

    nx.draw_networkx_edge_labels(
        D, pos_d, edge_labels=edge_labels, ax=ax,
        font_size=8, font_color="#F1F5F9", font_weight="bold",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#0F172A", edgecolor="#475569", alpha=0.9)
    )

    # Draw hyperedge nodes
    for idx, (h_id, h_data) in enumerate(hyperedges.items()):
        color = HYPEREDGE_COLORS[idx % len(HYPEREDGE_COLORS)]
        nx.draw_networkx_nodes(
            D, pos_d, nodelist=[h_id], ax=ax,
            node_color=color, node_shape="h", node_size=2800,
            edgecolors="#FFFFFF", linewidths=2.5
        )
        label_text = f"{h_id}\n{h_data['name']}\n({len(h_data['members'])} nodes)"
        nx.draw_networkx_labels(
            D, pos_d, labels={h_id: label_text}, ax=ax,
            font_size=8, font_weight="bold", font_color="#0F172A"
        )
    ax.axis("off")


def draw_incidence_matrix(
    ax,
    nodes: List[str],
    hyperedges: Dict[str, dict],
    t: float = 0.0,
):
    """Render Incidence Matrix Heatmap (Physical Nodes × Hyperedges)."""
    ax.set_facecolor("#1E293B")
    ax.set_title("4. Incidence Matrix (Node × Hyperedge)", fontsize=14, fontweight="bold", color="#F8FAFC", pad=12)

    h_keys = list(hyperedges.keys())
    if not h_keys or not nodes:
        ax.text(0.5, 0.5, "No data available.", ha="center", va="center", color="#94A3B8", transform=ax.transAxes)
        ax.axis("off")
        return

    matrix = np.zeros((len(nodes), len(h_keys)), dtype=int)
    for c_idx, h_id in enumerate(h_keys):
        for r_idx, node in enumerate(nodes):
            if node in hyperedges[h_id]["members"]:
                matrix[r_idx, c_idx] = 1

    # Draw cell rectangles and checkmarks
    for r in range(len(nodes)):
        for c in range(len(h_keys)):
            is_member = matrix[r, c] == 1
            color = HYPEREDGE_COLORS[c % len(HYPEREDGE_COLORS)] if is_member else "#334155"
            rect = patches.FancyBboxPatch(
                (c - 0.42, r - 0.42), 0.84, 0.84,
                boxstyle="round,pad=0.04,rounding_size=0.15",
                facecolor=color if is_member else "#1E293B",
                edgecolor=color if is_member else "#475569",
                linewidth=1.8 if is_member else 1.0,
                alpha=0.9 if is_member else 0.35,
                zorder=2
            )
            ax.add_patch(rect)

            symbol = "✓" if is_member else "—"
            text_color = "#0F172A" if is_member else "#64748B"
            ax.text(c, r, symbol, ha="center", va="center", color=text_color,
                    fontsize=14, fontweight="bold", zorder=3)

    # Set ticks and labels
    ax.set_xticks(range(len(h_keys)))
    ax.set_xticklabels([f"{h_id}\n({hyperedges[h_id]['name']})" for h_id in h_keys],
                       fontsize=9, color="#F8FAFC", fontweight="bold")
    ax.set_yticks(range(len(nodes)))
    ax.set_yticklabels(nodes, fontsize=10, color="#38BDF8", fontweight="bold")

    ax.set_xlim(-0.5, len(h_keys) - 0.5)
    ax.set_ylim(len(nodes) - 0.5, -0.5)
    ax.tick_params(top=False, bottom=True, left=True, right=False)
    for spine in ax.spines.values():
        spine.set_color("#475569")


def export_interactive_html(
    hyperedges: Dict[str, dict],
    physical_links: List[Tuple[str, str]],
    nodes: List[str],
    output_html: str = "hypergraph.html",
    show_gui: bool = True,
):
    """Generate interactive browser visualization with filter buttons, SVG network, and matrix."""
    num_nodes = len(nodes)
    radius = 240
    cx, cy = 350, 320
    node_coords = {}
    for i, name in enumerate(nodes):
        angle = 2 * math.pi * i / num_nodes - (math.pi / 2)
        node_coords[name] = {
            "x": round(cx + radius * math.cos(angle), 1),
            "y": round(cy + radius * math.sin(angle), 1)
        }

    # Prepare JSON structures and pre-rendered HTML snippets
    h_data_list = []
    for idx, (h_id, d) in enumerate(hyperedges.items()):
        color = HYPEREDGE_COLORS[idx % len(HYPEREDGE_COLORS)]
        h_data_list.append({
            "id": h_id,
            "name": d["name"],
            "members": d["members"],
            "color": color,
            "desc": d.get("description", "")
        })

    buttons_html = " ".join([
        f'<button class="btn" onclick="filterHyperedge(\'{h["id"]}\', this)">{h["id"]}: {h["name"]}</button>'
        for h in h_data_list
    ])

    links_svg = "".join([
        f'<line class="link" x1="{node_coords[u]["x"]}" y1="{node_coords[u]["y"]}" x2="{node_coords[v]["x"]}" y2="{node_coords[v]["y"]}" />'
        for u, v in physical_links if u in node_coords and v in node_coords
    ])

    nodes_svg = "".join([
        f'<g class="node-group" id="node-{n}"><circle class="node-circle" cx="{c["x"]}" cy="{c["y"]}" r="22" /><text class="node-label" x="{c["x"]}" y="{c["y"]}">{n}</text></g>'
        for n, c in node_coords.items()
    ])

    table_rows = []
    for h in h_data_list:
        member_tags = " ".join([f'<span class="tag" style="background:{h["color"]};">{m}</span>' for m in h["members"]])
        table_rows.append(f'<tr><td><b style="color:{h["color"]};">{h["id"]}</b><br><span style="color:#94A3B8;font-size:11px;">{h["name"]}</span></td><td>{member_tags}</td></tr>')
    table_rows_html = "".join(table_rows)

    phys_rows_html = "".join([f'<tr><td>{u} ↔ {v}</td><td style="color:#10B981;">Active TCP</td></tr>' for u, v in physical_links])

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>P2P Hypergraph Interactive Explorer</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: #0B1120;
            color: #F8FAFC;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            padding: 24px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #1E293B;
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        .title {{ font-size: 24px; font-weight: bold; color: #38BDF8; }}
        .badge {{ background: #1E293B; border: 1px solid #334155; padding: 6px 14px; border-radius: 9999px; font-size: 13px; }}
        .main-grid {{
            display: grid;
            grid-template-columns: 1fr 380px;
            gap: 24px;
        }}
        .card {{
            background: #131D31;
            border: 1px solid #1E293B;
            border-radius: 12px;
            padding: 20px;
        }}
        .controls {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 18px;
        }}
        .btn {{
            background: #1E293B;
            border: 1px solid #334155;
            color: #F8FAFC;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
            transition: all 0.2s;
        }}
        .btn:hover, .btn.active {{
            background: #38BDF8;
            color: #0F172A;
            border-color: #38BDF8;
        }}
        svg {{
            width: 100%;
            height: 640px;
            background: #0F172A;
            border-radius: 8px;
        }}
        .link {{ stroke: #334155; stroke-dasharray: 4,4; stroke-width: 1.5; }}
        .hull {{ opacity: 0.28; transition: opacity 0.3s; }}
        .node-circle {{ fill: #38BDF8; stroke: #FFFFFF; stroke-width: 2.5; cursor: pointer; transition: all 0.2s; }}
        .node-circle:hover {{ fill: #F59E0B; transform: scale(1.1); transform-origin: center; }}
        .node-label {{ fill: #0F172A; font-weight: bold; font-size: 11px; text-anchor: middle; dominant-baseline: middle; pointer-events: none; }}
        .dimmed {{ opacity: 0.15 !important; }}
        .highlight {{ stroke: #F59E0B !important; stroke-width: 3.5 !important; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            margin-top: 10px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #1E293B;
        }}
        th {{ color: #94A3B8; text-transform: uppercase; font-size: 11px; }}
        .tag {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            color: #0F172A;
            margin: 2px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="title">🌐 P2P Hypergraph Interactive Explorer</div>
            <div style="color: #94A3B8; font-size: 14px; margin-top: 4px;">Dynamic multi-hop quorum inspection & live topology visualization</div>
        </div>
        <div class="badge">Nodes: <b>{len(nodes)}</b> | Hyperedges: <b>{len(hyperedges)}</b> | Physical Links: <b>{len(physical_links)}</b></div>
    </div>

    <div class="controls">
        <button class="btn active" onclick="filterHyperedge('all', this)">Show All</button>
        {buttons_html}
    </div>

    <div class="main-grid">
        <div class="card">
            <svg id="svgGraph" viewBox="0 0 700 640">
                <!-- Physical Links -->
                <g id="linksGroup">
                    {links_svg}
                </g>
                <!-- Hyperedge Polygons -->
                <g id="hullsGroup"></g>
                <!-- Nodes -->
                <g id="nodesGroup">
                    {nodes_svg}
                </g>
            </svg>
        </div>

        <div>
            <div class="card" style="margin-bottom: 24px;">
                <h3 style="color: #38BDF8; margin-bottom: 12px;">Defined Hyperedges</h3>
                <table>
                    <thead><tr><th>ID / Name</th><th>Members</th></tr></thead>
                    <tbody>
                        {table_rows_html}
                    </tbody>
                </table>
            </div>

            <div class="card">
                <h3 style="color: #38BDF8; margin-bottom: 12px;">Physical Links Snapshot</h3>
                <div style="max-height: 220px; overflow-y: auto;">
                    <table>
                        <thead><tr><th>Link</th><th>Type</th></tr></thead>
                        <tbody>
                            {phys_rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
        const nodeCoords = {json.dumps(node_coords)};
        const hyperedges = {json.dumps(h_data_list)};

        function drawHulls() {{
            const group = document.getElementById("hullsGroup");
            group.innerHTML = "";
            hyperedges.forEach((h, idx) => {{
                const pts = h.members.map(m => nodeCoords[m]).filter(Boolean);
                if (pts.length < 2) return;
                const pathStr = "M " + pts.map(p => `${{p.x}} ${{p.y}}`).join(" L ") + " Z";
                const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                path.setAttribute("d", pathStr);
                path.setAttribute("class", "hull");
                path.setAttribute("id", "hull-" + h.id);
                path.setAttribute("fill", h.color);
                path.setAttribute("stroke", h.color);
                path.setAttribute("stroke-width", "32");
                path.setAttribute("stroke-linejoin", "round");
                group.appendChild(path);
            }});
        }}
        drawHulls();

        function filterHyperedge(selectedId, btn) {{
            document.querySelectorAll(".btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            hyperedges.forEach(h => {{
                const hull = document.getElementById("hull-" + h.id);
                if (!hull) return;
                if (selectedId === "all" || selectedId === h.id) {{
                    hull.classList.remove("dimmed");
                }} else {{
                    hull.classList.add("dimmed");
                }}
            }});

            const targetMembers = selectedId === "all"
                ? null
                : new Set(hyperedges.find(h => h.id === selectedId)?.members || []);

            for (const name in nodeCoords) {{
                const el = document.getElementById("node-" + name);
                if (!el) continue;
                if (!targetMembers || targetMembers.has(name)) {{
                    el.classList.remove("dimmed");
                }} else {{
                    el.classList.add("dimmed");
                }}
            }}
        }}
    </script>
</body>
</html>
"""
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"✓ Interactive Hypergraph visualizer saved to: {output_html}")
    if show_gui:
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", output_html])
        except Exception:
            pass


class LiveHypergraphState:
    """Monitors CSV modification timestamps and provides live topology state."""

    def __init__(self, hypergraph_csv: str = "hypergraph.csv", connections_csv: str = "connections.csv"):
        self.hypergraph_csv = hypergraph_csv
        self.connections_csv = connections_csv
        self.last_h_mtime = -1.0
        self.last_c_mtime = -1.0
        self.hyperedges: Dict[str, dict] = {}
        self.physical_links: List[Tuple[str, str]] = []
        self.nodes: List[str] = []
        self.update_count = 0
        self.flash_counter = 0
        self.last_updated_str = "init"
        self.reload(force=True)

    def reload(self, force: bool = False) -> bool:
        """Reload CSV data if modification timestamp changed."""
        h_mtime = os.path.getmtime(self.hypergraph_csv) if os.path.exists(self.hypergraph_csv) else 0.0
        c_mtime = os.path.getmtime(self.connections_csv) if os.path.exists(self.connections_csv) else 0.0

        if force or h_mtime != self.last_h_mtime or c_mtime != self.last_c_mtime:
            self.last_h_mtime = h_mtime
            self.last_c_mtime = c_mtime
            self.hyperedges = load_hypergraph_csv(self.hypergraph_csv)
            self.physical_links = load_connections_csv(self.connections_csv)

            all_nodes: Set[str] = set()
            for e in self.hyperedges.values():
                all_nodes.update(e.get("members", []))
            for src, tgt in self.physical_links:
                all_nodes.add(src)
                all_nodes.add(tgt)
            if not all_nodes:
                all_nodes = {f"Node-{i}" for i in range(1, 6)}
            self.nodes = sorted(all_nodes)
            self.update_count += 1
            if not force:
                self.flash_counter = 15
                self.last_updated_str = time.strftime("%H:%M:%S")
            return True
        return False


def run_live_animation(
    hypergraph_csv: str = "hypergraph.csv",
    connections_csv: str = "connections.csv",
    style: str = "dashboard",
    interval: int = 100,
):
    """
    Launch interactive live animated hypergraph window via Matplotlib FuncAnimation.
    Does NOT save PNG or HTML to disk. Real-time dynamic updates on CSV changes.
    """
    state = LiveHypergraphState(hypergraph_csv, connections_csv)

    print("\n" + "=" * 76)
    print("⚡ LIVE P2P HYPERGRAPH VISUALIZER (FuncAnimation Interactive Window)")
    print("=" * 76)
    print(f"  • Layout Style    : {style.upper()}")
    print(f"  • Refresh Interval: {interval} ms (~{int(1000/interval)} FPS)")
    print(f"  • Monitoring CSV  : {hypergraph_csv} & {connections_csv}")
    print(f"  • Initial State   : {len(state.nodes)} nodes, {len(state.hyperedges)} hyperedges, {len(state.physical_links)} physical links")
    print("  • Live Animation  : Pulsing hyperedge hulls & traveling multicast packets")
    print("  • Hot-Reload      : Any topology changes written by NetworkManager auto-refresh!")
    print("  • Zero Storage    : Pure in-memory GUI window — no PNG/HTML files saved.")
    print("=" * 76)
    print("Press Ctrl+C in terminal or close window to exit.\n")

    start_time = time.time()

    if style in ("dashboard", "all"):
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(18, 14), dpi=120)
        fig.patch.set_facecolor("#0F172A")

        def update_frame(frame):
            t = time.time() - start_time
            state.reload()

            ax1.clear()
            ax2.clear()
            ax3.clear()
            ax4.clear()

            draw_bipartite(ax1, state.nodes, state.hyperedges, state.physical_links, t=t, anim_packets=True)
            draw_euler(ax2, state.nodes, state.hyperedges, state.physical_links, t=t, anim_packets=True)
            draw_dual_graph(ax3, state.hyperedges, t=t, anim_packets=True)
            draw_incidence_matrix(ax4, state.nodes, state.hyperedges, t=t)

            pulse_glyph = "🟢" if int(t * 2.5) % 2 == 0 else "⚪"
            title_text = f"P2P HYPERGRAPH LIVE TOPOLOGY DASHBOARD • {pulse_glyph} LIVE STREAM"
            if state.flash_counter > 0:
                title_text += f"  ⚡ TOPOLOGY HOT-RELOADED [{state.last_updated_str}]"
                state.flash_counter -= 1

            fig.suptitle(
                f"{title_text}\n"
                f"Nodes: {len(state.nodes)}  |  Hyperedges: {len(state.hyperedges)}  |  Physical Mesh Links: {len(state.physical_links)}  |  Frame: {frame}",
                fontsize=13, fontweight="bold", color="#38BDF8", y=0.99
            )
            plt.tight_layout(rect=[0, 0.02, 1, 0.96])
            return []

    else:
        fig, ax = plt.subplots(figsize=(12, 10), dpi=130)
        fig.patch.set_facecolor("#0F172A")

        def update_frame(frame):
            t = time.time() - start_time
            state.reload()

            ax.clear()
            if style == "euler":
                draw_euler(ax, state.nodes, state.hyperedges, state.physical_links, t=t, anim_packets=True)
            elif style == "bipartite":
                draw_bipartite(ax, state.nodes, state.hyperedges, state.physical_links, t=t, anim_packets=True)
            elif style == "dual":
                draw_dual_graph(ax, state.hyperedges, t=t, anim_packets=True)
            elif style == "matrix":
                draw_incidence_matrix(ax, state.nodes, state.hyperedges, t=t)

            pulse_glyph = "🟢" if int(t * 2.5) % 2 == 0 else "⚪"
            title_text = f"{pulse_glyph} LIVE HYPERGRAPH [{style.upper()}] • Frame {frame}"
            if state.flash_counter > 0:
                title_text += f"  ⚡ HOT-RELOAD [{state.last_updated_str}]"
                state.flash_counter -= 1

            fig.suptitle(
                f"{title_text}\nNodes: {len(state.nodes)} | Hyperedges: {len(state.hyperedges)} | Links: {len(state.physical_links)}",
                fontsize=12, fontweight="bold", color="#38BDF8", y=0.98
            )
            plt.tight_layout(rect=[0, 0.02, 1, 0.95])
            return []

    anim = FuncAnimation(fig, update_frame, interval=interval, cache_frame_data=False)
    try:
        plt.show()
    except KeyboardInterrupt:
        pass


def plot_hypergraph(
    hypergraph_csv: str = "hypergraph.csv",
    connections_csv: str = "connections.csv",
    output_png: str = "hypergraph_plot.png",
    show_gui: bool = True,
    style: str = "dashboard",
):
    """
    Generate visualization in selected style:
    - 'dashboard' / 'all': 4-Panel Comprehensive Figure (Bipartite + Euler + Dual Line + Incidence Matrix)
    - 'bipartite': Single-Panel Bipartite Star-Hub View
    - 'euler': Single-Panel Euler Convex Hull Enclosure
    - 'dual': Single-Panel Dual Line Graph (Inter-Hyperedge Routing)
    - 'matrix': Single-Panel Incidence Matrix Heatmap
    - 'html' / 'interactive': Interactive Browser-Based HTML Explorer
    """
    hyperedges = load_hypergraph_csv(hypergraph_csv)
    physical_links = load_connections_csv(connections_csv)

    all_nodes_set: Set[str] = set()
    for e in hyperedges.values():
        all_nodes_set.update(e["members"])
    for src, tgt in physical_links:
        all_nodes_set.add(src)
        all_nodes_set.add(tgt)
    if not all_nodes_set:
        all_nodes_set = {f"Node-{i}" for i in range(1, 6)}
    nodes = sorted(all_nodes_set)

    if style in ("html", "interactive"):
        html_out = output_png.replace(".png", ".html") if output_png.endswith(".png") else output_png
        export_interactive_html(hyperedges, physical_links, nodes, output_html=html_out, show_gui=show_gui)
        return

    # 4-Panel Dashboard View
    if style in ("dashboard", "all"):
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(20, 18), dpi=150)
        fig.patch.set_facecolor("#0F172A")
        fig.suptitle("P2P HYPERGRAPH MULTI-DIMENSIONAL TOPOLOGY DASHBOARD",
                     fontsize=18, fontweight="bold", color="#F8FAFC", y=0.995)

        draw_bipartite(ax1, nodes, hyperedges, physical_links)
        draw_euler(ax2, nodes, hyperedges, physical_links)
        draw_dual_graph(ax3, hyperedges)
        draw_incidence_matrix(ax4, nodes, hyperedges)

        plt.tight_layout(rect=[0, 0.02, 1, 0.98])
        plt.savefig(output_png, dpi=180, facecolor=fig.get_facecolor(), bbox_inches="tight")
        print(f"✓ 4-Panel Dashboard plot saved to: {output_png}")

    # Single-Panel Views
    elif style == "bipartite":
        fig, ax = plt.subplots(figsize=(12, 10), dpi=160)
        fig.patch.set_facecolor("#0F172A")
        draw_bipartite(ax, nodes, hyperedges, physical_links)
        plt.tight_layout()
        plt.savefig(output_png, dpi=180, facecolor=fig.get_facecolor(), bbox_inches="tight")
        print(f"✓ Bipartite plot saved to: {output_png}")

    elif style == "euler":
        fig, ax = plt.subplots(figsize=(12, 10), dpi=160)
        fig.patch.set_facecolor("#0F172A")
        draw_euler(ax, nodes, hyperedges, physical_links)
        plt.tight_layout()
        plt.savefig(output_png, dpi=180, facecolor=fig.get_facecolor(), bbox_inches="tight")
        print(f"✓ Euler plot saved to: {output_png}")

    elif style == "dual":
        fig, ax = plt.subplots(figsize=(12, 9), dpi=160)
        fig.patch.set_facecolor("#0F172A")
        draw_dual_graph(ax, hyperedges)
        plt.tight_layout()
        plt.savefig(output_png, dpi=180, facecolor=fig.get_facecolor(), bbox_inches="tight")
        print(f"✓ Dual Line Graph plot saved to: {output_png}")

    elif style == "matrix":
        fig, ax = plt.subplots(figsize=(10, 8), dpi=160)
        fig.patch.set_facecolor("#0F172A")
        draw_incidence_matrix(ax, nodes, hyperedges)
        plt.tight_layout()
        plt.savefig(output_png, dpi=180, facecolor=fig.get_facecolor(), bbox_inches="tight")
        print(f"✓ Incidence Matrix plot saved to: {output_png}")

    if show_gui:
        try:
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
    parser.add_argument("--output", "-o", default="hypergraph_plot.png", help="Output path (PNG or HTML)")
    parser.add_argument(
        "--style", "-s",
        default="dashboard",
        choices=["dashboard", "all", "bipartite", "euler", "dual", "matrix", "html", "interactive"],
        help="Visualization layout style (default: dashboard)"
    )
    parser.add_argument("--no-gui", action="store_true", help="Do not open viewer automatically")
    parser.add_argument("--live", "-l", action="store_true", help="Launch live animated window without saving to disk")
    parser.add_argument("--interval", "-i", type=int, default=100, help="Live animation refresh interval in ms (default: 100)")
    args = parser.parse_args()

    if args.live:
        run_live_animation(
            hypergraph_csv=args.hypergraph,
            connections_csv=args.connections,
            style=args.style,
            interval=args.interval,
        )
    else:
        plot_hypergraph(
            hypergraph_csv=args.hypergraph,
            connections_csv=args.connections,
            output_png=args.output,
            show_gui=not args.no_gui,
            style=args.style,
        )


if __name__ == "__main__":
    main()

