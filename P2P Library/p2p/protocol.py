"""
P2P Protocol Definitions and Message Utilities.
Defines message structures, types, and formatting helpers.
"""

import time
import uuid

# Message Types
MSG_TYPE_PING = "PING"
MSG_TYPE_PONG = "PONG"
MSG_TYPE_CHAT = "CHAT"
MSG_TYPE_BROADCAST = "BROADCAST"
MSG_TYPE_DISCOVER_REQ = "DISCOVER_REQ"
MSG_TYPE_DISCOVER_RESP = "DISCOVER_RESP"
MSG_TYPE_HEARTBEAT = "HEARTBEAT"
MSG_TYPE_HYPER_MULTICAST = "HYPER_MULTICAST"

# ANSI Terminal Colors
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"


def colorize(text: str, color: str) -> str:
    """Wrap text in ANSI color codes."""
    return f"{color}{text}{Colors.RESET}"


def create_message(
    msg_type: str,
    sender_id: str,
    sender_host: str,
    sender_port: int,
    payload: any = None,
    target_id: str = None,
    **kwargs
) -> dict:
    """Create a standardized protocol message dictionary."""
    msg = {
        "msg_id": str(uuid.uuid4())[:8],
        "type": msg_type,
        "sender_id": str(sender_id),
        "sender_host": sender_host,
        "sender_port": int(sender_port),
        "timestamp": time.time(),
        "payload": payload,
    }
    if target_id is not None:
        msg["target_id"] = str(target_id)
    msg.update(kwargs)
    return msg

