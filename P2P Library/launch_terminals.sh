#!/usr/bin/env bash
# ==============================================================================
# Launch 5 Separate Terminal Windows on macOS for Node-1 to Node-5
# ==============================================================================

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Launching 5 P2P Node terminals..."

osascript <<EOF
tell application "Terminal"
    activate
    do script "cd '$DIR' && python3 node_cli.py --id Node-1 --port 8001"
    delay 0.3
    do script "cd '$DIR' && python3 node_cli.py --id Node-2 --port 8002"
    delay 0.3
    do script "cd '$DIR' && python3 node_cli.py --id Node-3 --port 8003"
    delay 0.3
    do script "cd '$DIR' && python3 node_cli.py --id Node-4 --port 8004"
    delay 0.3
    do script "cd '$DIR' && python3 node_cli.py --id Node-5 --port 8005"
end tell
EOF

echo "✓ 5 Terminal windows opened for Node-1 (8001) through Node-5 (8005)."
echo "You can now connect them using 'connect 127.0.0.1 <port>' in each terminal!"

