#!/usr/bin/env python3
"""
Noctem Signal Send Skill
Send messages via Signal using signal-cli daemon (JSON-RPC).
"""

import json
import socket
from typing import Dict, Any
from .base import Skill, SkillResult, SkillContext, register_skill

# Must match signal_receiver.py
SIGNAL_DAEMON_HOST = "127.0.0.1"
SIGNAL_DAEMON_PORT = 7583


@register_skill
class SignalSendSkill(Skill):
    """Send messages via Signal."""
    
    name = "signal_send"
    description = "Send a message via Signal messenger. Use to notify the user or send results."
    parameters = {
        "message": "string - the message to send",
        "recipient": "string (optional) - phone number to send to, defaults to owner"
    }
    
    def run(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        message = params.get("message", "")
        recipient = params.get("recipient")
        
        if not message:
            return SkillResult(
                success=False,
                output="",
                error="No message provided"
            )
        
        # Get phone number from config or params
        phone = recipient or context.config.get("signal_phone")
        
        if not phone:
            return SkillResult(
                success=False,
                output="",
                error="No recipient specified and no default signal_phone in config"
            )
        
        # Truncate very long messages (Signal has limits)
        if len(message) > 2000:
            message = message[:1997] + "..."
        
        try:
            # Send via JSON-RPC to signal-cli daemon
            request = {
                "jsonrpc": "2.0",
                "method": "send",
                "params": {
                    "recipient": [phone],
                    "message": message
                },
                "id": 1
            }
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            sock.connect((SIGNAL_DAEMON_HOST, SIGNAL_DAEMON_PORT))
            sock.sendall((json.dumps(request) + "\n").encode())
            
            # Read response
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
            if "error" in result:
                return SkillResult(
                    success=False,
                    output="",
                    error=f"Signal daemon error: {result['error']}"
                )
            
            return SkillResult(
                success=True,
                output=f"Message sent to {phone}",
                data={"recipient": phone, "message_length": len(message)}
            )
                
        except ConnectionRefusedError:
            return SkillResult(
                success=False,
                output="",
                error=f"signal-cli daemon not running. Start with: signal-cli -a PHONE daemon --tcp 127.0.0.1:{SIGNAL_DAEMON_PORT}"
            )
        except socket.timeout:
            return SkillResult(
                success=False,
                output="",
                error="Signal send timed out"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                output="",
                error=f"Failed to send message: {str(e)}"
            )


if __name__ == "__main__":
    # Test (won't actually send without proper config)
    skill = SignalSendSkill()
    ctx = SkillContext(config={"signal_phone": "+1234567890"})
    
    result = skill.execute({"message": "Test message"}, ctx)
    print(f"Test result: {result}")
