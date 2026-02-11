#!/usr/bin/env python3
"""
Parent CLI - Remote supervision for Noctem.

Usage:
    parent status              Get current Noctem status
    parent history [--hours N] Get task history
    parent health              Check system health
    parent report              Generate babysitting report
    parent improve             Analyze and suggest improvements
    parent watch [--interval]  Continuous monitoring mode
    parent config              Configure connection settings
"""

import argparse
import json
import socket
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

from .protocol import ParentCommand, ParentRequest

# Configuration
CONFIG_DIR = Path.home() / ".config" / "noctem-parent"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Signal daemon settings
SIGNAL_CLI = "signal-cli"


class ParentCLI:
    """Parent CLI for remote Noctem supervision."""
    
    def __init__(self):
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text())
            except json.JSONDecodeError:
                pass
        return {}
    
    def _save_config(self, config: Dict[str, Any]):
        """Save configuration to file."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(config, indent=2))
        self.config = config
    
    @property
    def my_number(self) -> Optional[str]:
        return self.config.get("my_number")
    
    @property
    def noctem_number(self) -> Optional[str]:
        return self.config.get("noctem_number")
    
    def send_command(self, command: ParentCommand, params: Dict = None) -> Optional[str]:
        """Send a command to Noctem via Signal and wait for response."""
        if not self.my_number or not self.noctem_number:
            print("Error: Not configured. Run 'parent config' first.")
            return None
        
        # Build request
        request = ParentRequest(command=command, params=params or {})
        message = request.to_signal_message()
        
        # Send via signal-cli
        try:
            result = subprocess.run(
                [SIGNAL_CLI, "-u", self.my_number, "send", "-m", message, self.noctem_number],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                print(f"Failed to send: {result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            print("Timeout sending message")
            return None
        except FileNotFoundError:
            print(f"Error: {SIGNAL_CLI} not found. Install signal-cli first.")
            return None
        
        # Wait for response
        print("Waiting for response", end="", flush=True)
        
        for _ in range(60):  # Wait up to 60 seconds
            time.sleep(1)
            print(".", end="", flush=True)
            
            try:
                result = subprocess.run(
                    [SIGNAL_CLI, "-u", self.my_number, "receive", "--timeout", "1", "-o", "json"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.stdout:
                    # Parse JSON output
                    for line in result.stdout.strip().split('\n'):
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            envelope = data.get("envelope", {})
                            source = envelope.get("sourceNumber") or envelope.get("source")
                            
                            # Check if from Noctem
                            if source == self.noctem_number:
                                msg = envelope.get("dataMessage", {}).get("message")
                                if msg:
                                    print()  # Newline after dots
                                    return msg
                            
                            # Also check syncMessage for messages from self
                            sync = envelope.get("syncMessage", {}).get("sentMessage", {})
                            if sync:
                                dest = sync.get("destinationNumber")
                                if dest == self.noctem_number:
                                    # This is our outgoing message, ignore
                                    continue
                                    
                        except json.JSONDecodeError:
                            continue
                            
            except subprocess.TimeoutExpired:
                continue
            except Exception as e:
                print(f"\nError receiving: {e}")
                continue
        
        print("\nNo response received (timeout)")
        return None
    
    def cmd_status(self, args):
        """Get Noctem status."""
        response = self.send_command(ParentCommand.STATUS)
        if response:
            print(response)
    
    def cmd_history(self, args):
        """Get task history."""
        params = {"limit": args.limit, "since_hours": args.hours}
        response = self.send_command(ParentCommand.HISTORY, params)
        if response:
            print(response)
    
    def cmd_health(self, args):
        """Check system health."""
        response = self.send_command(ParentCommand.HEALTH)
        if response:
            print(response)
    
    def cmd_logs(self, args):
        """Get recent logs."""
        params = {"lines": args.lines}
        response = self.send_command(ParentCommand.LOGS, params)
        if response:
            print(response)
    
    def cmd_report(self, args):
        """Generate babysitting report."""
        response = self.send_command(ParentCommand.REPORT)
        if response:
            print(response)
    
    def cmd_improve(self, args):
        """Analyze and suggest improvements using Warp."""
        print("Gathering Noctem state for analysis...")
        
        # Collect data
        status = self.send_command(ParentCommand.STATUS)
        history = self.send_command(ParentCommand.HISTORY, {"limit": 50, "since_hours": 48})
        health = self.send_command(ParentCommand.HEALTH)
        logs = self.send_command(ParentCommand.LOGS, {"lines": 100})
        
        # Create context for Warp
        context = f"""# Noctem Analysis Context

## Current Status
{status or 'Unable to fetch'}

## Recent History (48h)
{history or 'Unable to fetch'}

## Health Check
{health or 'Unable to fetch'}

## Recent Logs
{logs or 'Unable to fetch'}

---

## Your Task

