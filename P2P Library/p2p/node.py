"""
P2P Enhanced Node implementation.
Supports both the external `p2pnetwork` library and a pure standard-library
fallback engine, ensuring zero friction across any terminal environment.
"""

import sys
import os
import time
import uuid
import socket
import threading
import json
from typing import Dict, List, Optional, Any, Callable

from p2p.protocol import (
    MSG_TYPE_PING,
    MSG_TYPE_PONG,
    MSG_TYPE_CHAT,
    MSG_TYPE_BROADCAST,
    MSG_TYPE_DISCOVER_REQ,
    MSG_TYPE_DISCOVER_RESP,
    MSG_TYPE_HEARTBEAT,
    MSG_TYPE_HYPER_MULTICAST,
    Colors,
    colorize,
    create_message,
)
from p2p.hypergraph import TopologyCSVManager

# ---------------------------------------------------------------------------
# Attempt to import p2pnetwork, otherwise provide clean built-in engine
# ---------------------------------------------------------------------------
HAS_P2P_NETWORK_PKG = False
try:
    from p2pnetwork.node import Node as P2PNetworkBaseNode
    HAS_P2P_NETWORK_PKG = True
except ImportError:
    pass

EOT_CHAR = b"\x04"


class StandaloneNodeConnection(threading.Thread):
    """Clean socket connection worker matching p2pnetwork protocol framing."""

    def __init__(self, main_node, sock: socket.socket, id: str, host: str, port: int):
        super().__init__(daemon=True)
        self.main_node = main_node
        self.sock = sock
        self.id = str(id)
        self.host = host
        self.port = int(port)
        self.terminate_flag = threading.Event()
        self.sock.settimeout(0.5)

    def send(self, data: Any):
        """Send string or dict framed with EOT character."""
        if self.terminate_flag.is_set():
            return
        try:
            if isinstance(data, dict):
                payload = json.dumps(data).encode("utf-8") + EOT_CHAR
            elif isinstance(data, str):
                payload = data.encode("utf-8") + EOT_CHAR
            elif isinstance(data, bytes):
                payload = data + EOT_CHAR
            else:
                payload = str(data).encode("utf-8") + EOT_CHAR
            self.sock.sendall(payload)
        except Exception:
            self.stop()

    def stop(self):
        self.terminate_flag.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

    def run(self):
        buffer = b""
        while not self.terminate_flag.is_set():
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                while EOT_CHAR in buffer:
                    message_bytes, buffer = buffer.split(EOT_CHAR, 1)
                    if message_bytes:
                        try:
                            msg_str = message_bytes.decode("utf-8")
                            try:
                                data = json.loads(msg_str)
                            except json.JSONDecodeError:
                                data = msg_str
                            self.main_node.node_message(self, data)
                        except Exception:
                            pass
            except socket.timeout:
                continue
            except Exception:
                break

        if not self.terminate_flag.is_set():
            self.main_node.node_disconnected(self)


