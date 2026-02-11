#!/usr/bin/env python3
"""
Stage 10: Cleanup birth artifacts and finalize.
"""

from pathlib import Path

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage, clear_state
from ..umbilical import close_tunnel


class CleanupStage(Stage):
    """Cleanup birth artifacts."""
    
    name = "cleanup"
    description = "Finalizing installation"
    birth_stage = BirthStage.CLEANUP
    
    def check(self) -> bool:
        """Always run cleanup."""
        return self.birth_stage.name not in self.state.completed_stages
    
    def run(self) -> StageOutput:
        """Cleanup and finalize."""
        from ..notify import notify_progress
        
        noctem_dir = Path(__file__).parent.parent.parent
        
        # Close any umbilical connection
        notify_progress(self.name, "Closing connections...")
        close_tunnel()
        
        # Remove temporary files
        notify_progress(self.name, "Cleaning up...")
        temp_files = [
            noctem_dir / ".birth_log",
            Path("/tmp/noctem.service"),
            Path("/tmp/signal-cli.tar.gz"),
        ]
        
        for f in temp_files:
            try:
                if f.exists():
                    f.unlink()
            except:
                pass
        
        # Set correct permissions on data directory
        data_dir = noctem_dir / "data"
        if data_dir.exists():
            self.run_command(["chmod", "-R", "700", str(data_dir)])
        
        # Create a birth completion marker
        marker_file = noctem_dir / ".birth_complete"
        marker_file.write_text(self.state.started_at)
        
        return StageOutput(
            result=StageResult.SUCCESS,
            message="Cleanup complete"
        )
    
    def verify(self) -> bool:
        """Verify cleanup."""
        noctem_dir = Path(__file__).parent.parent.parent
        return (noctem_dir / ".birth_complete").exists()