Analyze the above Noctem state and:
1. Identify any issues or inefficiencies
2. Suggest specific improvements to the codebase
3. Generate code patches for the most impactful improvements

Focus on:
- Error patterns that could be prevented
- Performance optimizations
- New skills that would be useful based on task patterns
- Configuration improvements

For each improvement:
- Explain the problem
- Describe the solution
- Provide a diff/patch if applicable
"""
        
        # Write context to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(context)
            context_file = f.name
        
        print(f"\nContext saved to: {context_file}")
        
        if args.warp:
            print("\nLaunching Warp for analysis...")
            try:
                subprocess.run(["warp", "--file", context_file])
            except FileNotFoundError:
                print("Warp CLI not found. Opening context file instead...")
                subprocess.run(["xdg-open", context_file])
        else:
            print("\nContext ready. Options:")
            print(f"  1. Open in Warp: warp --file {context_file}")
            print(f"  2. View: cat {context_file}")
            print(f"  3. Copy and paste into your preferred AI tool")
    
    def cmd_watch(self, args):
        """Continuous monitoring mode."""
        interval = args.interval
        print(f"Starting watch mode (interval: {interval}s, Ctrl+C to stop)")
        print("=" * 50)
        
        try:
            while True:
                response = self.send_command(ParentCommand.REPORT)
                if response:
                    # Clear screen and print
                    print("\033[2J\033[H", end="")  # ANSI clear
                    print(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                    print("=" * 50)
                    print(response)
                
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nWatch mode stopped.")
    
    def cmd_approve(self, args):
        """Approve an improvement."""
        params = {"id": args.id}
        response = self.send_command(ParentCommand.APPROVE, params)
        if response:
            print(response)
    
    def cmd_reject(self, args):
        """Reject an improvement."""
        params = {"id": args.id}
        response = self.send_command(ParentCommand.REJECT, params)
        if response:
            print(response)
    
    def cmd_config(self, args):
        """Configure parent settings."""
        print("Noctem Parent Configuration")
        print("-" * 30)
        
        current_my = self.config.get("my_number", "(not set)")
        current_noctem = self.config.get("noctem_number", "(not set)")
        
        print(f"Current settings:")
        print(f"  Your number: {current_my}")
        print(f"  Noctem number: {current_noctem}")
        print()
        
        my_number = input(f"Your Signal phone number [{current_my}]: ").strip()
        if not my_number and self.my_number:
            my_number = self.my_number
        
        noctem_number = input(f"Noctem's Signal number [{current_noctem}]: ").strip()
        if not noctem_number and self.noctem_number:
            noctem_number = self.noctem_number
        
        if my_number and noctem_number:
            self._save_config({
                "my_number": my_number,
                "noctem_number": noctem_number
            })
            print("\nConfiguration saved!")
        else:
            print("\nConfiguration not saved (missing values)")


def main():
    """Main entry point."""
    cli = ParentCLI()
    
    parser = argparse.ArgumentParser(
        description="Parent - Remote supervision for Noctem",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Status
    subparsers.add_parser("status", help="Get current Noctem status")
    
    # History
    history_parser = subparsers.add_parser("history", help="Get task history")
    history_parser.add_argument("--hours", type=int, default=24, help="Hours of history")
    history_parser.add_argument("--limit", type=int, default=20, help="Max items")
    
    # Health
    subparsers.add_parser("health", help="Check system health")
    
    # Logs
    logs_parser = subparsers.add_parser("logs", help="Get recent logs")
    logs_parser.add_argument("--lines", type=int, default=50, help="Number of lines")
    
    # Report
    subparsers.add_parser("report", help="Generate babysitting report")
    
    # Improve
    improve_parser = subparsers.add_parser("improve", help="Analyze and suggest improvements")
    improve_parser.add_argument("--warp", action="store_true", help="Launch Warp automatically")
    
    # Watch
    watch_parser = subparsers.add_parser("watch", help="Continuous monitoring")
    watch_parser.add_argument("--interval", type=int, default=300, help="Seconds between updates")
    
    # Approve
    approve_parser = subparsers.add_parser("approve", help="Approve an improvement")
    approve_parser.add_argument("id", type=int, help="Improvement ID")
    
    # Reject
    reject_parser = subparsers.add_parser("reject", help="Reject an improvement")
    reject_parser.add_argument("id", type=int, help="Improvement ID")
    
    # Config
    subparsers.add_parser("config", help="Configure parent settings")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    commands = {
        "status": cli.cmd_status,
        "history": cli.cmd_history,
        "health": cli.cmd_health,
        "logs": cli.cmd_logs,
        "report": cli.cmd_report,
        "improve": cli.cmd_improve,
        "watch": cli.cmd_watch,
        "approve": cli.cmd_approve,
        "reject": cli.cmd_reject,
        "config": cli.cmd_config,
    }
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
