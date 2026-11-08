# 🌐 P2P Library - 5-Node Peer-to-Peer Network

A modular, robust Python Peer-to-Peer (P2P) networking library and terminal testing suite. It allows you to create **4 to 5 nodes**, connect them, check their status, and test direct messaging, network-wide broadcasts, and ping latencies directly from the terminal.

---

## 📁 Project Structure

```
P2P Library/
├── p2p/                        # Core P2P library package
│   ├── __init__.py             # Package exports
│   ├── node.py                 # EnhancedNode class (TCP sockets + p2pnetwork compatibility)
│   ├── protocol.py             # Message definitions (PING, CHAT, BROADCAST, HYPER_MULTICAST)
│   └── hypergraph.py           # HypergraphManager & TopologyCSVManager
├── network_manager.py          # 🎛️ Interactive manager for 4-5 nodes & Hypergraph in ONE terminal
├── node_cli.py                 # 💻 Interactive CLI for a single node (run in separate terminal tabs)
├── visualize_hypergraph.py     # 📊 Hypergraph Visualizer (Matplotlib & NetworkX)
├── test_5_nodes.py             # 🧪 8-step automated test suite (includes hypergraph & CSV tests)
├── launch_terminals.sh         # 🚀 macOS helper script to launch 5 terminal windows
├── hypergraph.csv              # Multi-node hyperedge group definitions
├── connections.csv             # Pairwise physical topology connections
├── connection_events.csv       # Live audit log of connection & disconnection events
├── requirements.txt            # Optional dependencies (p2pnetwork)
└── README.md                   # Documentation and usage guide
```

---

## ⚡ Three Ways to Run & Test

### Option 1: Multi-Node Terminal Manager (Recommended)
Manage, connect, check, and test all 4 to 5 nodes from **a single terminal**:

```bash
python3 network_manager.py
```

Inside the interactive manager:
1. **Spawn 5 nodes**:
   ```
   spawn 5
   ```
2. **Connect them in Mesh, Ring, or Star topology**:
   ```
   topology mesh     # Connects all 5 nodes to each other (full mesh)
   topology ring     # Connects 1 -> 2 -> 3 -> 4 -> 5 -> 1
   ```
3. **Check status of all nodes and connections**:
   ```
   check
   ```
4. **Ping to test connectivity & latency**:
   ```
   ping Node-1 Node-3
   ping_all
   ```
5. **Send direct message**:
   ```
   send Node-1 Node-4 "Hello from Node 1!"
   ```
6. **Send network broadcast**:
   ```
   broadcast Node-2 "Global alert to all peers"
   ```
7. **Hypergraph Multi-Node Multicast**:
   ```
   hyper list                                         # View defined hyperedges (H1, H2, H3)
   hyper create H1 Node-1,Node-2,Node-3 FastQuorum    # Create new 3-node hyperedge
   hyper send H1 Node-1 "Quorum directive #42"        # Multicast ONLY to H1 members
   hyper node Node-2                                  # Show all hyperedges Node-2 belongs to
   ```
8. **CSV Topology Persistence**:
   ```
   export_csv my_net.csv   # Save current live connections to CSV
   load_csv my_net.csv     # Restore all connection links from CSV
   ```
9. **Visualize Hypergraph (Live Animation & 6 Distinct Layouts)**:
   ```
   plot live                # ⚡ Real-Time Live Animated Dashboard (FuncAnimation - No Disk Files!)
   plot live euler          # Live animated Euler convex hull enclosure with multicast packet flows
   plot live bipartite      # Live animated star-hub projection with streaming packets
   plot                     # 4-in-1 Comprehensive Multi-view Dashboard (Default PNG)
   plot dual                # Dual Line Graph (Inter-hyperedge bridges & routing)
   plot matrix              # Incidence Matrix Heatmap (Node × Hyperedge table)
   plot euler               # Euler Enclosure (Convex Hull translucent blobs)
   plot bipartite           # Bipartite Projection (Star Hub view)
   plot html                # Interactive browser explorer (hypergraph.html)
   ```
   *Tip: In `plot live` mode, the window stays open and automatically hot-reloads whenever you create or modify hyperedges or connections in the terminal!*
