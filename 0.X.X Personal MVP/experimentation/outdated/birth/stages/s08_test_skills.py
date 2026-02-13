#!/usr/bin/env python3
"""
Stage 8: Test core Noctem skills.
"""

import sys
from pathlib import Path

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage


class TestSkillsStage(Stage):
    """Test core Noctem skills."""
    
    name = "test_skills"
    description = "Testing Noctem skills"
    birth_stage = BirthStage.TEST_SKILLS
    
    def check(self) -> bool:
        """Check if skills have been tested."""
        return self.birth_stage.name not in self.state.completed_stages
    
    def run(self) -> StageOutput:
        """Run skill tests."""
        from ..notify import notify_progress
        
        noctem_dir = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(noctem_dir))
        
        results = {}
        failures = []
        
        # Test shell skill
        notify_progress(self.name, "Testing shell skill...")
        try:
            from skills.shell import ShellSkill
            from skills.base import SkillContext
            
            skill = ShellSkill()
            ctx = SkillContext()
            result = skill.execute({"command": "echo 'test'"}, ctx)
            
            if result.success:
                results["shell"] = "OK"
            else:
                results["shell"] = f"FAILED: {result.error}"
                failures.append("shell")
        except Exception as e:
            results["shell"] = f"ERROR: {e}"
            failures.append("shell")
        
        # Test file_ops skill
        notify_progress(self.name, "Testing file_ops skill...")
        try:
            from skills.file_ops import FileOpsSkill
            
            skill = FileOpsSkill()
            ctx = SkillContext()
            result = skill.execute({"action": "read", "path": "/etc/hostname"}, ctx)
            
            if result.success:
                results["file_ops"] = "OK"
            else:
                results["file_ops"] = f"FAILED: {result.error}"
                failures.append("file_ops")
        except Exception as e:
            results["file_ops"] = f"ERROR: {e}"
            failures.append("file_ops")
        
        # Test web_fetch skill (if requests available)
        notify_progress(self.name, "Testing web_fetch skill...")
        try:
            from skills.web_fetch import WebFetchSkill
            
            skill = WebFetchSkill()
            ctx = SkillContext()
            result = skill.execute({"url": "https://example.com"}, ctx)
            
            if result.success:
                results["web_fetch"] = "OK"
            else:
                results["web_fetch"] = f"FAILED: {result.error}"
                failures.append("web_fetch")
        except ImportError:
            results["web_fetch"] = "SKIPPED (requests not installed)"
        except Exception as e:
            results["web_fetch"] = f"ERROR: {e}"
            failures.append("web_fetch")
        
        # Test Ollama connectivity
        notify_progress(self.name, "Testing Ollama connection...")
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            urllib.request.urlopen(req, timeout=5)
            results["ollama"] = "OK"
        except Exception as e:
            results["ollama"] = f"ERROR: {e}"
            failures.append("ollama")
        
        # Store results
        self.state.config["skill_tests"] = results
        
        if failures:
            return StageOutput(
                result=StageResult.FAILED,
                message=f"{len(failures)} skill(s) failed",
                error=f"Failed: {', '.join(failures)}",
                data=results
            )
        
        return StageOutput(
            result=StageResult.SUCCESS,
            message=f"All {len(results)} skills OK",
            data=results
        )
    
    def verify(self) -> bool:
        """Verify skills work."""
        return "skill_tests" in self.state.config
