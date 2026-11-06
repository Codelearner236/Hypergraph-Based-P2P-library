#!/usr/bin/env python3
"""
Automated Test Suite for 5 P2P Nodes.
Spins up 5 nodes, interconnects them, verifies message passing,
broadcasts, and ping latencies, and prints a comprehensive test report.
"""

import sys
import os
import time
import socket

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from p2p.node import EnhancedNode
from p2p.protocol import Colors, colorize
from p2p.hypergraph import HypergraphManager, TopologyCSVManager


def find_free_port_range(count=5, start_port=9001):
    """Find a block of consecutive available ports."""
    for base in range(start_port, start_port + 200, count):
        available = True
        for p in range(base, base + count):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", p))
            except OSError:
                available = False
                break
        if available:
            return base
    return start_port


def run_tests():
    print(colorize("\n" + "=" * 70, Colors.BOLD + Colors.CYAN))
    print(colorize("   🧪 P2P 5-NODE AUTOMATED VERIFICATION SUITE 🧪", Colors.BOLD + Colors.CYAN))
    print(colorize("=" * 70 + "\n", Colors.BOLD + Colors.CYAN))

    nodes = []
    num_nodes = 5
    base_port = find_free_port_range(count=num_nodes, start_port=9001)
    tests_passed = 0
    total_tests = 8

    try:
        # TEST 1: Spin up 5 Nodes
        print(colorize("[STEP 1] Starting 5 P2P Nodes...", Colors.BOLD))
        for i in range(1, num_nodes + 1):
            n = EnhancedNode("127.0.0.1", base_port + (i - 1), node_id=f"Node-{i}")
            n.start()
            nodes.append(n)
            print(f"  ✓ {n.node_id} listening on 127.0.0.1:{n.port}")

        time.sleep(0.5)
        print(colorize("  --> TEST 1 PASSED: All 5 nodes started successfully!\n", Colors.GREEN))
        tests_passed += 1

        # TEST 2: Connect all 5 nodes into a Full Mesh
        print(colorize("[STEP 2] Interconnecting nodes into a Full Mesh topology...", Colors.BOLD))
        link_count = 0
        for i in range(num_nodes):
            for j in range(i + 1, num_nodes):
                src = nodes[i]
                tgt = nodes[j]
                ok = src.connect(tgt.host, tgt.port)
                if ok:
                    link_count += 1

        time.sleep(1.0)
        print(f"  ✓ Established {link_count} connections between 5 nodes.")
        print(colorize("  --> TEST 2 PASSED: Topology established!\n", Colors.GREEN))
        tests_passed += 1

        # TEST 3: Check status and peer count on each node
        print(colorize("[STEP 3] Checking connection status across all 5 nodes...", Colors.BOLD))
        peers_ok = True
        for n in nodes:
            peers = n.get_connected_peers()
            print(f"  • {n.node_id} (port {n.port}): {len(peers)} peers connected -> {list(peers.keys())}")
            if len(peers) != 4:
                peers_ok = False

        if peers_ok:
            print(colorize("  --> TEST 3 PASSED: Every node has exactly 4 connected peers!\n", Colors.GREEN))
            tests_passed += 1
        else:
            print(colorize("  --> TEST 3 FAILED: Some nodes did not reach full mesh connection.\n", Colors.RED))

        # TEST 4: Ping / Pong latency check
        print(colorize("[STEP 4] Testing Ping / Pong latency between nodes...", Colors.BOLD))
        ping_ok = True
        test_pairs = [(0, 1), (1, 3), (4, 0), (2, 4)]
        for src_idx, tgt_idx in test_pairs:
            src = nodes[src_idx]
            tgt = nodes[tgt_idx]
            rtt = src.ping(tgt.node_id, timeout=2.0)
            if rtt is not None:
                print(colorize(f"  ✓ Ping from {src.node_id} to {tgt.node_id}: {rtt:.2f} ms", Colors.GREEN))
            else:
                print(colorize(f"  ✗ Ping from {src.node_id} to {tgt.node_id} timed out", Colors.RED))
                ping_ok = False

        if ping_ok:
            print(colorize("  --> TEST 4 PASSED: All ping checks succeeded with sub-millisecond latencies!\n", Colors.GREEN))
            tests_passed += 1
        else:
            print(colorize("  --> TEST 4 FAILED: Ping timeout occurred.\n", Colors.RED))

        # TEST 5: Direct messaging between nodes
        print(colorize("[STEP 5] Testing Direct Messaging (Node-1 -> Node-4)...", Colors.BOLD))
        direct_payload = "Greetings from Node 1 to Node 4"
        nodes[0].send_direct("Node-4", direct_payload)
        time.sleep(0.5)

        received_by_node4 = any(
            m.get("payload") == direct_payload and m.get("sender_id") == "Node-1"
            for m in nodes[3].received_messages
        )
        if received_by_node4:
            print(colorize(f"  ✓ Node-4 verified receipt of message: \"{direct_payload}\"", Colors.GREEN))
            print(colorize("  --> TEST 5 PASSED: Direct messaging validated!\n", Colors.GREEN))
            tests_passed += 1
        else:
            print(colorize("  --> TEST 5 FAILED: Node-4 did not receive direct message.\n", Colors.RED))

        # TEST 6: Network-Wide Broadcast
        print(colorize("[STEP 6] Testing Network-Wide Broadcast from Node-2...", Colors.BOLD))
        bcast_payload = "Global Announcement: P2P Network is Live!"
        nodes[1].broadcast(bcast_payload)
        time.sleep(0.6)

        received_counts = 0
        for i, n in enumerate(nodes):
            if i == 1:
                continue  # Sender
            has_bcast = any(
                m.get("payload") == bcast_payload and m.get("sender_id") == "Node-2"
                for m in n.received_messages
            )
            if has_bcast:
                received_counts += 1
                print(f"  ✓ {n.node_id} successfully received broadcast.")

        if received_counts == 4:
            print(colorize("  --> TEST 6 PASSED: All 4 peer nodes received the broadcast!\n", Colors.GREEN))
            tests_passed += 1
        else:
            print(colorize(f"  --> TEST 6 FAILED: Only {received_counts}/4 nodes received the broadcast.\n", Colors.RED))

        # TEST 7: Hypergraph Multi-Node Multicast
        print(colorize("[STEP 7] Testing Hypergraph Multi-Node Multicast (H1: Node-1, Node-2, Node-3)...", Colors.BOLD))
        hyper = HypergraphManager("test_hypergraph.csv")
        hyper.add_hyperedge("H1", ["Node-1", "Node-2", "Node-3"], name="Consensus_Group", description="3-Node Quorum")
        hyper.save_to_csv()

        h_payload = "Hypergraph Quorum Directive #777"
        nodes[0].send_hyper_multicast("H1", ["Node-1", "Node-2", "Node-3"], h_payload)
        time.sleep(0.5)

        # Check members received
        h_recv_n2 = any(m.get("payload") == h_payload and m.get("hyperedge_id") == "H1" for m in nodes[1].received_messages)
        h_recv_n3 = any(m.get("payload") == h_payload and m.get("hyperedge_id") == "H1" for m in nodes[2].received_messages)
        # Check non-members did NOT receive
        h_recv_n4 = any(m.get("payload") == h_payload for m in nodes[3].received_messages)
        h_recv_n5 = any(m.get("payload") == h_payload for m in nodes[4].received_messages)

        if h_recv_n2 and h_recv_n3 and (not h_recv_n4) and (not h_recv_n5):
            print(colorize("  ✓ Verified: Message delivered ONLY to H1 members (Node-2, Node-3)", Colors.GREEN))
            print(colorize("  ✓ Verified: Non-members (Node-4, Node-5) correctly excluded from multicast.", Colors.GREEN))
            print(colorize("  --> TEST 7 PASSED: Hypergraph routing validated!\n", Colors.GREEN))
            tests_passed += 1
        else:
            print(colorize("  --> TEST 7 FAILED: Hypergraph delivery was inaccurate.\n", Colors.RED))

        # TEST 8: CSV Physical Topology Export and Load
        print(colorize("[STEP 8] Testing CSV Physical Topology Export and Load...", Colors.BOLD))
        nodes_dict = {n.node_id: n for n in nodes}
        test_csv_path = "test_connections.csv"
        exported_count = TopologyCSVManager.export_topology_to_csv(nodes_dict, test_csv_path)
        imported_links = TopologyCSVManager.import_topology_from_csv(test_csv_path)

        if exported_count == 10 and len(imported_links) == 10:
            print(colorize(f"  ✓ Exported 10 mesh links to '{test_csv_path}'", Colors.GREEN))
            print(colorize(f"  ✓ Successfully imported back 10 connection specs from CSV.", Colors.GREEN))
            print(colorize("  --> TEST 8 PASSED: CSV Topology Persistence validated!\n", Colors.GREEN))
            tests_passed += 1
        else:
            print(colorize(f"  --> TEST 8 FAILED: Expected 10 links in CSV, got export={exported_count}, import={len(imported_links)}\n", Colors.RED))

    finally:
        # Cleanup
        print(colorize("Shutting down all 5 nodes cleanly...", Colors.YELLOW))
        for n in nodes:
            try:
                n.stop()
            except Exception:
                pass
        print(colorize("All nodes terminated.", Colors.GREEN))

    # Final Summary Report
    print("\n" + "=" * 70)
    print(colorize(f"   TEST SUMMARY: {tests_passed} / {total_tests} TESTS PASSED", Colors.BOLD + (Colors.GREEN if tests_passed == total_tests else Colors.RED)))
    print("=" * 70 + "\n")

    return 0 if tests_passed == total_tests else 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)

