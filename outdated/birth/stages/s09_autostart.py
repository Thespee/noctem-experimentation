#!/usr/bin/env python3
"""
Stage 9: Setup systemd auto-start service.
"""

import os
import getpass
from pathlib import Path

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage


class AutostartStage(Stage):
    """Setup systemd auto-start."""
    
    name = "autostart"
    description = "Configuring auto-start"
    birth_stage = BirthStage.AUTOSTART
    
    SERVICE_NAME = "noctem.service"
    SERVICE_PATH = f"/etc/systemd/system/{SERVICE_NAME}"
    
    SERVICE_TEMPLATE = """[Unit]
Description=Noctem Personal AI Assistant
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={working_dir}
ExecStart=/usr/bin/python3 {main_script} --headless
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment
Environment=HOME={home}
Environment=PATH=/usr/local/bin:/usr/bin:/bin

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={working_dir}
PrivateTmp=true

[Install]
WantedBy=multi-user.target
"""
    
    def check(self) -> bool:
        """Check if service is already installed."""
        if self.birth_stage.name in self.state.completed_stages:
            return False
        
        return not Path(self.SERVICE_PATH).exists()
    
    def run(self) -> StageOutput:
        """Install systemd service."""
        from ..notify import notify_progress
        
        noctem_dir = Path(__file__).parent.parent.parent
        
        # Get user info
        user = getpass.getuser()
        try:
            import grp
            group = grp.getgrgid(os.getgid()).gr_name
        except:
            group = user
        
        home = os.environ.get("HOME", f"/home/{user}")
        
        # Generate service file
        service_content = self.SERVICE_TEMPLATE.format(
            user=user,
            group=group,
            working_dir=noctem_dir,
            main_script=noctem_dir / "main.py",
            home=home
        )
        
        notify_progress(self.name, "Creating systemd service...")
        
        # Write to temp file
        temp_path = Path("/tmp/noctem.service")
        temp_path.write_text(service_content)
        
        # Copy to systemd directory
        code, _, err = self.run_sudo(["cp", str(temp_path), self.SERVICE_PATH])
        if code != 0:
            return StageOutput(
                result=StageResult.FAILED,
                message="Failed to install service",
                error=err
            )
        
        # Set permissions
        self.run_sudo(["chmod", "644", self.SERVICE_PATH])
        
        # Reload systemd
        self.run_sudo(["systemctl", "daemon-reload"])
        
        # Enable service
        code, _, err = self.run_sudo(["systemctl", "enable", self.SERVICE_NAME])
        if code != 0:
            return StageOutput(
                result=StageResult.FAILED,
                message="Failed to enable service",
                error=err
            )
        
        # Clean up
        temp_path.unlink()
        
        return StageOutput(
            result=StageResult.SUCCESS,
            message=f"Auto-start enabled: {self.SERVICE_NAME}"
        )
    
    def verify(self) -> bool:
        """Verify service is installed."""
        # Check if service file exists
        if not Path(self.SERVICE_PATH).exists():
            return False
        
        # Check if enabled
        code, out, _ = self.run_command(
            ["systemctl", "is-enabled", self.SERVICE_NAME],
            check=False
        )
        return "enabled" in out