class StandaloneBaseNode(threading.Thread):
    """Pure-Python standard library implementation of p2pnetwork.node.Node."""

    def __init__(self, host: str, port: int, id: str = None, callback=None, max_connections: int = 0):
        super().__init__(daemon=True)
        self.host = host
        self.port = int(port)
        self.id = str(id) if id else str(uuid.uuid4())[:8]
        self.callback = callback
        self.max_connections = max_connections
        self.nodes_inbound: List[StandaloneNodeConnection] = []
        self.nodes_outbound: List[StandaloneNodeConnection] = []
        self.terminate_flag = threading.Event()
        self.debug = False

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(1.0)
        self.sock.listen(10)

    def debug_print(self, msg: str):
        if self.debug:
            print(f"DEBUG [{self.id}]: {msg}")

    def connect_with_node(self, host: str, port: int) -> bool:
        port = int(port)
        if host == self.host and port == self.port:
            return False

        for n in self.nodes_outbound:
            if n.host == host and n.port == port:
                return True

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            # Handshake: send our ID and listening port
            sock.send((f"{self.id}:{self.port}").encode("utf-8"))
            connected_node_id = sock.recv(4096).decode("utf-8")

            if self.id == connected_node_id:
                sock.close()
                return False

            conn = StandaloneNodeConnection(self, sock, connected_node_id, host, port)
            self.nodes_outbound.append(conn)
            conn.start()
            self.outbound_node_connected(conn)
            return True
        except Exception as e:
            return False

    def disconnect_with_node(self, node):
        if node in self.nodes_outbound:
            node.stop()
            if node in self.nodes_outbound:
                self.nodes_outbound.remove(node)
        elif node in self.nodes_inbound:
            node.stop()
            if node in self.nodes_inbound:
                self.nodes_inbound.remove(node)

    def send_to_node(self, n, data):
        if n in self.nodes_inbound or n in self.nodes_outbound:
            n.send(data)

    def send_to_nodes(self, data, exclude=None):
        exclude = exclude or []
        for n in list(self.nodes_inbound) + list(self.nodes_outbound):
            if n not in exclude:
                n.send(data)

    def inbound_node_connected(self, node):
        pass

    def outbound_node_connected(self, node):
        pass

    def node_disconnected(self, node):
        if node in self.nodes_inbound:
            self.nodes_inbound.remove(node)
        if node in self.nodes_outbound:
            self.nodes_outbound.remove(node)

    def node_message(self, node, data):
        pass

    def stop(self):
        self.terminate_flag.set()
        connections = list(self.nodes_inbound) + list(self.nodes_outbound)
        self.nodes_inbound.clear()
        self.nodes_outbound.clear()
        for n in connections:
            n.stop()
        for n in connections:
            try:
                n.join(timeout=0.2)
            except Exception:
                pass
        try:
            self.sock.close()
        except Exception:
            pass

    def run(self):
        while not self.terminate_flag.is_set():
            try:
                connection, client_address = self.sock.accept()
                if self.max_connections == 0 or len(self.nodes_inbound) < self.max_connections:
                    raw_id = connection.recv(4096).decode("utf-8")
                    connected_node_port = client_address[1]
                    connected_node_id = raw_id
                    if ":" in raw_id:
                        parts = raw_id.split(":", 1)
                        connected_node_id = parts[0]
                        connected_node_port = int(parts[1])
                    connection.send(self.id.encode("utf-8"))

                    conn = StandaloneNodeConnection(
                        self, connection, connected_node_id, client_address[0], connected_node_port
                    )
                    self.nodes_inbound.append(conn)
                    conn.start()
                    self.inbound_node_connected(conn)
                else:
                    connection.close()
            except socket.timeout:
                continue
            except Exception:
                break


# Base class selection
NodeBase = P2PNetworkBaseNode if HAS_P2P_NETWORK_PKG else StandaloneBaseNode


