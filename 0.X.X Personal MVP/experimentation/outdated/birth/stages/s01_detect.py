#!/usr/bin/env python3
"""
Stage 1: Detect first boot and check environment.
"""

import os
import platform
from pathlib import Path

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage


class DetectStage(Stage):
    """Detect first boot and validate environment."""
    
    name = "detect"
    description = "Detecting environment"
    birth_stage = BirthStage.DETECT
    
    def check(self) -> bool:
        """Always run detection."""
        return self.birth_stage.name not in self.state.completed_stages
    
    def run(self) -> StageOutput:
        """Detect and validate environment."""
        issues = []
        info = {}
        
        # Check OS
        info["os"] = platform.system()
        info["os_release"] = platform.release()
        info["machine"] = platform.machine()
        
        if info["os"] != "Linux":
            issues.append(f"Expected Linux, got {info['os']}")
        
        # Check for Ubuntu
        if Path("/etc/lsb-release").exists():
            with open("/etc/lsb-release") as f:
                lsb = f.read()
                if "Ubuntu" in lsb:
                    info["distro"] = "Ubuntu"
                    # Extract version
                    for line in lsb.split("\n"):
                        if line.startswith("DISTRIB_RELEASE="):
                            info["distro_version"] = line.split("=")[1]
        elif Path("/etc/os-release").exists():
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("ID="):
                        info["distro"] = line.split("=")[1].strip().strip('"')
                    if line.startswith("VERSION_ID="):
                        info["distro_version"] = line.split("=")[1].strip().strip('"')
        
        # Check if running as root (bad) or has sudo (good)
        info["is_root"] = os.geteuid() == 0
        if info["is_root"]:
            issues.append("Running as root - please run as normal user with sudo access")
        
        # Check sudo access
        code, _, _ = self.run_command(["sudo", "-n", "true"], check=False)
        info["has_sudo"] = code == 0
        if not info["has_sudo"] and not info["is_root"]:
            issues.append("No passwordless sudo access - configure with: sudo visudo")
        
        # Check architecture
        if info["machine"] not in ["x86_64", "aarch64", "arm64"]:
            issues.append(f"Unsupported architecture: {info['machine']}")
        
        # Check disk space (need at least 20GB free)
        try:
            stat = os.statvfs("/")
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
            info["disk_free_gb"] = round(free_gb, 1)
            if free_gb < 20:
                issues.append(f"Low disk space: {free_gb:.1f}GB free (need 20GB+)")
        except:
            pass
        
        # Check RAM (need at least 4GB)
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        info["ram_gb"] = round(kb / (1024**2), 1)
                        if info["ram_gb"] < 4:
                            issues.append(f"Low RAM: {info['ram_gb']}GB (need 4GB+)")
                        break
        except:
            pass
        
        # Store info in state
        self.state.config["environment"] = info
        
        if issues:
            return StageOutput(
                result=StageResult.FAILED,
                message="Environment check failed",
                error="; ".join(issues),
                data=info
            )
        
        return StageOutput(
            result=StageResult.SUCCESS,
            message=f"Environment OK: {info.get('distro', 'Linux')} {info.get('distro_version', '')}",
            data=info
        )
    
    def verify(self) -> bool:
        """Verify detection completed."""
        return "environment" in self.state.config
