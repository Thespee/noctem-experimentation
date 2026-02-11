#!/usr/bin/env python3
"""
Stage 5: Install Ollama and pull required models.
"""

import time
import urllib.request
import urllib.error
import json

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage


class OllamaStage(Stage):
    """Install Ollama and pull models."""
    
    name = "ollama"
    description = "Setting up Ollama AI"
    birth_stage = BirthStage.OLLAMA
    
    # Models to pull
    MODELS = [
        "qwen2.5:1.5b-instruct-q4_K_M",  # Fast router model
        "qwen2.5:7b-instruct-q4_K_M",     # Main worker model
    ]
    
    def check(self) -> bool:
        """Check if Ollama is installed and models are pulled."""
        if self.birth_stage.name in self.state.completed_stages:
            return False
        
        # Check if ollama command exists
        if not self.check_command_exists("ollama"):
            return True
        
        # Check if service is running and models exist
        if not self._is_ollama_running():
            return True
        
        return not self._models_exist()
    
    def run(self) -> StageOutput:
        """Install Ollama and pull models."""
        from ..notify import notify_progress
        
        # Install Ollama if needed
        if not self.check_command_exists("ollama"):
            notify_progress(self.name, "Installing Ollama...")
            
            # Download and run install script
            code, out, err = self.run_command(
                ["curl", "-fsSL", "https://ollama.ai/install.sh"],
                timeout=60
            )
            if code != 0:
                return StageOutput(
                    result=StageResult.FAILED,
                    message="Failed to download Ollama installer",
                    error=err
                )
            
            # Run installer with sudo
            code, out, err = self.run_command(
                ["bash", "-c", "curl -fsSL https://ollama.ai/install.sh | sh"],
                timeout=300
            )
            if code != 0:
                return StageOutput(
                    result=StageResult.FAILED,
                    message="Ollama installation failed",
                    error=err
                )
        
        # Start Ollama service
        notify_progress(self.name, "Starting Ollama service...")
        self.run_sudo(["systemctl", "enable", "ollama"])
        self.run_sudo(["systemctl", "start", "ollama"])
        
        # Wait for service to be ready
        for _ in range(30):
            if self._is_ollama_running():
                break
            time.sleep(2)
        else:
            return StageOutput(
                result=StageResult.FAILED,
                message="Ollama service failed to start",
                error="Service not responding after 60 seconds"
            )
        
        # Pull models
        for model in self.MODELS:
            notify_progress(self.name, f"Pulling model: {model} (this may take a while)...")
            
            code, out, err = self.run_command(
                ["ollama", "pull", model],
                timeout=1800  # 30 min timeout per model
            )
            
            if code != 0:
                return StageOutput(
                    result=StageResult.FAILED,
                    message=f"Failed to pull model: {model}",
                    error=err
                )
        
        return StageOutput(
            result=StageResult.SUCCESS,
            message=f"Ollama ready with {len(self.MODELS)} models"
        )
    
    def _is_ollama_running(self) -> bool:
        """Check if Ollama API is responding."""
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            urllib.request.urlopen(req, timeout=5)
            return True
        except:
            return False
    
    def _models_exist(self) -> bool:
        """Check if required models are already pulled."""
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                models = [m["name"] for m in data.get("models", [])]
                
                for required in self.MODELS:
                    # Check if model name matches (may have :latest suffix)
                    base_name = required.split(":")[0]
                    if not any(base_name in m for m in models):
                        return False
                return True
        except:
            return False
    
    def verify(self) -> bool:
        """Verify Ollama is working."""
        return self._is_ollama_running() and self._models_exist()
