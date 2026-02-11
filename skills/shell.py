#!/usr/bin/env python3
"""
Noctem Shell Skill
Execute shell commands with safety restrictions.
"""

import subprocess
import shlex
from typing import Dict, Any
from .base import Skill, SkillResult, SkillContext, register_skill


# Default dangerous command patterns
DEFAULT_BLACKLIST = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "mkfs",
    "dd if=",
    "> /dev/",
    ":(){ :|:& };:",  # Fork bomb
    "chmod -R 777 /",
    "chown -R",
    "> /etc/",
    "curl | sh",
    "wget | sh",
    "curl | bash",
    "wget | bash",
]


@register_skill
class ShellSkill(Skill):
    """Execute shell commands safely."""
    
    name = "shell"
    description = "Execute a shell command and return the output. Use for system tasks, file operations, running scripts, etc."
    parameters = {
        "command": "string - the shell command to execute",
        "timeout": "int (optional, default 30) - timeout in seconds",
        "allow_stderr": "bool (optional, default true) - include stderr in output"
    }
    
    def __init__(self):
        super().__init__()
        self.blacklist = DEFAULT_BLACKLIST.copy()
    
    def is_dangerous(self, command: str) -> bool:
        """Check if command matches any blacklist pattern."""
        cmd_lower = command.lower().strip()
        for pattern in self.blacklist:
            if pattern.lower() in cmd_lower:
                return True
        return False
    
    def run(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        command = params.get("command", "")
        timeout = params.get("timeout", 30)
        allow_stderr = params.get("allow_stderr", True)
        
        if not command:
            return SkillResult(
                success=False,
                output="",
                error="No command provided"
            )
        
        # Check for dangerous commands
        if self.is_dangerous(command):
            return SkillResult(
                success=False,
                output="",
                error=f"Command blocked by safety filter: {command}"
            )
        
        # Load blacklist from config if available
        if context.config.get("dangerous_commands"):
            self.blacklist = DEFAULT_BLACKLIST + context.config["dangerous_commands"]
            if self.is_dangerous(command):
                return SkillResult(
                    success=False,
                    output="",
                    error=f"Command blocked by safety filter: {command}"
                )
        
        try:
            # Execute the command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=None  # Use current directory
            )
            
            # Combine stdout and stderr if allowed
            output = result.stdout
            if allow_stderr and result.stderr:
                if output:
                    output += "\n--- stderr ---\n"
                output += result.stderr
            
            # Truncate very long output
            if len(output) > 10000:
                output = output[:10000] + "\n... (output truncated)"
            
            return SkillResult(
                success=(result.returncode == 0),
                output=output.strip(),
                data={
                    "return_code": result.returncode,
                    "command": command
                },
                error=None if result.returncode == 0 else f"Command exited with code {result.returncode}"
            )
            
        except subprocess.TimeoutExpired:
            return SkillResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout} seconds"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                output="",
                error=f"Failed to execute command: {str(e)}"
            )


if __name__ == "__main__":
    # Test the skill
    skill = ShellSkill()
    ctx = SkillContext()
    
    # Safe command
    result = skill.execute({"command": "echo 'Hello, Noctem!'"}, ctx)
    print(f"Echo test: {result}")
    
    # List files
    result = skill.execute({"command": "ls -la"}, ctx)
    print(f"ls test: success={result.success}, lines={len(result.output.split(chr(10)))}")
    
    # Dangerous command (should be blocked)
    result = skill.execute({"command": "rm -rf /"}, ctx)
    print(f"Dangerous test: blocked={not result.success}, error={result.error}")
