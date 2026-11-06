"""
Hypergraph and CSV Connection Management for P2P Networks.

Supports:
1. Hypergraph representation: Hyperedges connecting N nodes simultaneously
   (multicast clusters, consensus quorums, data shards).
2. CSV persistence:
   - hypergraph.csv: persists multi-node hyperedge group definitions.
   - connections.csv: persists current pairwise physical topology links.
   - connection_events.csv: append-only audit log for connection events.
"""

import os
import csv
import time
from typing import Dict, List, Set, Optional, Any

from p2p.protocol import Colors, colorize


class HypergraphManager:
    """
    Manages hyperedges where each edge connects any number of nodes (>= 1).
    Used for multi-node multicast groups, consensus quorums, and sharded clusters.
    """

    def __init__(self, default_csv: str = "hypergraph.csv"):
        self.default_csv = default_csv
        # hyperedge_id -> {"id": str, "name": str, "members": Set[str], "description": str, "created_at": float}
        self.hyperedges: Dict[str, dict] = {}

    def add_hyperedge(
        self,
        edge_id: str,
        members: List[str],
        name: str = "",
        description: str = "",
    ) -> dict:
        """Add or update a hyperedge connecting multiple nodes."""
        edge_id = str(edge_id).strip()
        cleaned_members = {str(m).strip() for m in members if str(m).strip()}
        edge_data = {
            "id": edge_id,
            "name": name.strip() or f"Group-{edge_id}",
            "members": cleaned_members,
            "description": description.strip() or "P2P Hyperedge Cluster",
            "created_at": time.time(),
        }
        self.hyperedges[edge_id] = edge_data
        return edge_data

    def remove_hyperedge(self, edge_id: str) -> bool:
        """Remove a hyperedge by ID."""
        if edge_id in self.hyperedges:
            del self.hyperedges[edge_id]
            return True
        return False

    def add_member(self, edge_id: str, node_id: str) -> bool:
        """Add a single node to an existing hyperedge."""
        if edge_id in self.hyperedges:
            self.hyperedges[edge_id]["members"].add(str(node_id).strip())
            return True
        return False

    def remove_member(self, edge_id: str, node_id: str) -> bool:
        """Remove a single node from a hyperedge."""
        if edge_id in self.hyperedges:
            self.hyperedges[edge_id]["members"].discard(str(node_id).strip())
            return True
        return False

    def get_members(self, edge_id: str) -> Set[str]:
        """Get set of member node IDs belonging to hyperedge."""
        if edge_id in self.hyperedges:
            return set(self.hyperedges[edge_id]["members"])
        return set()

    def get_hyperedge(self, edge_id: str) -> Optional[dict]:
        """Get hyperedge metadata dictionary."""
        return self.hyperedges.get(edge_id)

    def get_all_hyperedges(self) -> Dict[str, dict]:
        """Return all defined hyperedges."""
        return self.hyperedges

    def get_node_hyperedges(self, node_id: str) -> List[dict]:
        """Find all hyperedges that include the given node."""
        node_id = str(node_id).strip()
        return [e for e in self.hyperedges.values() if node_id in e["members"]]

    # -----------------------------------------------------------------------
    # CSV Persistence: hypergraph.csv
    # -----------------------------------------------------------------------
    def save_to_csv(self, filepath: Optional[str] = None) -> int:
        """
        Save all hyperedges to CSV.
        Format: hyperedge_id,group_name,member_nodes,description,created_at
        """
        target_path = filepath or self.default_csv
        with open(target_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["hyperedge_id", "group_name", "member_nodes", "description", "created_at"])
            for edge_id, data in self.hyperedges.items():
                members_str = ",".join(sorted(data["members"]))
                writer.writerow([
                    edge_id,
                    data.get("name", ""),
                    members_str,
                    data.get("description", ""),
                    f"{data.get('created_at', time.time()):.2f}",
                ])
        return len(self.hyperedges)

    def load_from_csv(self, filepath: Optional[str] = None) -> int:
        """Load hyperedges from CSV."""
        target_path = filepath or self.default_csv
        if not os.path.exists(target_path):
            return 0

        loaded_count = 0
        with open(target_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                edge_id = row.get("hyperedge_id", "").strip()
                if not edge_id:
                    continue
                name = row.get("group_name", "").strip()
                desc = row.get("description", "").strip()
                raw_members = row.get("member_nodes", "").split(",")
                members = [m.strip() for m in raw_members if m.strip()]
                created_at = float(row.get("created_at", time.time()) or time.time())

                self.hyperedges[edge_id] = {
                    "id": edge_id,
                    "name": name or f"Group-{edge_id}",
                    "members": set(members),
                    "description": desc,
                    "created_at": created_at,
                }
                loaded_count += 1
        return loaded_count

    def print_hyperedges_table(self):
        """Display an ASCII table of all defined hyperedges."""
        if not self.hyperedges:
            print(colorize("No hyperedges currently defined.", Colors.YELLOW))
            return

        print("\n" + "=" * 80)
        print(colorize("               🌐  HYPERGRAPH CLUSTERS & GROUPS  🌐", Colors.BOLD + Colors.CYAN))
        print("=" * 80)
        print(f" {'ID':<8} {'NAME':<18} {'MEMBERS COUNT':<15} {'MEMBER NODES'}")
        print("-" * 80)
        for edge_id, data in sorted(self.hyperedges.items()):
            members_str = ", ".join(sorted(data["members"])) or colorize("(empty)", Colors.DIM)
            count = len(data["members"])
            print(f" {colorize(edge_id, Colors.BOLD + Colors.GREEN):<17} {data['name']:<18} {count:<15} {members_str}")
        print("=" * 80 + "\n")


class TopologyCSVManager:
    """
    Manages CSV logging and export/import of pairwise physical node connections.
    """

    @staticmethod
    def log_event(
        source_id: str,
        target_id: str,
        host: str,
        port: int,
        direction: str,
        status: str,
        filepath: str = "connection_events.csv",
    ):
        """Append an event to connection_events.csv log."""
        file_exists = os.path.exists(filepath)
        try:
            with open(filepath, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["timestamp", "datetime", "source_node", "target_node", "host", "port", "direction", "status"])
                now = time.time()
                dt_str = time.strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([f"{now:.2f}", dt_str, source_id, target_id, host, port, direction, status])
        except Exception:
            pass

    @staticmethod
    def export_topology_to_csv(nodes_dict: dict, filepath: str = "connections.csv") -> int:
        """
        Export current active physical connections across all running nodes.
        Deduplicates bidirectional links so each physical link is represented clearly.
        Format: source_node,target_node,target_host,target_port,direction,latency_ms,status,timestamp
        """
        seen_pairs = set()
        rows = []
        now = time.time()

        for src_name, node in nodes_dict.items():
            peers = node.get_connected_peers()
            for tgt_id, p_info in peers.items():
                # Store unique undirected links to avoid duplicate inverted rows if desired,
                # but keep directional info
                link_key = tuple(sorted([src_name, tgt_id]))
                if link_key in seen_pairs:
                    continue
                seen_pairs.add(link_key)

                lat = f"{p_info['latency_ms']:.2f}" if p_info.get("latency_ms") is not None else ""
                rows.append([
                    src_name,
                    tgt_id,
                    p_info.get("host", "127.0.0.1"),
                    p_info.get("port", 0),
                    p_info.get("direction", "active"),
                    lat,
                    "connected",
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                ])

        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["source_node", "target_node", "target_host", "target_port", "direction", "latency_ms", "status", "timestamp"])
            writer.writerows(rows)

        return len(rows)

    @staticmethod
    def import_topology_from_csv(filepath: str = "connections.csv") -> List[dict]:
        """
        Read topology connections from CSV.
        Returns list of connection specifications:
        [{"source": "Node-1", "target": "Node-2", "host": "127.0.0.1", "port": 8002}, ...]
        """
        if not os.path.exists(filepath):
            return []

        connections = []
        with open(filepath, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                src = row.get("source_node", "").strip()
                tgt = row.get("target_node", "").strip()
                host = row.get("target_host", "127.0.0.1").strip() or "127.0.0.1"
                port = int(row.get("target_port", 0) or 0)
                if src and tgt:
                    connections.append({
                        "source": src,
                        "target": tgt,
                        "host": host,
                        "port": port,
                        "status": row.get("status", "connected"),
                    })
        return connections

