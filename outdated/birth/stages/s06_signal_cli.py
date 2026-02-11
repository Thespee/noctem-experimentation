#!/usr/bin/env python3
"""
Stage 6: Install signal-cli.

Note: signal-cli registration must be done manually BEFORE birth.
This stage only installs signal-cli and verifies it's registered.
"""

import os
from pathlib import Path

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage


class SignalCliStage(Stage):
    """Install signal-cli."""
    
    name = "signal_cli"
    description = "Setting up Signal messaging"
    birth_stage = BirthStage.SIGNAL_CLI
    
    # signal-cli version and download URL
    SIGNAL_CLI_VERSION = "0.13.4"
    SIGNAL_CLI_URL = f"https://github.com/AsamK/signal-cli/releases/download/v{SIGNAL_CLI_VERSION}/signal-cli-{SIGNAL_CLI_VERSION}-Linux.tar.gz"
    INSTALL_DIR = "/opt/signal-cli"
    
    def check(self) -> bool:
        """Check if signal-cli is installed."""
        if self.birth_stage.name in self.state.completed_stages:
            return False
        
        return not self.check_command_exists("signal-cli")
    
    def run(self) -> StageOutput:
        """Install signal-cli."""
        from ..notify import notify_progress
        
        # Check if Java is available
        if not self.check_command_exists("java"):
            return StageOutput(
                result=StageResult.FAILED,
                message="Java not found",
                error="Install Java first (stage 3)"
            )
        
        notify_progress(self.name, "Downloading signal-cli...")
        
        # Create install directory
        code, _, err = self.run_sudo(["mkdir", "-p", self.INSTALL_DIR])
        if code != 0:
            return StageOutput(
                result=StageResult.FAILED,
                message="Failed to create install directory",
                error=err
            )
        
        # Download signal-cli
        code, _, err = self.run_command(
            ["wget", "-q", "-O", "/tmp/signal-cli.tar.gz", self.SIGNAL_CLI_URL],
            timeout=120
        )
        if code != 0:
            return StageOutput(
                result=StageResult.FAILED,
                message="Failed to download signal-cli",
                error=err
            )
        
        # Extract
        notify_progress(self.name, "Installing signal-cli...")
        code, _, err = self.run_sudo(
            ["tar", "-xzf", "/tmp/signal-cli.tar.gz", "-C", self.INSTALL_DIR, "--strip-components=1"],
            timeout=60
        )
        if code != 0:
            return StageOutput(
                result=StageResult.FAILED,
                message="Failed to extract signal-cli",
                error=err
            )
        
        # Create symlink
        self.run_sudo(["ln", "-sf", f"{self.INSTALL_DIR}/bin/signal-cli", "/usr/local/bin/signal-cli"])
        
        # Clean up
        self.run_command(["rm", "-f", "/tmp/signal-cli.tar.gz"])
        
        # Check if already registered
        phone = self.state.config.get("signal_phone")
        if phone:
            code, out, err = self.run_command(
                ["signal-cli", "-u", phone, "listAccounts"],
                timeout=30
            )
            if code == 0 and phone in out:
                return StageOutput(
                    result=StageResult.SUCCESS,
                    message=f"signal-cli installed and registered to {phone}"
                )
        
        # Not registered - provide instructions
        return StageOutput(
            result=StageResult.SUCCESS,
            message="signal-cli installed (registration required)",
            data={
                "needs_registration": True,
                "instructions": (
                    "Register signal-cli with your phone:\n"
                    "1. signal-cli -u +YOURNUMBER register\n"
                    "2. signal-cli -u +YOURNUMBER verify CODE\n"
                    "3. Add signal_phone to config.json"
                )
            }
        )
    
    def verify(self) -> bool:
        """Verify signal-cli is installed."""
        return self.check_command_exists("signal-cli")