10. **Run automated verification tests**:
   ```
   test
   ```

---

### Option 2: Run Individual Nodes in Separate Terminals
If you want to open 4 or 5 terminal tabs/windows side-by-side to chat and test:

#### macOS 1-Click Launcher:
```bash
./launch_terminals.sh
```
*This automatically launches 5 terminal windows running `Node-1` through `Node-5`.*

#### Or manually in separate terminal tabs:
- **Terminal 1**:
  ```bash
  python3 node_cli.py --id Node-1 --port 8001
  ```
- **Terminal 2**:
  ```bash
  python3 node_cli.py --id Node-2 --port 8002
  ```
- **Terminal 3**:
  ```bash
  python3 node_cli.py --id Node-3 --port 8003
  ```
- **Terminal 4**:
  ```bash
  python3 node_cli.py --id Node-4 --port 8004
  ```
- **Terminal 5**:
  ```bash
  python3 node_cli.py --id Node-5 --port 8005
  ```

#### Terminal Commands in Each Node:
| Command | Description | Example |
|---|---|---|
| `connect <host> <port>` | Connect to another peer | `connect 127.0.0.1 8002` |
| `check` / `status` | Inspect node status & peer table | `check` |
| `peers` | List connected peer IDs | `peers` |
| `ping <peer_id>` | Send ping and measure latency | `ping Node-2` |
| `ping_all` | Ping all connected peers | `ping_all` |
| `send <peer_id> <msg>` | Send private direct message | `send Node-2 Hello Node 2!` |
| `broadcast <msg>` | Broadcast to all peers | `broadcast Hello everyone!` |
| `discover` | Query peers to find other nodes | `discover` |
| `plot [style]` | Plot Hypergraph (dashboard, dual, matrix, html) | `plot matrix` |
| `disconnect <peer_id>` | Disconnect from peer | `disconnect Node-2` |
| `exit` / `quit` | Gracefully shut down node | `exit` |

---

### Option 3: Automated 5-Node Test Suite
Run the end-to-end automated test script:

```bash
python3 test_5_nodes.py
```

This script will:
- ✅ **Test 1**: Start 5 nodes on ports 8001–8005
- ✅ **Test 2**: Interconnect them into a full mesh topology
- ✅ **Test 3**: Verify connection counts across all nodes (4 peers each)
- ✅ **Test 4**: Validate ping/pong round-trip latency
- ✅ **Test 5**: Verify direct message delivery (`Node-1` -> `Node-4`)
- ✅ **Test 6**: Verify network-wide broadcast (`Node-2` -> all nodes)
- ✅ Cleanly shut down all nodes

---

## 🐍 Using the P2P Library in Your Own Python Code

You can also import and use `EnhancedNode` directly in your own Python projects:

```python
import time
from p2p.node import EnhancedNode

# 1. Create two nodes
node1 = EnhancedNode(host="127.0.0.1", port=8001, node_id="Node-1")
node2 = EnhancedNode(host="127.0.0.1", port=8002, node_id="Node-2")

# 2. Start listening
node1.start()
node2.start()
time.sleep(0.5)

# 3. Connect node1 to node2
node1.connect("127.0.0.1", 8002)
time.sleep(0.5)

# 4. Check status & ping
latency = node1.ping("Node-2")
print(f"Ping latency: {latency:.2f} ms")

# 5. Send direct message & broadcast
node1.send_direct("Node-2", "Hello peer!")
node1.broadcast("Hello to everyone connected!")

# 6. Inspect connected peers
peers = node1.get_connected_peers()
print("Connected peers:", peers)

# 7. Stop nodes cleanly
node1.stop()
node2.stop()
```

