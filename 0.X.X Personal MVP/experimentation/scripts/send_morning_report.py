#!/usr/bin/env python3
"""
Send morning report via Signal.
Called by systemd timer at 8am.
"""

import sys
import json
import socket
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.morning_report import generate_morning_report
from skill_runner import load_config

SIGNAL_DAEMON_HOST = "127.0.0.1"
SIGNAL_DAEMON_PORT = 7583


def send_signal_message(phone: str, message: str) -> bool:
    """Send a message via signal-cli daemon JSON-RPC."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SIGNAL_DAEMON_HOST, SIGNAL_DAEMON_PORT))
        sock.settimeout(30)
        
        request = {
            "jsonrpc": "2.0",
            "method": "send",
            "params": {
                "recipient": [phone],
                "message": message
            },
            "id": 1
        }
        
        sock.sendall((json.dumps(request) + "\n").encode())
        
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\n" in response:
                break
        
        sock.close()
        
        result = json.loads(response.decode().strip())
        return "result" in result
        
    except Exception as e:
        print(f"Error sending message: {e}")
        return False


def main():
    config = load_config()
    phone = config.get("signal_phone")
    
    if not phone or phone == "+1YOURNUMBER":
        print("Signal phone not configured in data/config.json")
        sys.exit(1)
    
    report = generate_morning_report()
    
    if send_signal_message(phone, report):
        print(f"Morning report sent to {phone}")
    else:
        print("Failed to send morning report")
        sys.exit(1)


if __name__ == "__main__":
    main()
