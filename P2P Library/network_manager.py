#!/usr/bin/env python3
"""
P2P Network Manager & Interactive Terminal Orchestrator.
Allows you to spin up 4 to 5 nodes in one terminal, inspect their status,
connect them in mesh/ring/star topologies, and test direct messaging,
broadcasts, and ping latencies.
"""

import sys
import os
import time
import threading
import shlex
import re
import subprocess
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    import readline
except ImportError:
    pass

from p2p.node import EnhancedNode
from p2p.protocol import Colors, colorize
from p2p.hypergraph import HypergraphManager, TopologyCSVManager


class NetworkManager:
    def __init__(self, host: str = "127.0.0.1", base_port: int = 8001):
        self.host = host
        self.base_port = base_port
        self.nodes: Dict[str, EnhancedNode] = {}
        self.lock = threading.Lock()
        self.running = True
        self.msg_logs: List[str] = []
        self.hypergraph = HypergraphManager("hypergraph.csv")
        # Load existing hyperedges if file exists
        self.hypergraph.load_from_csv()

    def _on_log(self, msg: str, level: str):
        # We store logs to keep terminal neat unless user requests verbose logs
        self.msg_logs.append(msg)
        if len(self.msg_logs) > 500:
            self.msg_logs.pop(0)

    # -----------------------------------------------------------------------
    # Node Lifecycle: Spawn, Stop, Kill, Revive
    # -----------------------------------------------------------------------
    def spawn_nodes(self, count: int = 5):
        """Spawn N nodes on consecutive ports starting from base_port."""
        if count < 2:
            print(colorize("Please spawn at least 2 nodes.", Colors.RED))
            return
        if count > 10:
            print(colorize("Maximum recommended nodes for local test is 10.", Colors.YELLOW))

        print(colorize(f"\n🚀 Spawning {count} P2P Nodes...", Colors.BOLD + Colors.CYAN))
        for i in range(1, count + 1):
            name = f"Node-{i}"
            port = self.base_port + (i - 1)

            if name in self.nodes:
                print(colorize(f"  • {name} already exists on port {self.nodes[name].port}. Skipping.", Colors.YELLOW))
                continue

            try:
                node = EnhancedNode(
                    host=self.host,
                    port=port,
                    node_id=name,
                    on_log_callback=self._on_log,
                )
                node.start()
                self.nodes[name] = node
                print(colorize(f"  ✓ Started {name} listening on {self.host}:{port}", Colors.GREEN))
            except OSError as e:
                if e.errno == 48:
                    print(colorize(f"  ✗ Port {port} is already in use by another running terminal or process.", Colors.RED))
                    print(colorize(f"    (Tip: Stop the previous node or terminal running on port {port})", Colors.YELLOW))
                else:
                    print(colorize(f"  ✗ Error starting {name} on port {port}: {e}", Colors.RED))

        time.sleep(0.5)
        print(colorize(f"All {len(self.nodes)} nodes are online and ready!\n", Colors.BOLD + Colors.GREEN))

    def stop_all(self):
        """Stop and terminate all running nodes cleanly."""
        if not self.nodes:
            print(colorize("No nodes currently running.", Colors.YELLOW))
            return

        print(colorize(f"\n🛑 Stopping {len(self.nodes)} nodes...", Colors.YELLOW))
        for name, node in list(self.nodes.items()):
            try:
                node.stop()
                print(colorize(f"  ✓ Stopped {name}", Colors.DIM))
            except Exception as e:
                print(colorize(f"  ✗ Error stopping {name}: {e}", Colors.RED))
        self.nodes.clear()
        print(colorize("All nodes stopped cleanly.\n", Colors.GREEN))

    def kill_node(self, node_id: str):
        """Simulate a node crash or abrupt failure."""
        if node_id not in self.nodes:
            print(colorize(f"Node '{node_id}' does not exist.", Colors.RED))
            return
        node = self.nodes.pop(node_id)
        node.stop()
        print(colorize(f"💥 {node_id} (port {node.port}) was killed to test network resilience.", Colors.RED))

    def revive_node(self, node_id: str):
        """Revive a previously killed node on its original port."""
        if node_id in self.nodes:
            print(colorize(f"Node '{node_id}' is already running.", Colors.YELLOW))
            return
        # Infer port from ID: Node-3 -> base_port + 2
        try:
            num = int(node_id.replace("Node-", ""))
            port = self.base_port + (num - 1)
        except Exception:
            port = self.base_port + len(self.nodes)

        node = EnhancedNode(host=self.host, port=port, node_id=node_id, on_log_callback=self._on_log)
        node.start()
        self.nodes[node_id] = node
        print(colorize(f"✨ Revived {node_id} on port {port}!", Colors.GREEN))

    # -----------------------------------------------------------------------
    # Topology & Connections
    # -----------------------------------------------------------------------
    def connect_pair(self, from_id: str, to_id: str) -> bool:
        """Connect from_id to to_id."""
        if from_id not in self.nodes:
            print(colorize(f"Source '{from_id}' not found.", Colors.RED))
            return False
        if to_id not in self.nodes:
            print(colorize(f"Target '{to_id}' not found.", Colors.RED))
            return False
        if from_id == to_id:
            print(colorize("Cannot connect a node to itself.", Colors.YELLOW))
            return False

        src = self.nodes[from_id]
        tgt = self.nodes[to_id]
        ok = src.connect(tgt.host, tgt.port)
        if ok:
            print(colorize(f"✓ Connected {from_id} -> {to_id} ({tgt.host}:{tgt.port})", Colors.GREEN))
        else:
            print(colorize(f"✗ Failed to connect {from_id} -> {to_id}", Colors.RED))
        return ok

    def setup_topology(self, topo_type: str):
        """Build Ring, Mesh, or Star network topology."""
        node_names = list(self.nodes.keys())
        n = len(node_names)
        if n < 2:
            print(colorize("Need at least 2 nodes to form a topology. Run 'spawn 5' first.", Colors.RED))
            return

        topo = topo_type.lower()
        print(colorize(f"\n🔗 Constructing '{topo.upper()}' topology across {n} nodes...", Colors.BOLD + Colors.CYAN))

        if topo == "ring":
            # 1 -> 2 -> 3 -> 4 -> 5 -> 1
            for i in range(n):
                src = self.nodes[node_names[i]]
                tgt = self.nodes[node_names[(i + 1) % n]]
                src.connect(tgt.host, tgt.port)
            print(colorize("✓ Ring topology established! (Each node connected in a closed loop)", Colors.GREEN))

        elif topo == "mesh":
            # Every node connects to all subsequent nodes (full duplex coverage)
            count = 0
            for i in range(n):
                for j in range(i + 1, n):
                    src = self.nodes[node_names[i]]
                    tgt = self.nodes[node_names[j]]
                    src.connect(tgt.host, tgt.port)
                    count += 1
            print(colorize(f"✓ Full Mesh topology established with {count} peer links!", Colors.GREEN))

        elif topo == "star":
            # Hub is Node-1, all others connect to it
            hub = self.nodes[node_names[0]]
            for i in range(1, n):
                spoke = self.nodes[node_names[i]]
                spoke.connect(hub.host, hub.port)
            print(colorize(f"✓ Star topology established! Hub: [{node_names[0]}]", Colors.GREEN))

        else:
            print(colorize(f"Unknown topology '{topo_type}'. Options: ring, mesh, star", Colors.RED))
            return

        time.sleep(0.5)
        print()

    # -----------------------------------------------------------------------
    # Status & Inspection (Check)
    # -----------------------------------------------------------------------
    def print_status(self):
        """Display an ASCII dashboard table of all nodes and their connections."""
        if not self.nodes:
            print(colorize("\nNo nodes currently running. Use 'spawn 5' to start nodes.\n", Colors.YELLOW))
            return

        print("\n" + "=" * 80)
        print(colorize("           🌐  P2P NETWORK STATUS DASHBOARD  🌐", Colors.BOLD + Colors.CYAN))
        print("=" * 80)
        print(f" {'NODE':<10} {'PORT':<8} {'INBOUND':<10} {'OUTBOUND':<10} {'TOTAL':<8} {'CONNECTED PEERS'}")
        print("-" * 80)

        for name, node in self.nodes.items():
            peers = node.get_connected_peers()
            peer_list_str = ", ".join(peers.keys()) if peers else colorize("None", Colors.DIM)
            in_count = len(node.nodes_inbound)
            out_count = len(node.nodes_outbound)
            total = len(peers)
            print(f" {colorize(name, Colors.BOLD + Colors.GREEN):<19} {node.port:<8} {in_count:<10} {out_count:<10} {total:<8} {peer_list_str}")

        print("=" * 80)
        print(colorize(f"Total Nodes: {len(self.nodes)} | Host: {self.host}\n", Colors.DIM))

    # -----------------------------------------------------------------------
    # Testing & Verification
    # -----------------------------------------------------------------------
    def ping_pair(self, from_id: str, to_id: str):
        """Ping to_id from from_id."""
        if from_id not in self.nodes:
            print(colorize(f"Node '{from_id}' not found.", Colors.RED))
            return
        node = self.nodes[from_id]
        print(colorize(f"Pinging [{to_id}] from [{from_id}]...", Colors.YELLOW))
        rtt = node.ping(to_id)
        if rtt is not None:
            print(colorize(f"✓ Pong from [{to_id}] to [{from_id}]: {rtt:.2f} ms", Colors.GREEN))
        else:
            print(colorize(f"✗ Ping from [{from_id}] to [{to_id}] timed out or not directly connected.", Colors.RED))

    def ping_matrix(self):
        """Measure round-trip time between all directly connected pairs."""
        if not self.nodes:
            print(colorize("No nodes running.", Colors.YELLOW))
            return

        print(colorize("\n📊 Running Ping Latency Matrix...", Colors.BOLD + Colors.CYAN))
        results = []
        for src_name, src_node in self.nodes.items():
            peers = src_node.get_connected_peers()
            for tgt_id in peers:
                rtt = src_node.ping(tgt_id, timeout=1.5)
                results.append((src_name, tgt_id, rtt))

        print("\n" + "-" * 55)
        print(f" {'FROM':<12} {'TO':<12} {'STATUS':<12} {'LATENCY'}")
        print("-" * 55)
        for src, tgt, rtt in results:
            if rtt is not None:
                stat = colorize("OK", Colors.GREEN)
                lat = f"{rtt:.2f} ms"
            else:
                stat = colorize("TIMEOUT", Colors.RED)
                lat = "--"
            print(f" {src:<12} {tgt:<12} {stat:<21} {lat}")
        print("-" * 55 + "\n")

    def send_direct_msg(self, from_id: str, to_id: str, text: str):
        """Send direct chat message."""
        if from_id not in self.nodes:
            print(colorize(f"Node '{from_id}' not found.", Colors.RED))
            return
        src = self.nodes[from_id]
        ok = src.send_direct(to_id, text)
        if ok:
            time.sleep(0.2)
            # Verify target received it
            if to_id in self.nodes:
                tgt = self.nodes[to_id]
                recent = [m for m in tgt.received_messages if m.get("payload") == text]
                if recent:
                    print(colorize(f"✓ Delivered! [{to_id}] confirmed receipt of: \"{text}\"", Colors.GREEN))
                else:
                    print(colorize(f"Message sent to socket, waiting for reception on [{to_id}]...", Colors.YELLOW))

    def broadcast_msg(self, from_id: str, text: str):
        """Broadcast message from a node to all its peers."""
        if from_id not in self.nodes:
            print(colorize(f"Node '{from_id}' not found.", Colors.RED))
            return
        src = self.nodes[from_id]
        count = src.broadcast(text)
        print(colorize(f"✓ Broadcast sent from [{from_id}] to {count} connected peer(s).", Colors.GREEN))
        time.sleep(0.3)
        # Check who got it
        recipients = []
        for name, node in self.nodes.items():
            if name != from_id:
                if any(m.get("payload") == text and m.get("sender_id") == from_id for m in node.received_messages):
                    recipients.append(name)
        if recipients:
            print(colorize(f"  Received by: {', '.join(recipients)}", Colors.CYAN))

    # -----------------------------------------------------------------------
    # Hypergraph Management & Multicast
    # -----------------------------------------------------------------------
    def setup_default_hyperedges(self):
        """Pre-populate sample hyperedges if none exist."""
        if not self.hypergraph.hyperedges and len(self.nodes) >= 3:
            all_names = list(self.nodes.keys())
            h1_members = all_names[:3]  # Node-1, Node-2, Node-3
            self.hypergraph.add_hyperedge(
                edge_id="H1",
                members=h1_members,
                name="Consensus_Quorum",
                description="Fast 3-node voting cluster",
            )
            if len(all_names) >= 5:
                h2_members = all_names[1:5]  # Node-2, Node-3, Node-4, Node-5
                self.hypergraph.add_hyperedge(
                    edge_id="H2",
                    members=h2_members,
                    name="Storage_Shard_A",
                    description="4-node distributed replica set",
                )
            self.hypergraph.save_to_csv()
            print(colorize("✓ Created default Hyperedges (H1: Consensus Quorum, H2: Storage Shard)", Colors.GREEN))

    def multicast_hyperedge(self, edge_id: str, sender_id: str, text: str):
        """Send a message to all members of a specific hyperedge."""
        edge = self.hypergraph.get_hyperedge(edge_id)
        if not edge:
            print(colorize(f"Hyperedge '{edge_id}' does not exist. Use 'hyper list' to see available groups.", Colors.RED))
            return

        members = edge["members"]
        if sender_id not in members:
            print(colorize(f"Warning: Sender [{sender_id}] is not a member of hyperedge [{edge_id}]! (Members: {', '.join(members)})", Colors.YELLOW))

        if sender_id not in self.nodes:
            print(colorize(f"Node '{sender_id}' is not online.", Colors.RED))
            return

        sender_node = self.nodes[sender_id]
        count = sender_node.send_hyper_multicast(edge_id, members, text)
        time.sleep(0.3)

        # Verify receipt among online member nodes
        received_by = []
        for mid in members:
            if mid != sender_id and mid in self.nodes:
                target_node = self.nodes[mid]
                if any(m.get("payload") == text and m.get("hyperedge_id") == edge_id for m in target_node.received_messages):
                    received_by.append(mid)

        print(colorize(f"✓ Hyperedge [{edge_id} - {edge['name']}] message delivered to {len(received_by)} member(s): {', '.join(received_by)}", Colors.GREEN))

    # -----------------------------------------------------------------------
    # CSV Topology Import / Export
    # -----------------------------------------------------------------------
    def export_topology_csv(self, filepath: str = "connections.csv") -> int:
        """Export snapshot of current pairwise connections to CSV."""
        if not self.nodes:
            print(colorize("No nodes online to export.", Colors.YELLOW))
            return 0
        count = TopologyCSVManager.export_topology_to_csv(self.nodes, filepath)
        print(colorize(f"✓ Exported {count} physical connections to '{filepath}'.", Colors.GREEN))
        return count

    def load_topology_csv(self, filepath: str = "connections.csv") -> int:
        """Read CSV file and establish the recorded physical socket links."""
        links = TopologyCSVManager.import_topology_from_csv(filepath)
        if not links:
            print(colorize(f"No connections found in '{filepath}'.", Colors.YELLOW))
            return 0

        print(colorize(f"\n📂 Loading {len(links)} connection(s) from '{filepath}'...", Colors.BOLD + Colors.CYAN))
        connected_count = 0
        for item in links:
            src = item["source"]
            tgt = item["target"]
            if src in self.nodes and tgt in self.nodes:
                ok = self.connect_pair(src, tgt)
                if ok:
                    connected_count += 1
            else:
                print(colorize(f"  • Cannot connect {src} -> {tgt}: one or both nodes not spawned.", Colors.YELLOW))

        time.sleep(0.5)
        print(colorize(f"✓ Restored {connected_count} connection links from CSV!\n", Colors.GREEN))
        return connected_count

    # -----------------------------------------------------------------------
    # Hypergraph Command Handlers (Supports both 'hyper create' and 'create')
    # -----------------------------------------------------------------------
    def _handle_hyper_create(self, args: List[str]):
        """Handle creating a hyperedge from various argument formats."""
        if len(args) < 2:
            print(colorize("Usage: hyper create <id> <node1,node2,...> [name] [description]", Colors.RED))
            print(colorize("   OR: create <id> <node1,node2,...> [name]", Colors.YELLOW))
            return
        edge_id = args[0]
        raw_members = args[1]

        # Support both comma-separated ("Node-1,Node-2,Node-3") and space-separated ("Node-1 Node-2 Node-3")
        if "," in raw_members:
            members = [m.strip() for m in raw_members.split(",") if m.strip()]
            name = args[2] if len(args) > 2 else f"Group-{edge_id}"
            desc = " ".join(args[3:]) if len(args) > 3 else "Custom Hyperedge"
        else:
            member_list = [raw_members]
            remaining = []
            for item in args[2:]:
                if item.startswith("Node-") or item in self.nodes:
                    member_list.append(item)
                else:
                    remaining.append(item)
            members = member_list
            name = " ".join(remaining) if remaining else f"Group-{edge_id}"
            desc = "Custom Hyperedge"

        self.hypergraph.add_hyperedge(edge_id, members, name=name, description=desc)
        self.hypergraph.save_to_csv()
        print(colorize(f"✓ Created hyperedge '{edge_id}' ({name}) with members: {', '.join(members)}", Colors.GREEN))

    def _handle_hyper_send(self, args: List[str]):
        """Handle sending a multicast message across a hyperedge."""
        if len(args) < 3:
            print(colorize("Usage: hyper send <edge_id> <sender_node> <message>", Colors.RED))
            print(colorize("   OR: hypersend <edge_id> <sender_node> <message>", Colors.YELLOW))
            return
        edge_id = args[0]
        sender_id = args[1]
        raw_msg = " ".join(args[2:])
        if (raw_msg.startswith('"') and raw_msg.endswith('"')) or (raw_msg.startswith("'") and raw_msg.endswith("'")):
            raw_msg = raw_msg[1:-1]
        self.multicast_hyperedge(edge_id, sender_id, raw_msg)

    def _handle_hyper_node(self, args: List[str]):
        """Show hyperedges that include the specified node."""
        if not args:
            print(colorize("Usage: hyper node <node_id>", Colors.RED))
            return
        node_id = args[0]
        edges = self.hypergraph.get_node_hyperedges(node_id)
        if not edges:
            print(colorize(f"[{node_id}] does not belong to any hyperedge.", Colors.YELLOW))
        else:
            print(colorize(f"\n--- Hyperedges for [{node_id}] ---", Colors.BOLD))
            for e in edges:
                print(f"  • {colorize(e['id'], Colors.GREEN)} ({e['name']}): {', '.join(e['members'])}")
            print()

    def _handle_hyper_remove(self, args: List[str]):
        """Remove a hyperedge by ID."""
        if not args:
            print(colorize("Usage: hyper remove <edge_id>", Colors.RED))
            return
        edge_id = args[0]
        ok = self.hypergraph.remove_hyperedge(edge_id)
        if ok:
            self.hypergraph.save_to_csv()
            print(colorize(f"✓ Removed hyperedge '{edge_id}'.", Colors.GREEN))
        else:
            print(colorize(f"Hyperedge '{edge_id}' not found.", Colors.RED))

    def _handle_hyper_save(self, args: List[str]):
        target_file = args[0] if args else "hypergraph.csv"
        count = self.hypergraph.save_to_csv(target_file)
        print(colorize(f"✓ Saved {count} hyperedge(s) to '{target_file}'.", Colors.GREEN))

    def _handle_hyper_load(self, args: List[str]):
        target_file = args[0] if args else "hypergraph.csv"
        count = self.hypergraph.load_from_csv(target_file)
        print(colorize(f"✓ Loaded {count} hyperedge(s) from '{target_file}'.", Colors.GREEN))

    def plot_hypergraph_visualization(self, output_png: str = "hypergraph_plot.png"):
        """Generate and display visual hypergraph plot using Matplotlib & NetworkX."""
        self.hypergraph.save_to_csv("hypergraph.csv")
        self.export_topology_csv("connections.csv")

        script_path = os.path.join(os.path.dirname(__file__), "visualize_hypergraph.py")
        venv_python = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python")
        python_bin = venv_python if os.path.exists(venv_python) else sys.executable

        try:
            subprocess.run([python_bin, script_path, "--output", output_png], check=True)
            print(colorize(f"✓ Visual hypergraph plot generated: '{output_png}'", Colors.GREEN))
        except Exception as e:
            print(colorize(f"Error generating plot: {e}", Colors.RED))

    def _parse_line(self, raw_line: str) -> Tuple[Optional[str], List[str]]:
        """
        Intelligently parses user input lines.
        Handles glued paste text (e.g. 'View all defined Hyperedgeshyper list'),
        ignores comment/instruction lines, and supports standard command syntax.
        """
        line = raw_line.strip()
        if not line:
            return None, []

        # If user pasted comments like "# 1. ...", strip leading prefix
        if line.startswith("#") or line.startswith("//"):
            line = re.sub(r"^[#/]+\s*", "", line).strip()
            if not line:
                return None, []

        # Specific regex patterns for extracting real commands from pasted text
        command_patterns = [
            ("hyper_sub", r"hyper\s+(?:list|show|create|send|node|nodes|remove|delete|save|load)\b.*"),
            ("create_edge", r"(?:hyper\s+)?create\s+[A-Za-z0-9_]+\s+[A-Za-z0-9_,\-]+(?:,|Node)[A-Za-z0-9_,\-]*.*"),
            ("load_csv", r"load_csv\b.*"),
            ("export_csv", r"export_csv\b.*"),
            ("hypersend", r"hypersend\b.*"),
            ("hyperlist", r"hyperlist\b"),
            ("hypernode", r"hypernode\b.*"),
            ("spawn", r"spawn\s+\d+"),
            ("topology", r"topology\s+(?:mesh|ring|star)\b"),
            ("broadcast", r"broadcast\b.*"),
            ("ping_all", r"ping_all\b"),
            ("ping", r"ping\s+\S+"),
            ("check", r"check\b"),
            ("status", r"status\b"),
            ("peers", r"peers\b"),
            ("plot", r"(?:hyper\s+)?(?:plot|visualize)\b.*"),
            ("test", r"test\b"),
            ("help", r"help\b"),
            ("exit", r"exit\b"),
            ("quit", r"quit\b"),
        ]

        # Check for commands embedded in line
        for cmd_type, pattern in command_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                cmd_str = line[match.start():].strip()
                try:
                    parts = shlex.split(cmd_str)
                except ValueError:
                    parts = cmd_str.split()
                if parts:
                    return parts[0].lower(), parts[1:]

        # Handle user typing or pasting "view ..." (e.g. "View all defined Hyperedges" or "view hyper")
        parts = line.split()
        if parts and parts[0].lower() in ("view", "show"):
            # If user ran "view ...", show hyperedges table or status
            if len(parts) > 1 and parts[1].lower() in ("status", "nodes", "dashboard", "peers"):
                return "check", []
            return "hyper", ["list"]

        # If line looks like human instruction / prose without commands (e.g. "Start 5 nodes and connect them")
        if re.match(r"^(start|multicast|save|disconnect|step|\d+[\.\)])\b", line, re.IGNORECASE):
            return "COMMENT", [line]

        # Standard fallback parse
        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()

        return (parts[0].lower(), parts[1:]) if parts else (None, [])

        return (parts[0].lower(), parts[1:]) if parts else (None, [])

    def run_automated_suite(self):
        """Comprehensive automated test for 5 nodes."""
        print(colorize("\n" + "=" * 65, Colors.BOLD + Colors.CYAN))
        print(colorize("   🧪 RUNNING AUTOMATED P2P NETWORK TEST SUITE 🧪", Colors.BOLD + Colors.CYAN))
        print(colorize("=" * 65 + "\n", Colors.BOLD + Colors.CYAN))

        # Step 1: Ensure 5 nodes
        if len(self.nodes) < 5:
            self.stop_all()
            self.spawn_nodes(5)
        time.sleep(0.5)

        # Step 2: Establish mesh topology
        print(colorize("[TEST 1/5] Setting up Full Mesh Topology...", Colors.BOLD))
        self.setup_topology("mesh")
        time.sleep(0.5)

        # Step 3: Verify connectivity
        print(colorize("[TEST 2/5] Checking Node Connection Counts...", Colors.BOLD))
        all_connected = True
        for name, node in self.nodes.items():
            peer_count = len(node.get_connected_peers())
            if peer_count != 4:  # In 5-node mesh, each node has 4 peers
                print(colorize(f"  ✗ {name} has {peer_count} peers (expected 4)", Colors.RED))
                all_connected = False
            else:
                print(colorize(f"  ✓ {name} has {peer_count}/4 peer connections", Colors.GREEN))

        # Step 4: Ping / Pong latency check
        print(colorize("\n[TEST 3/5] Testing Ping/Pong Latency...", Colors.BOLD))
        ping_ok = True
        pairs = [("Node-1", "Node-2"), ("Node-2", "Node-4"), ("Node-5", "Node-1"), ("Node-3", "Node-5")]
        for src, tgt in pairs:
            rtt = self.nodes[src].ping(tgt, timeout=2.0)
            if rtt is not None and rtt < 100:
                print(colorize(f"  ✓ Ping {src} -> {tgt}: {rtt:.2f} ms", Colors.GREEN))
            else:
                print(colorize(f"  ✗ Ping {src} -> {tgt} failed or high latency", Colors.RED))
                ping_ok = False

        # Step 5: Direct messaging
        print(colorize("\n[TEST 4/5] Testing Direct Messaging...", Colors.BOLD))
        test_msg = "Secret handshake #42"
        self.nodes["Node-1"].send_direct("Node-3", test_msg)
        time.sleep(0.3)
        msg_delivered = any(m.get("payload") == test_msg for m in self.nodes["Node-3"].received_messages)
        if msg_delivered:
            print(colorize(f"  ✓ Direct message verified: Node-1 -> Node-3: \"{test_msg}\"", Colors.GREEN))
        else:
            print(colorize("  ✗ Direct message was not received by Node-3", Colors.RED))

        # Step 6: Broadcast verification
        print(colorize("\n[TEST 5/5] Testing Network Broadcast...", Colors.BOLD))
        bcast_payload = "Alert: Network update v2"
        self.nodes["Node-4"].broadcast(bcast_payload)
        time.sleep(0.4)
        received_by = [
            n_name for n_name, n in self.nodes.items()
            if n_name != "Node-4" and any(m.get("payload") == bcast_payload for m in n.received_messages)
        ]
        bcast_ok = len(received_by) == 4
        if bcast_ok:
            print(colorize(f"  ✓ Broadcast from Node-4 received by all 4 peers: {', '.join(received_by)}", Colors.GREEN))
        else:
            print(colorize(f"  ✗ Broadcast received only by {len(received_by)}/4 nodes", Colors.RED))

        # Summary
        print("\n" + "=" * 65)
        passed = sum([all_connected, ping_ok, msg_delivered, bcast_ok])
        if passed == 4:
            print(colorize(f"🎉 ALL CORE TESTS PASSED (4/4)! Network is fully operational.", Colors.BOLD + Colors.GREEN))
        else:
            print(colorize(f"⚠️  {passed}/4 tests passed. See details above.", Colors.BOLD + Colors.YELLOW))

        # Step 7: Hypergraph Multicast Test
        print(colorize("\n[TEST 6/7] Testing Hypergraph Multi-Node Multicast...", Colors.BOLD))
        self.hypergraph.add_hyperedge(
            edge_id="H_TEST",
            members=["Node-1", "Node-2", "Node-3"],
            name="Test_Cluster",
            description="3-node multicast test group",
        )
        self.hypergraph.save_to_csv()
        hyper_payload = "Hypergraph Quorum Directive #101"
        self.multicast_hyperedge("H_TEST", "Node-1", hyper_payload)
        time.sleep(0.4)

        # Node-2 and Node-3 should have it
        recv_n2 = any(m.get("payload") == hyper_payload for m in self.nodes["Node-2"].received_messages)
        recv_n3 = any(m.get("payload") == hyper_payload for m in self.nodes["Node-3"].received_messages)
        # Node-4 and Node-5 should NOT have it
        recv_n4 = any(m.get("payload") == hyper_payload for m in self.nodes["Node-4"].received_messages)
        recv_n5 = any(m.get("payload") == hyper_payload for m in self.nodes["Node-5"].received_messages)

        hyper_ok = recv_n2 and recv_n3 and (not recv_n4) and (not recv_n5)
        if hyper_ok:
            print(colorize("  ✓ Hypergraph multicast verified: delivered ONLY to H_TEST members (Node-2, Node-3)!", Colors.GREEN))
            print(colorize("  ✓ Non-members (Node-4, Node-5) correctly excluded.", Colors.GREEN))
        else:
            print(colorize("  ✗ Hypergraph multicast routing verification failed.", Colors.RED))

        # Step 8: CSV Export & Import Test
        print(colorize("\n[TEST 7/7] Testing CSV Topology Export and Import...", Colors.BOLD))
        test_csv = "test_connections.csv"
        exported_count = self.export_topology_csv(test_csv)
        csv_file_ok = os.path.exists(test_csv) and exported_count > 0

        # Read back
        imported_links = TopologyCSVManager.import_topology_from_csv(test_csv)
        csv_import_ok = len(imported_links) == exported_count

        if csv_file_ok and csv_import_ok:
            print(colorize(f"  ✓ Exported & verified {exported_count} active connection links via CSV!", Colors.GREEN))
        else:
            print(colorize("  ✗ CSV topology export/import mismatch.", Colors.RED))

        total_all_passed = passed + int(hyper_ok) + int(csv_file_ok and csv_import_ok)
        print("\n" + "=" * 65)
        print(colorize(f"🏁 FINAL SUITE RESULT: {total_all_passed}/6 CHECKS PASSED", Colors.BOLD + (Colors.GREEN if total_all_passed == 6 else Colors.YELLOW)))
        print("=" * 65 + "\n")

    # -----------------------------------------------------------------------
    # Interactive Terminal Loop
    # -----------------------------------------------------------------------
    def start_cli(self):
        banner = f"""
{Colors.CYAN}{Colors.BOLD}======================================================================
  🎛️  P2P MULTI-NODE TERMINAL MANAGER & HYPERGRAPH
  Control, Connect, and Test 4 to 5 Nodes from One Terminal
======================================================================{Colors.RESET}
Basic Controls:
  • {colorize("spawn 5", Colors.GREEN)}               - Spin up 5 nodes (Node-1..Node-5 on ports 8001..8005)
  • {colorize("topology mesh", Colors.GREEN)}         - Interconnect all 5 nodes in a Full Mesh
  • {colorize("topology ring", Colors.GREEN)}         - Interconnect nodes in a Ring (1->2->3->4->5->1)
  • {colorize("check / status", Colors.GREEN)}        - View live connection dashboard of all nodes
  • {colorize("send Node-1 Node-3 <msg>", Colors.GREEN)} - Send message from Node-1 to Node-3
  • {colorize("broadcast Node-2 <msg>", Colors.GREEN)}   - Broadcast message from Node-2 to all peers
  • {colorize("ping Node-1 Node-2", Colors.GREEN)}       - Test ping latency
  • {colorize("test", Colors.GREEN)}                  - Run automated verification test suite

Hypergraph Clusters:
  • {colorize("hyper list", Colors.MAGENTA)}                         - View all multi-node hyperedges
  • {colorize("hyper create <id> <nodes> [name]", Colors.MAGENTA)}   - Define hyperedge (e.g., hyper create H1 Node-1,Node-2,Node-3 Quorum)
  • {colorize("hyper send <id> <sender> <msg>", Colors.MAGENTA)}     - Multicast message ONLY to hyperedge members
  • {colorize("hyper node <node_id>", Colors.MAGENTA)}               - Show which hyperedges a node belongs to
  • {colorize("hyper plot / visualize", Colors.MAGENTA)}             - Plot & open Hypergraph image (Matplotlib & NetworkX)
  • {colorize("hyper save / load", Colors.MAGENTA)}                  - Persist or reload hyperedges from hypergraph.csv

CSV Topology:
  • {colorize("export_csv [file.csv]", Colors.YELLOW)}              - Export active connections to CSV
  • {colorize("load_csv [file.csv]", Colors.YELLOW)}                - Restore physical links from CSV
  • {colorize("exit / quit", Colors.RED)}                     - Stop all nodes and exit
----------------------------------------------------------------------
"""
        print(banner)

        while self.running:
            prompt = f"{Colors.BOLD}{Colors.YELLOW}[Manager ({len(self.nodes)} nodes)]{Colors.RESET} > "
            try:
                line = input(prompt).strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting...")
                break

            cmd, args = self._parse_line(line)
            if not cmd or cmd == "comment":
                continue

            if cmd in ("exit", "quit", "q"):
                break

            elif cmd in ("help", "?"):
                print(banner)

            elif cmd in ("clear", "cls"):
                os.system("clear" if os.name != "nt" else "cls")
                print(banner)

            elif cmd in ("spawn", "start"):
                count = int(args[0]) if args else 5
                self.spawn_nodes(count)

            elif cmd in ("check", "status", "dashboard"):
                self.print_status()

            elif cmd in ("view", "show"):
                if not args or args[0] in ("hyper", "hyperedges", "groups", "clusters"):
                    self.hypergraph.print_hyperedges_table()
                elif args[0] in ("status", "nodes", "dashboard", "peers"):
                    self.print_status()
                else:
                    self.hypergraph.print_hyperedges_table()

            elif cmd == "topology":
                if not args:
                    print(colorize("Usage: topology [mesh | ring | star]", Colors.RED))
                    continue
                self.setup_topology(args[0])

            elif cmd == "connect":
                if len(args) == 1 and "," in args[0]:
                    nodes_to_connect = args[0].split(",")
                    self.connect_pair(nodes_to_connect[0], nodes_to_connect[1])
                elif len(args) == 2:
                    self.connect_pair(args[0], args[1])
                else:
                    print(colorize("Usage: connect <NodeA> <NodeB> (e.g., connect Node-1 Node-2)", Colors.RED))

            elif cmd == "send":
                if len(args) < 3:
                    print(colorize("Usage: send <FromNode> <ToNode> <message>", Colors.RED))
                    continue
                from_id = args[0]
                to_id = args[1]
                msg = " ".join(args[2:])
                self.send_direct_msg(from_id, to_id, msg)

            elif cmd in ("broadcast", "bcast"):
                if len(args) < 2:
                    print(colorize("Usage: broadcast <FromNode> <message>", Colors.RED))
                    continue
                from_id = args[0]
                msg = " ".join(args[1:])
                self.broadcast_msg(from_id, msg)

            elif cmd == "ping":
                if len(args) == 2:
                    self.ping_pair(args[0], args[1])
                else:
                    print(colorize("Usage: ping <FromNode> <ToNode>  OR  ping_all", Colors.RED))

            elif cmd in ("ping_all", "matrix"):
                self.ping_matrix()

            # --- HYPERGRAPH COMMANDS ---
            elif cmd in ("hyper", "hypergraph"):
                if not args or args[0] in ("list", "show"):
                    self.hypergraph.print_hyperedges_table()
                elif args[0] == "create":
                    self._handle_hyper_create(args[1:])
                elif args[0] == "send":
                    self._handle_hyper_send(args[1:])
                elif args[0] in ("node", "nodes"):
                    self._handle_hyper_node(args[1:])
                elif args[0] in ("remove", "delete"):
                    self._handle_hyper_remove(args[1:])
                elif args[0] == "save":
                    self._handle_hyper_save(args[1:])
                elif args[0] == "load":
                    self._handle_hyper_load(args[1:])
                else:
                    print(colorize("Available hyper commands: list, create, send, node, remove, save, load", Colors.RED))

            # Direct aliases so user doesn't even need 'hyper' prefix!
            elif cmd in ("create", "hyper_create", "hypercreate"):
                self._handle_hyper_create(args)

            elif cmd in ("hypersend", "hyper_send", "hsend"):
                self._handle_hyper_send(args)

            elif cmd in ("hyperlist", "hyper_list", "hlist"):
                self.hypergraph.print_hyperedges_table()

            elif cmd in ("hypernode", "hyper_node"):
                self._handle_hyper_node(args)

            # --- CSV PERSISTENCE COMMANDS ---
            elif cmd in ("export_csv", "exportcsv", "export-csv", "save_csv", "export"):
                target_file = args[0] if args else "connections.csv"
                self.export_topology_csv(target_file)

            elif cmd in ("load_csv", "loadcsv", "load-csv", "import_csv", "load", "import"):
                target_file = args[0] if args else "connections.csv"
                self.load_topology_csv(target_file)

            elif cmd in ("plot", "visualize", "hyperplot", "hyper_plot"):
                out_path = args[0] if args else "hypergraph_plot.png"
                self.plot_hypergraph_visualization(out_path)

            elif cmd == "test":
                self.run_automated_suite()

            elif cmd == "kill":
                if not args:
                    print(colorize("Usage: kill <NodeName> (e.g., kill Node-3)", Colors.RED))
                    continue
                self.kill_node(args[0])

            elif cmd == "revive":
                if not args:
                    print(colorize("Usage: revive <NodeName> (e.g., revive Node-3)", Colors.RED))
                    continue
                self.revive_node(args[0])

            elif cmd == "stop":
                self.stop_all()

            else:
                print(colorize(f"Unknown command '{cmd}'. Type 'help' for options.", Colors.RED))

        self.stop_all()
        print(colorize("Goodbye!", Colors.GREEN))


def main():
    manager = NetworkManager()
    manager.start_cli()


if __name__ == "__main__":
    main()

