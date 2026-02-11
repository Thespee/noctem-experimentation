#!/usr/bin/env python3
"""
Stage 4: Install Python dependencies via pip.
"""

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage


class PythonDepsStage(Stage):
    """Install Python dependencies."""
    
    name = "python_deps"
    description = "Installing Python packages"
    birth_stage = BirthStage.PYTHON_DEPS
    
    # Required packages
    PACKAGES = [
        "requests",
        "beautifulsoup4",
        "ollama",  # Ollama Python client
    ]
    
    def check(self) -> bool:
        """Check if packages are already installed."""
        if self.birth_stage.name in self.state.completed_stages:
            return False
        
        # Try importing key packages
        for pkg in ["requests", "bs4", "ollama"]:
            try:
                __import__(pkg)
            except ImportError:
                return True
        
        return False
    
    def run(self) -> StageOutput:
        """Install Python packages."""
        # Upgrade pip first
        code, _, _ = self.run_command(
            ["pip3", "install", "--user", "--upgrade", "pip"],
            timeout=120
        )
        
        # Install packages
        success, msg = self.pip_install(self.PACKAGES)
        
        if not success:
            return StageOutput(
                result=StageResult.FAILED,
                message="Python package installation failed",
                error=msg
            )
        
        return StageOutput(
            result=StageResult.SUCCESS,
            message=f"Installed: {', '.join(self.PACKAGES)}"
        )
    
    def verify(self) -> bool:
        """Verify packages can be imported."""
        # Need to refresh sys.path after pip install
        import importlib
        import sys
        
        # Add user site-packages to path
        import site
        user_site = site.getusersitepackages()
        if user_site not in sys.path:
            sys.path.insert(0, user_site)
        
        for pkg in ["requests", "bs4", "ollama"]:
            try:
                importlib.import_module(pkg)
            except ImportError:
                self.logger.error(f"Failed to import {pkg}")
                return False
        
        return True
