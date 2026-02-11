#!/usr/bin/env python3
"""
Stage 7: Initialize Noctem database and configuration.
"""

import json
import sys
from pathlib import Path

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage


class NoctemInitStage(Stage):
    """Initialize Noctem database and config."""
    
    name = "noctem_init"
    description = "Initializing Noctem"
    birth_stage = BirthStage.NOCTEM_INIT
    
    def check(self) -> bool:
        """Check if Noctem is already initialized."""
        if self.birth_stage.name in self.state.completed_stages:
            return False
        
        noctem_dir = Path(__file__).parent.parent.parent
        config_file = noctem_dir / "data" / "config.json"
        db_file = noctem_dir / "data" / "noctem.db"
        
        return not (config_file.exists() and db_file.exists())
    
    def run(self) -> StageOutput:
        """Initialize Noctem."""
        from ..notify import notify_progress
        
        noctem_dir = Path(__file__).parent.parent.parent
        data_dir = noctem_dir / "data"
        
        # Create data directory
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Create config.json
        notify_progress(self.name, "Creating configuration...")
        config_file = data_dir / "config.json"
        config_example = data_dir / "config.json.example"
        
        if not config_file.exists():
            if config_example.exists():
                # Copy from example
                config = json.loads(config_example.read_text())
            else:
                # Create default config
                config = {
                    "signal_phone": "",
                    "model": "qwen2.5:7b-instruct-q4_K_M",
                    "router_model": "qwen2.5:1.5b-instruct-q4_K_M",
                    "quick_chat_max_length": 80,
                    "boot_notification": True
                }
            
            # Merge with birth state config
            if "signal_phone" in self.state.config:
                config["signal_phone"] = self.state.config["signal_phone"]
            
            config_file.write_text(json.dumps(config, indent=2))
        
        # Initialize database
        notify_progress(self.name, "Creating database...")
        
        # Add Noctem to Python path
        sys.path.insert(0, str(noctem_dir))
        
        try:
            import state as noctem_state
            noctem_state.init_db()
        except Exception as e:
            return StageOutput(
                result=StageResult.FAILED,
                message="Database initialization failed",
                error=str(e)
            )
        
        # Create logs directory
        logs_dir = noctem_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        return StageOutput(
            result=StageResult.SUCCESS,
            message="Noctem initialized"
        )
    
    def verify(self) -> bool:
        """Verify Noctem is initialized."""
        noctem_dir = Path(__file__).parent.parent.parent
        config_file = noctem_dir / "data" / "config.json"
        db_file = noctem_dir / "data" / "noctem.db"
        
        return config_file.exists() and db_file.exists()
