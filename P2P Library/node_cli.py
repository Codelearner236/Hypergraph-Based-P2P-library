#!/usr/bin/env python3
"""
Interactive Terminal CLI for a Single P2P Node.
Run this script in separate terminal windows (e.g. Node 1, Node 2, Node 3, etc.)
to connect them, check their status, and send messages/pings interactively.
"""

import sys
import os
import argparse
import time
import threading
import shlex
import re
import subprocess

# Add parent directory to sys.path so p2p package can be imported directly
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    import readline  # Enable arrow key navigation & history on macOS/Linux
except ImportError:
    pass

from p2p.node import EnhancedNode
from p2p.protocol import Colors, colorize
from p2p.hypergraph import HypergraphManager, TopologyCSVManager


def print_banner(node_id: str, host: str, port: int):
    banner = f"""
{Colors.CYAN}{Colors.BOLD}======================================================================
  🌐  P2P NODE TERMINAL: [{node_id}]
  Listening on: {host}:{port}
======================================================================{Colors.RESET}
Commands:
  {colorize("connect <host> <port>", Colors.GREEN)}  - Connect to another peer (e.g., connect 127.0.0.1 8002)
  {colorize("check / status", Colors.GREEN)}          - Inspect this node and all connected peers
  {colorize("peers", Colors.GREEN)}                   - List connected peer IDs and endpoints
  {colorize("send <peer_id> <msg>", Colors.GREEN)}    - Send direct message to a peer
  {colorize("broadcast <msg>", Colors.GREEN)}         - Broadcast message to all connected peers
  {colorize("hyper list", Colors.MAGENTA)}               - List defined hyperedges in hypergraph.csv
  {colorize("hyper send <edge_id> <msg>", Colors.MAGENTA)} - Multicast message to hyperedge members
  {colorize("plot [style]", Colors.MAGENTA)}             - Plot Hypergraph (dashboard, dual, matrix, euler, bipartite, html)
  {colorize("export_csv [file.csv]", Colors.YELLOW)}     - Save active peer connections to CSV
  {colorize("ping <peer_id>", Colors.GREEN)}          - Ping a peer and measure latency (ms)
  {colorize("ping_all", Colors.GREEN)}                - Ping all connected peers
  {colorize("discover", Colors.GREEN)}                - Query peers for new nodes in the network
  {colorize("disconnect <peer_id>", Colors.GREEN)}    - Disconnect from a peer
  {colorize("clear", Colors.GREEN)}                   - Clear the terminal screen
  {colorize("help", Colors.GREEN)}                    - Show this help menu
  {colorize("exit / quit", Colors.GREEN)}             - Shut down node and exit
----------------------------------------------------------------------
"""
    print(banner)