class EnhancedNode(NodeBase):
    """
    Production-ready P2P Node with rich messaging, ping/pong latency checks,
    peer discovery, event callbacks, and graceful terminal logging.
    """

    def __init__(
        self,
        host: str,
        port: int,
        node_id: Optional[str] = None,
        on_message_callback: Optional[Callable] = None,
        on_connect_callback: Optional[Callable] = None,
        on_disconnect_callback: Optional[Callable] = None,
        on_log_callback: Optional[Callable] = None,
    ):
        actual_id = node_id or f"Node-{port}"
        super().__init__(host, int(port), id=actual_id)
        self.node_id = actual_id
        self.host = host
        self.port = int(port)

        # Callbacks
        self.on_message_cb = on_message_callback
        self.on_connect_cb = on_connect_callback
        self.on_disconnect_cb = on_disconnect_callback
        self.on_log_cb = on_log_callback

        # State tracking
        self.lock = threading.Lock()
        self.pending_pings: Dict[str, dict] = {}
        self.latencies: Dict[str, float] = {}
        self.known_peers: Dict[str, dict] = {}  # id -> {host, port, last_seen}
        self.received_messages: List[dict] = []
        self.message_count_recv = 0
        self.start_time = time.time()
        self.is_stopping = False

    def log(self, text: str, level: str = "INFO"):
        """Deliver log line via callback or print."""
        if self.is_stopping:
            return
        ts = time.strftime("%H:%M:%S")
        prefix = f"[{ts}] [{self.node_id}]"
        formatted = f"{prefix} {text}"
        if self.on_log_cb:
            self.on_log_cb(formatted, level)
        else:
            try:
                print(formatted, flush=True)
            except Exception:
                pass

    def stop(self):
        """Cleanly mark node as stopping and terminate background connections."""
        self.is_stopping = True
        try:
            super().stop()
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Connection Management & Helpers
    # -----------------------------------------------------------------------
    def get_all_connections(self) -> List[Any]:
        """Return combined list of active inbound and outbound connections."""
        with self.lock:
            # Deduplicate by connection object
            return list({c for c in (self.nodes_inbound + self.nodes_outbound)})

    def find_connection_by_id(self, peer_id: str) -> Optional[Any]:
        """Locate connection object matching peer_id."""
        with self.lock:
            for c in self.nodes_inbound + self.nodes_outbound:
                if str(c.id) == str(peer_id):
                    return c
        return None

    def get_connected_peers(self) -> Dict[str, dict]:
        """
        Return dictionary of currently connected peers with metadata:
        id -> {host, port, direction, latency_ms}
        """
        peers = {}
        with self.lock:
            for c in self.nodes_inbound:
                peers[str(c.id)] = {
                    "id": str(c.id),
                    "host": c.host,
                    "port": c.port,
                    "direction": "inbound",
                    "latency_ms": self.latencies.get(str(c.id), None),
                }
            for c in self.nodes_outbound:
                # If already present as inbound, mark as bidirectional
                if str(c.id) in peers:
                    peers[str(c.id)]["direction"] = "bidirectional"
                else:
                    peers[str(c.id)] = {
                        "id": str(c.id),
                        "host": c.host,
                        "port": c.port,
                        "direction": "outbound",
                        "latency_ms": self.latencies.get(str(c.id), None),
                    }
        return peers

    def connect(self, host: str, port: int) -> bool:
        """Connect to peer at host:port."""
        try:
            ok = self.connect_with_node(host, int(port))
            if ok:
                self.log(colorize(f"Connected to {host}:{port}", Colors.GREEN))
            else:
                self.log(colorize(f"Failed to connect to {host}:{port}", Colors.RED), level="WARN")
            return bool(ok)
        except Exception as e:
            self.log(colorize(f"Connection error to {host}:{port}: {e}", Colors.RED), level="ERROR")
            return False

    def disconnect_peer(self, peer_id: str) -> bool:
        """Disconnect from a peer by ID."""
        conn = self.find_connection_by_id(peer_id)
        if not conn:
            return False
        self.disconnect_with_node(conn)
        self.log(colorize(f"Disconnected from {peer_id}", Colors.YELLOW))
        return True

    # -----------------------------------------------------------------------
    # Messaging API: Direct, Broadcast, Ping, Discovery
    # -----------------------------------------------------------------------
    def send_direct(self, target_id: str, text: str) -> bool:
        """Send a direct message to a specific peer."""
        conn = self.find_connection_by_id(target_id)
        if not conn:
            self.log(colorize(f"Cannot send: Peer '{target_id}' is not connected.", Colors.RED), level="WARN")
            return False

        msg = create_message(
            msg_type=MSG_TYPE_CHAT,
            sender_id=self.node_id,
            sender_host=self.host,
            sender_port=self.port,
            payload=text,
            target_id=target_id,
        )
        self.send_to_node(conn, msg)
        self.log(colorize(f"Sent message to [{target_id}]: \"{text}\"", Colors.BLUE))
        return True

    def broadcast(self, text: str) -> int:
        """Broadcast a message to all connected peers."""
        conns = self.get_all_connections()
        if not conns:
            self.log(colorize("Cannot broadcast: No connected peers.", Colors.YELLOW), level="WARN")
            return 0

        msg = create_message(
            msg_type=MSG_TYPE_BROADCAST,
            sender_id=self.node_id,
            sender_host=self.host,
            sender_port=self.port,
            payload=text,
        )
        self.send_to_nodes(msg)
        self.log(colorize(f"Broadcasted to {len(conns)} peer(s): \"{text}\"", Colors.CYAN))
        return len(conns)

    def ping(self, target_id: str, timeout: float = 2.0) -> Optional[float]:
        """
        Send a PING to target_id and wait for PONG.
        Returns round-trip time in milliseconds, or None on timeout.
        """
        conn = self.find_connection_by_id(target_id)
        if not conn:
            self.log(colorize(f"Ping failed: '{target_id}' not connected.", Colors.RED), level="WARN")
            return None

        ping_id = str(uuid.uuid4())[:8]
        event = threading.Event()
        ping_info = {
            "target": target_id,
            "start_time": time.time(),
            "event": event,
            "rtt": None,
        }
        with self.lock:
            self.pending_pings[ping_id] = ping_info

        msg = create_message(
            msg_type=MSG_TYPE_PING,
            sender_id=self.node_id,
            sender_host=self.host,
            sender_port=self.port,
            payload={"ping_id": ping_id, "sent_at": ping_info["start_time"]},
            target_id=target_id,
        )
        self.send_to_node(conn, msg)

        # Wait for reply
        arrived = event.wait(timeout=timeout)
        with self.lock:
            info = self.pending_pings.pop(ping_id, None)

        if arrived and info and info["rtt"] is not None:
            rtt = info["rtt"]
            self.latencies[target_id] = rtt
            self.log(colorize(f"Ping to [{target_id}]: {rtt:.2f} ms", Colors.GREEN))
            return rtt
        else:
            self.log(colorize(f"Ping to [{target_id}]: TIMEOUT (>{timeout}s)", Colors.RED), level="WARN")
            return None

    def request_discovery(self, target_id: Optional[str] = None):
        """Ask peer(s) to share their list of known nodes."""
        msg = create_message(
            msg_type=MSG_TYPE_DISCOVER_REQ,
            sender_id=self.node_id,
            sender_host=self.host,
            sender_port=self.port,
        )
        if target_id:
            conn = self.find_connection_by_id(target_id)
            if conn:
                self.send_to_node(conn, msg)
        else:
            self.send_to_nodes(msg)

    def send_hyper_multicast(self, edge_id: str, target_node_ids: Any, text: str) -> int:
        """
        Multicast a message to all members of a hyperedge that are currently connected.
        Returns the count of members the message was sent to.
        """
        sent_count = 0
        target_ids = set(target_node_ids) - {self.node_id}
        for target_id in target_ids:
            conn = self.find_connection_by_id(target_id)
            if conn:
                msg = create_message(
                    msg_type=MSG_TYPE_HYPER_MULTICAST,
                    sender_id=self.node_id,
                    sender_host=self.host,
                    sender_port=self.port,
                    payload=text,
                    target_id=target_id,
                    hyperedge_id=edge_id,
                )
                self.send_to_node(conn, msg)
                sent_count += 1
        self.log(colorize(f"Hyperedge [{edge_id}] multicast sent to {sent_count} peer(s): \"{text}\"", Colors.MAGENTA))
        return sent_count

    # -----------------------------------------------------------------------
    # Event Handlers (Inherited from Node)
    # -----------------------------------------------------------------------
    def inbound_node_connected(self, node):
        peer_id = str(node.id)
        with self.lock:
            self.known_peers[peer_id] = {"host": node.host, "port": node.port, "last_seen": time.time()}
        self.log(colorize(f"Inbound connection from [{peer_id}] ({node.host}:{node.port})", Colors.GREEN))
        TopologyCSVManager.log_event(
            source_id=self.node_id,
            target_id=peer_id,
            host=node.host,
            port=node.port,
            direction="inbound",
            status="connected",
        )
        if self.on_connect_cb:
            self.on_connect_cb(node, "inbound")

    def outbound_node_connected(self, node):
        peer_id = str(node.id)
        with self.lock:
            self.known_peers[peer_id] = {"host": node.host, "port": node.port, "last_seen": time.time()}
        self.log(colorize(f"Outbound connection established with [{peer_id}] ({node.host}:{node.port})", Colors.GREEN))
        TopologyCSVManager.log_event(
            source_id=self.node_id,
            target_id=peer_id,
            host=node.host,
            port=node.port,
            direction="outbound",
            status="connected",
        )
        if self.on_connect_cb:
            self.on_connect_cb(node, "outbound")

    def node_disconnected(self, node):
        super().node_disconnected(node)
        peer_id = str(node.id)
        with self.lock:
            self.latencies.pop(peer_id, None)
        self.log(colorize(f"Peer disconnected: [{peer_id}]", Colors.YELLOW))
        TopologyCSVManager.log_event(
            source_id=self.node_id,
            target_id=peer_id,
            host=getattr(node, "host", "127.0.0.1"),
            port=getattr(node, "port", 0),
            direction="unknown",
            status="disconnected",
        )
        if self.on_disconnect_cb:
            self.on_disconnect_cb(node, "disconnected")

    def node_message(self, node, data):
        """Handle incoming messages across the network."""
        self.message_count_recv += 1

        if not isinstance(data, dict):
            # Plain string message
            self.log(colorize(f"[MSG from {node.id}]: {data}", Colors.CYAN))
            if self.on_message_cb:
                self.on_message_cb({"type": "RAW", "payload": data, "sender_id": node.id}, node)
            return

        msg_type = data.get("type", "UNKNOWN")
        sender_id = data.get("sender_id", str(node.id))
        payload = data.get("payload")

        # Remember peer info
        if "sender_host" in data and "sender_port" in data:
            with self.lock:
                self.known_peers[sender_id] = {
                    "host": data["sender_host"],
                    "port": data["sender_port"],
                    "last_seen": time.time(),
                }

        # Dispatch by message type
        if msg_type == MSG_TYPE_PING:
            # Immediately reply with PONG
            ping_id = payload.get("ping_id") if isinstance(payload, dict) else None
            sent_at = payload.get("sent_at", time.time()) if isinstance(payload, dict) else time.time()
            pong = create_message(
                msg_type=MSG_TYPE_PONG,
                sender_id=self.node_id,
                sender_host=self.host,
                sender_port=self.port,
                target_id=sender_id,
                payload={"ping_id": ping_id, "sent_at": sent_at},
            )
            self.send_to_node(node, pong)

        elif msg_type == MSG_TYPE_PONG:
            # Measure RTT
            if isinstance(payload, dict) and "ping_id" in payload:
                pid = payload["ping_id"]
                sent_at = payload.get("sent_at")
                rtt = (time.time() - sent_at) * 1000.0 if sent_at else 0.0
                with self.lock:
                    if pid in self.pending_pings:
                        self.pending_pings[pid]["rtt"] = rtt
                        self.pending_pings[pid]["event"].set()
                    self.latencies[sender_id] = rtt

        elif msg_type == MSG_TYPE_CHAT:
            self.log(colorize(f"[DIRECT MSG from {sender_id}]: {payload}", Colors.CYAN))
            self.received_messages.append(data)

        elif msg_type == MSG_TYPE_BROADCAST:
            self.log(colorize(f"[BROADCAST from {sender_id}]: {payload}", Colors.MAGENTA))
            self.received_messages.append(data)

        elif msg_type == MSG_TYPE_HYPER_MULTICAST:
            edge_id = data.get("hyperedge_id", "UNKNOWN")
            self.log(colorize(f"[HYPERGRAPH {edge_id} from {sender_id}]: {payload}", Colors.MAGENTA))
            self.received_messages.append(data)

        elif msg_type == MSG_TYPE_DISCOVER_REQ:
            # Share list of known peers
            peers_list = [
                {"id": p_id, "host": p_info["host"], "port": p_info["port"]}
                for p_id, p_info in self.get_connected_peers().items()
            ]
            resp = create_message(
                msg_type=MSG_TYPE_DISCOVER_RESP,
                sender_id=self.node_id,
                sender_host=self.host,
                sender_port=self.port,
                target_id=sender_id,
                payload={"peers": peers_list},
            )
            self.send_to_node(node, resp)

        elif msg_type == MSG_TYPE_DISCOVER_RESP:
            if isinstance(payload, dict) and "peers" in payload:
                found = payload["peers"]
                self.log(colorize(f"Discovered {len(found)} peers via [{sender_id}]", Colors.BLUE))
                with self.lock:
                    for p in found:
                        if p["id"] != self.node_id:
                            self.known_peers[p["id"]] = {
                                "host": p["host"],
                                "port": p["port"],
                                "last_seen": time.time(),
                            }

        # Forward to user-supplied callback
        if self.on_message_cb:
            self.on_message_cb(data, node)

    # -----------------------------------------------------------------------
    # Status & Inspection
    # -----------------------------------------------------------------------
    def print_status(self):
        """Print formatted terminal summary of node status and connections."""
        peers = self.get_connected_peers()
        uptime = int(time.time() - self.start_time)
        backend = "p2pnetwork" if HAS_P2P_NETWORK_PKG else "standalone socket"

        print("\n" + "=" * 65)
        print(colorize(f"  NODE STATUS: {self.node_id}", Colors.BOLD + Colors.GREEN))
        print("=" * 65)
        print(f"  Address        : {self.host}:{self.port}")
        print(f"  Engine Backend : {backend}")
        print(f"  Uptime         : {uptime}s")
        print(f"  Inbound Peers  : {len(self.nodes_inbound)}")
        print(f"  Outbound Peers : {len(self.nodes_outbound)}")
        print(f"  Total Peers    : {len(peers)}")
        print("-" * 65)

        if not peers:
            print(colorize("  No peers currently connected.", Colors.YELLOW))
        else:
            print(f"  {'PEER ID':<15} {'ENDPOINT':<20} {'DIRECTION':<15} {'LATENCY'}")
            print("  " + "-" * 60)
            for pid, p in peers.items():
                lat = f"{p['latency_ms']:.2f} ms" if p["latency_ms"] is not None else "--"
                endpoint = f"{p['host']}:{p['port']}"
                print(f"  {pid:<15} {endpoint:<20} {p['direction']:<15} {lat}")

        print("=" * 65 + "\n")
