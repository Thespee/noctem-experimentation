#!/usr/bin/env python3
"""
Stage 3: Install system dependencies via apt.
"""

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage


class SystemDepsStage(Stage):
    """Install system dependencies."""
    
    name = "system_deps"
    description = "Installing system packages"
    birth_stage = BirthStage.SYSTEM_DEPS
    
    # Required packages
    PACKAGES = [
        # Python
        "python3",
        "python3-pip",
        "python3-venv",
        
        # For signal-cli
        "openjdk-17-jre-headless",
        
        # Networking and utilities
        "curl",
        "wget",
        "jq",
        "openssh-server",
        "openssh-client",
        
        # For web skills
        "ca-certificates",
        
        # exFAT support for shared partition
        "exfatprogs",
    ]
    
    def check(self) -> bool:
        """Check if packages are already installed."""
        if self.birth_stage.name in self.state.completed_stages:
            return False
        
        # Quick check for key packages
        for pkg in ["python3", "java", "curl"]:
            if not self.check_command_exists(pkg):
                return True
        
        return False
    
    def run(self) -> StageOutput:
        """Install system packages."""
        from ..notify import notify_progress
        
        notify_progress(self.name, f"Installing {len(self.PACKAGES)} packages...")
        
        # Update package list
        code, _, err = self.run_sudo(["apt-get", "update"], timeout=120)
        if code != 0:
            return StageOutput(
                result=StageResult.FAILED,
                message="apt update failed",
                error=err
            )
        
        # Install packages
        code, out, err = self.run_sudo(
            ["apt-get", "install", "-y", "--no-install-recommends"] + self.PACKAGES,
            timeout=900  # 15 minutes for all packages
        )
        
        if code != 0:
            return StageOutput(
                result=StageResult.FAILED,
                message="Package installation failed",
                error=err
            )
        
        # Enable SSH service
        self.run_sudo(["systemctl", "enable", "ssh"])
        self.run_sudo(["systemctl", "start", "ssh"])
        
        return StageOutput(
            result=StageResult.SUCCESS,
            message=f"Installed {len(self.PACKAGES)} packages"
        )
    
    def verify(self) -> bool:
        """Verify key packages installed."""
        checks = [
            self.check_command_exists("python3"),
            self.check_command_exists("pip3"),
            self.check_command_exists("java"),
            self.check_command_exists("curl"),
        ]
        return all(checks)