class NodeCLI:
    def __init__(self, host: str, port: int, node_id: str):
        self.host = host
        self.port = port
        self.node_id = node_id
        self.running = True
        self.hypergraph = HypergraphManager("hypergraph.csv")
        self.hypergraph.load_from_csv()

        # Custom log callback for CLI
        def cli_log(formatted_msg, level):
            # Print cleanly
            sys.stdout.write(f"\r{formatted_msg}\n{self.get_prompt()}")
            sys.stdout.flush()

        self.node = EnhancedNode(
            host=self.host,
            port=self.port,
            node_id=self.node_id,
            on_log_callback=cli_log,
        )

    def get_prompt(self) -> str:
        peer_count = len(self.node.get_connected_peers())
        badge = colorize(f"[{peer_count} peers]", Colors.DIM)
        return f"{Colors.BOLD}{Colors.CYAN}[{self.node_id} @ {self.port}]{Colors.RESET} {badge} > "

    def _parse_line(self, raw_line: str):
        line = raw_line.strip()
        if not line:
            return None, []
        if line.startswith("#") or line.startswith("//"):
            line = re.sub(r"^[#/]+\s*", "", line).strip()
            if not line:
                return None, []

        command_patterns = [
            ("plot", r"(?:hyper\s+)?(?:plot|visualize)\b.*"),
            ("hyper_sub", r"hyper\s+(?:list|show|create|send)\b.*"),
            ("create_edge", r"(?:hyper\s+)?create\s+[A-Za-z0-9_]+\s+[A-Za-z0-9_,\-]+(?:,|Node)[A-Za-z0-9_,\-]*.*"),
            ("export_csv", r"export_csv\b.*"),
            ("hypersend", r"hypersend\b.*"),
            ("hyperlist", r"hyperlist\b"),
            ("broadcast", r"broadcast\b.*"),
            ("ping_all", r"ping_all\b"),
            ("ping", r"ping\s+\S+"),
            ("check", r"check\b"),
            ("status", r"status\b"),
            ("peers", r"peers\b"),
            ("help", r"help\b"),
            ("exit", r"exit\b"),
            ("quit", r"quit\b"),
        ]

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

        parts = line.split()
        if parts and parts[0].lower() in ("view", "show"):
            return "hyper", ["list"]

        if re.match(r"^(start|multicast|save|disconnect|step|\d+[\.\)])\b", line, re.IGNORECASE):
            return "COMMENT", [line]

        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()

        return (parts[0].lower(), parts[1:]) if parts else (None, [])

    def plot_hypergraph_visualization(self, style: str = "dashboard", output_path: Optional[str] = None, live: bool = False):
        """Generate and display visual hypergraph plot using Matplotlib & NetworkX."""
        self.hypergraph.save_to_csv("hypergraph.csv")
        TopologyCSVManager.export_topology_to_csv({self.node_id: self.node}, "connections.csv")

        script_path = os.path.join(os.path.dirname(__file__), "visualize_hypergraph.py")
        venv_python = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python")
        python_bin = venv_python if os.path.exists(venv_python) else sys.executable

        if live or style == "live":
            actual_style = "dashboard" if style == "live" else style
            try:
                cmd = [python_bin, script_path, "--live", "--style", actual_style]
                subprocess.Popen(cmd)
                print(colorize(f"🚀 Launched live interactive hypergraph window ({actual_style}) in background!", Colors.BOLD + Colors.CYAN))
                print(colorize("   • Dynamic real-time animation with zero disk writes.", Colors.GREEN))
            except Exception as e:
                print(colorize(f"Error launching live visualizer: {e}", Colors.RED))
            return

        default_out = "hypergraph.html" if style in ("html", "interactive") else (
            f"hypergraph_{style}.png" if style not in ("dashboard", "all") else "hypergraph_plot.png"
        )
        target_out = output_path or default_out

        try:
            cmd = [python_bin, script_path, "--style", style, "--output", target_out]
            subprocess.run(cmd, check=True)
            print(colorize(f"✓ Hypergraph plot ({style}) generated: '{target_out}'", Colors.GREEN))
        except Exception as e:
            print(colorize(f"Error generating plot: {e}", Colors.RED))

    def start(self):
        self.node.start()
        time.sleep(0.3)
        print_banner(self.node_id, self.host, self.port)

        while self.running:
            try:
                line = input(self.get_prompt()).strip()
            except (KeyboardInterrupt, EOFError):
                print("\nShutting down...")
                break

            cmd, args = self._parse_line(line)
            if not cmd or cmd == "COMMENT":
                continue

            if cmd in ("exit", "quit", "q"):
                break

            elif cmd in ("help", "?"):
                print_banner(self.node_id, self.host, self.port)

            elif cmd in ("clear", "cls"):
                os.system("clear" if os.name != "nt" else "cls")
                print_banner(self.node_id, self.host, self.port)

            elif cmd in ("check", "status"):
                self.node.print_status()

            elif cmd == "peers":
                peers = self.node.get_connected_peers()
                if not peers:
                    print(colorize("No peers currently connected.", Colors.YELLOW))
                else:
                    print(colorize(f"\n--- Connected Peers ({len(peers)}) ---", Colors.BOLD))
                    for pid, p in peers.items():
                        lat = f"{p['latency_ms']:.2f} ms" if p["latency_ms"] is not None else "not pinged"
                        print(f"  • {colorize(pid, Colors.GREEN)} -> {p['host']}:{p['port']} ({p['direction']}, latency: {lat})")
                    print()

            elif cmd == "connect":
                if len(args) == 1:
                    # Default host to 127.0.0.1 if only port given
                    target_host = "127.0.0.1"
                    try:
                        target_port = int(args[0])
                    except ValueError:
                        print(colorize("Usage: connect <host> <port>  OR  connect <port>", Colors.RED))
                        continue
                elif len(args) >= 2:
                    target_host = args[0]
                    try:
                        target_port = int(args[1])
                    except ValueError:
                        print(colorize("Port must be an integer.", Colors.RED))
                        continue
                else:
                    print(colorize("Usage: connect <host> <port>", Colors.RED))
                    continue

                print(colorize(f"Connecting to {target_host}:{target_port}...", Colors.YELLOW))
                ok = self.node.connect(target_host, target_port)
                if not ok:
                    print(colorize(f"Failed to connect to {target_host}:{target_port}.", Colors.RED))

            elif cmd == "send":
                if len(args) < 2:
                    print(colorize("Usage: send <peer_id> <message>", Colors.RED))
                    continue
                target_id = args[0]
                message = " ".join(args[1:])
                self.node.send_direct(target_id, message)

            elif cmd in ("broadcast", "bcast"):
                if not args:
                    print(colorize("Usage: broadcast <message>", Colors.RED))
                    continue
                message = " ".join(args)
                count = self.node.broadcast(message)
                if count == 0:
                    print(colorize("No peers connected to broadcast to.", Colors.YELLOW))

            elif cmd == "ping":
                if not args:
                    print(colorize("Usage: ping <peer_id>", Colors.RED))
                    continue
                target_id = args[0]
                print(colorize(f"Pinging [{target_id}]...", Colors.YELLOW))
                rtt = self.node.ping(target_id)
                if rtt is not None:
                    print(colorize(f"✓ Pong from [{target_id}]: latency = {rtt:.2f} ms", Colors.GREEN))

            elif cmd == "ping_all":
                peers = self.node.get_connected_peers()
                if not peers:
                    print(colorize("No peers connected to ping.", Colors.YELLOW))
                    continue
                print(colorize(f"Pinging {len(peers)} peer(s)...", Colors.YELLOW))
                for pid in peers:
                    rtt = self.node.ping(pid)
                    if rtt is not None:
                        print(colorize(f"  • [{pid}]: {rtt:.2f} ms", Colors.GREEN))
                    else:
                        print(colorize(f"  • [{pid}]: TIMEOUT", Colors.RED))

            elif cmd == "discover":
                print(colorize("Broadcasting peer discovery request...", Colors.YELLOW))
                self.node.request_discovery()

            elif cmd in ("hyper", "hypergraph"):
                self.hypergraph.load_from_csv()
                if not args or args[0] in ("list", "show"):
                    self.hypergraph.print_hyperedges_table()
                elif args[0] == "create":
                    if len(args) < 3:
                        print(colorize("Usage: hyper create <id> <node1,node2,...> [name]", Colors.RED))
                        continue
                    edge_id = args[1]
                    members = [m.strip() for m in args[2].split(",") if m.strip()]
                    name = args[3] if len(args) > 3 else f"Group-{edge_id}"
                    self.hypergraph.add_hyperedge(edge_id, members, name=name)
                    self.hypergraph.save_to_csv()
                    print(colorize(f"✓ Created hyperedge '{edge_id}' ({name}) with members: {', '.join(members)}", Colors.GREEN))
                elif args[0] == "send":
                    if len(args) < 3:
                        print(colorize("Usage: hyper send <edge_id> <message>", Colors.RED))
                        continue
                    edge_id = args[1]
                    msg = " ".join(args[2:])
                    members = self.hypergraph.get_members(edge_id)
                    if not members:
                        print(colorize(f"Hyperedge '{edge_id}' not found in hypergraph.csv.", Colors.RED))
                        continue
                    count = self.node.send_hyper_multicast(edge_id, members, msg)
                    print(colorize(f"Sent hyper multicast to {count} connected member(s).", Colors.GREEN))
                else:
                    print(colorize("Usage: hyper list  OR  hyper create <id> <nodes> [name]  OR  hyper send <edge_id> <message>", Colors.RED))

            elif cmd in ("create", "hypercreate", "hyper_create"):
                self.hypergraph.load_from_csv()
                if len(args) < 2:
                    print(colorize("Usage: create <id> <node1,node2,...> [name]", Colors.RED))
                    continue
                edge_id = args[0]
                members = [m.strip() for m in args[1].split(",") if m.strip()]
                name = args[2] if len(args) > 2 else f"Group-{edge_id}"
                self.hypergraph.add_hyperedge(edge_id, members, name=name)
                self.hypergraph.save_to_csv()
                print(colorize(f"✓ Created hyperedge '{edge_id}' ({name}) with members: {', '.join(members)}", Colors.GREEN))

            elif cmd in ("hypersend", "hyper_send"):
                self.hypergraph.load_from_csv()
                if len(args) < 2:
                    print(colorize("Usage: hypersend <edge_id> <message>", Colors.RED))
                    continue
                edge_id = args[0]
                msg = " ".join(args[1:])
                members = self.hypergraph.get_members(edge_id)
                if not members:
                    print(colorize(f"Hyperedge '{edge_id}' not found in hypergraph.csv.", Colors.RED))
                    continue
                count = self.node.send_hyper_multicast(edge_id, members, msg)
                print(colorize(f"Sent hyper multicast to {count} connected member(s).", Colors.GREEN))

            elif cmd in ("hyperlist", "hyper_list"):
                self.hypergraph.load_from_csv()
                self.hypergraph.print_hyperedges_table()

            elif cmd in ("export_csv", "exportcsv", "export-csv", "save_csv"):
                target_file = args[0] if args else f"connections_{self.node_id}.csv"
                count = TopologyCSVManager.export_topology_to_csv({self.node_id: self.node}, target_file)
                print(colorize(f"✓ Exported {count} connection(s) to '{target_file}'.", Colors.GREEN))

            elif cmd in ("plot", "visualize", "hyperplot", "hyper_plot"):
                style = "dashboard"
                out_path = None
                is_live = False
                if args:
                    lower_args = [a.lower() for a in args]
                    if "live" in lower_args:
                        is_live = True
                        lower_args.remove("live")
                    if lower_args:
                        first = lower_args[0]
                        if first in ("dashboard", "dual", "matrix", "euler", "bipartite", "html", "interactive", "all"):
                            style = first
                            out_path = lower_args[1] if len(lower_args) > 1 else None
                        else:
                            out_path = lower_args[0]
                self.plot_hypergraph_visualization(style=style, output_path=out_path, live=is_live)

            elif cmd == "disconnect":
                if not args:
                    print(colorize("Usage: disconnect <peer_id>", Colors.RED))
                    continue
                self.node.disconnect_peer(args[0])

            else:
                print(colorize(f"Unknown command: '{cmd}'. Type 'help' for available commands.", Colors.RED))

        print(colorize("\nStopping node...", Colors.YELLOW))
        self.node.stop()
        print(colorize("Node stopped cleanly. Goodbye!", Colors.GREEN))


def main():
    parser = argparse.ArgumentParser(description="P2P Terminal Node")
    parser.add_argument("--id", "-i", type=str, default=None, help="Unique Node ID (e.g. Node1, Node2)")
    parser.add_argument("--port", "-p", type=int, default=None, help="Port to listen on (e.g. 8001)")
    parser.add_argument("--host", "-H", type=str, default="127.0.0.1", help="Host IP to bind (default: 127.0.0.1)")
    args = parser.parse_args()

    # Prompt interactively if not passed via arguments
    port = args.port
    if port is None:
        try:
            port_input = input("Enter port for this node [default: 8001]: ").strip()
            port = int(port_input) if port_input else 8001
        except (ValueError, KeyboardInterrupt):
            port = 8001

    node_id = args.id
    if not node_id:
        default_id = f"Node-{port % 1000}" if port >= 1000 else f"Node-{port}"
        try:
            id_input = input(f"Enter ID for this node [default: {default_id}]: ").strip()
            node_id = id_input if id_input else default_id
        except (ValueError, KeyboardInterrupt):
            node_id = default_id

    cli = NodeCLI(host=args.host, port=port, node_id=node_id)
    cli.start()


if __name__ == "__main__":
    main()

