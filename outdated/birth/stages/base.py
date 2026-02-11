#!/usr/bin/env python3
"""
Base class for birth stages.
"""

import subprocess
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum, auto

from ..state import BirthStage, BirthState

logger = logging.getLogger("noctem.birth.stages")


class StageResult(Enum):
    """Result of a stage execution."""
    SUCCESS = auto()
    FAILED = auto()
    SKIPPED = auto()
    RETRY = auto()


@dataclass
class StageOutput:
    """Output from a stage execution."""
    result: StageResult
    message: str
    error: Optional[str] = None
    data: Optional[dict] = None


class Stage(ABC):
    """
    Base class for birth stages.
    
    Each stage should:
    1. Check if it needs to run (check method)
    2. Execute the installation/setup (run method)
    3. Verify the result (verify method)
    """
    
    # Override in subclasses
    name: str = "base"
    description: str = "Base stage"
    birth_stage: BirthStage = BirthStage.INIT
    
    def __init__(self, state: BirthState):
        self.state = state
        self.logger = logging.getLogger(f"noctem.birth.stages.{self.name}")
    
    @abstractmethod
    def check(self) -> bool:
        """
        Check if this stage needs to run.
        Return True if stage should run, False to skip.
        """
        pass
    
    @abstractmethod
    def run(self) -> StageOutput:
        """
        Execute the stage.
        Return StageOutput with result.
        """
        pass
    
    def verify(self) -> bool:
        """
        Verify the stage completed successfully.
        Override in subclasses for custom verification.
        """
        return True
    
    def rollback(self):
        """
        Rollback changes if stage failed.
        Override in subclasses if rollback is possible.
        """
        pass
    
    def execute(self) -> StageOutput:
        """
        Full execution flow: check -> run -> verify.
        """
        from ..notify import notify_progress, notify_error
        
        # Check if we need to run
        if not self.check():
            self.logger.info(f"Stage {self.name} skipped (already complete)")
            return StageOutput(
                result=StageResult.SKIPPED,
                message=f"{self.name} already complete"
            )
        
        # Notify start
        notify_progress(self.name, f"Starting: {self.description}")
        
        # Run the stage
        try:
            output = self.run()
        except Exception as e:
            self.logger.error(f"Stage {self.name} exception: {e}")
            notify_error(self.name, str(e))
            return StageOutput(
                result=StageResult.FAILED,
                message=f"{self.name} failed",
                error=str(e)
            )
        
        # Handle result
        if output.result == StageResult.SUCCESS:
            # Verify
            if self.verify():
                notify_progress(self.name, f"Complete: {output.message}", "✅")
                return output
            else:
                notify_error(self.name, "Verification failed")
                return StageOutput(
                    result=StageResult.FAILED,
                    message=f"{self.name} verification failed",
                    error="Post-run verification failed"
                )
        
        elif output.result == StageResult.FAILED:
            notify_error(self.name, output.error or "Unknown error")
            self.rollback()
        
        return output
    
    # Utility methods for subclasses
    
    def run_command(
        self,
        cmd: List[str],
        timeout: int = 300,
        check: bool = True,
        capture: bool = True
    ) -> Tuple[int, str, str]:
        """
        Run a shell command.
        
        Returns:
            (return_code, stdout, stderr)
        """
        self.logger.debug(f"Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture,
                text=True,
                timeout=timeout
            )
            
            stdout = result.stdout if capture else ""
            stderr = result.stderr if capture else ""
            
            if check and result.returncode != 0:
                self.logger.error(f"Command failed: {stderr}")
            
            return result.returncode, stdout, stderr
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Command timed out: {' '.join(cmd)}")
            return -1, "", "Command timed out"
        except FileNotFoundError:
            self.logger.error(f"Command not found: {cmd[0]}")
            return -1, "", f"Command not found: {cmd[0]}"
        except Exception as e:
            self.logger.error(f"Command error: {e}")
            return -1, "", str(e)
    
    def run_sudo(
        self,
        cmd: List[str],
        timeout: int = 300
    ) -> Tuple[int, str, str]:
        """Run a command with sudo."""
        return self.run_command(["sudo"] + cmd, timeout=timeout)
    
    def apt_install(self, packages: List[str]) -> Tuple[bool, str]:
        """Install packages via apt."""
        # Update first
        code, _, err = self.run_sudo(["apt-get", "update"], timeout=120)
        if code != 0:
            return False, f"apt update failed: {err}"
        
        # Install
        code, out, err = self.run_sudo(
            ["apt-get", "install", "-y"] + packages,
            timeout=600
        )
        
        if code != 0:
            return False, f"apt install failed: {err}"
        
        return True, f"Installed: {', '.join(packages)}"
    
    def pip_install(self, packages: List[str], user: bool = True) -> Tuple[bool, str]:
        """Install packages via pip."""
        cmd = ["pip3", "install"]
        if user:
            cmd.append("--user")
        cmd.extend(packages)
        
        code, out, err = self.run_command(cmd, timeout=300)
        
        if code != 0:
            return False, f"pip install failed: {err}"
        
        return True, f"Installed: {', '.join(packages)}"
    
    def check_command_exists(self, command: str) -> bool:
        """Check if a command is available."""
        code, _, _ = self.run_command(["which", command], check=False)
        return code == 0
    
    def check_service_running(self, service: str) -> bool:
        """Check if a systemd service is running."""
        code, _, _ = self.run_command(
            ["systemctl", "is-active", "--quiet", service],
            check=False
        )
        return code == 0
