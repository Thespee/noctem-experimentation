#!/usr/bin/env python3
"""
Noctem File Operations Skills
Read and write files safely.
"""

import os
from pathlib import Path
from typing import Dict, Any
from .base import Skill, SkillResult, SkillContext, register_skill


# Paths that should never be written to
PROTECTED_PATHS = [
    "/etc",
    "/bin",
    "/sbin",
    "/usr",
    "/boot",
    "/dev",
    "/proc",
    "/sys",
]


def is_path_safe(path: str, for_write: bool = False) -> tuple[bool, str]:
    """Check if a path is safe to access."""
    try:
        resolved = Path(path).resolve()
        path_str = str(resolved)
        
        # Check protected paths for writes
        if for_write:
            for protected in PROTECTED_PATHS:
                if path_str.startswith(protected):
                    return False, f"Cannot write to protected path: {protected}"
        
        return True, ""
    except Exception as e:
        return False, f"Invalid path: {str(e)}"


@register_skill
class FileReadSkill(Skill):
    """Read contents of a file."""
    
    name = "file_read"
    description = "Read the contents of a file. Returns the file text content."
    parameters = {
        "path": "string - path to the file to read",
        "max_lines": "int (optional, default 1000) - maximum lines to return",
        "encoding": "string (optional, default utf-8) - file encoding"
    }
    
    def run(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        path = params.get("path", "")
        max_lines = params.get("max_lines", 1000)
        encoding = params.get("encoding", "utf-8")
        
        if not path:
            return SkillResult(
                success=False,
                output="",
                error="No path provided"
            )
        
        # Expand user path
        path = os.path.expanduser(path)
        
        safe, error = is_path_safe(path, for_write=False)
        if not safe:
            return SkillResult(success=False, output="", error=error)
        
        try:
            file_path = Path(path)
            
            if not file_path.exists():
                return SkillResult(
                    success=False,
                    output="",
                    error=f"File not found: {path}"
                )
            
            if not file_path.is_file():
                return SkillResult(
                    success=False,
                    output="",
                    error=f"Not a file: {path}"
                )
            
            # Check file size (skip very large files)
            size = file_path.stat().st_size
            if size > 1_000_000:  # 1MB
                return SkillResult(
                    success=False,
                    output="",
                    error=f"File too large ({size} bytes). Max 1MB."
                )
            
            # Read file
            content = file_path.read_text(encoding=encoding)
            lines = content.split('\n')
            
            if len(lines) > max_lines:
                content = '\n'.join(lines[:max_lines])
                content += f"\n... (truncated, {len(lines) - max_lines} more lines)"
            
            return SkillResult(
                success=True,
                output=content,
                data={
                    "path": str(file_path.resolve()),
                    "size": size,
                    "lines": min(len(lines), max_lines)
                }
            )
            
        except UnicodeDecodeError:
            return SkillResult(
                success=False,
                output="",
                error=f"Cannot decode file with {encoding} encoding. Try a different encoding."
            )
        except Exception as e:
            return SkillResult(
                success=False,
                output="",
                error=f"Failed to read file: {str(e)}"
            )


@register_skill
class FileWriteSkill(Skill):
    """Write content to a file."""
    
    name = "file_write"
    description = "Write content to a file. Creates the file if it doesn't exist, overwrites if it does."
    parameters = {
        "path": "string - path to the file to write",
        "content": "string - content to write to the file",
        "append": "bool (optional, default false) - append instead of overwrite",
        "encoding": "string (optional, default utf-8) - file encoding"
    }
    
    def run(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        path = params.get("path", "")
        content = params.get("content", "")
        append = params.get("append", False)
        encoding = params.get("encoding", "utf-8")
        
        if not path:
            return SkillResult(
                success=False,
                output="",
                error="No path provided"
            )
        
        # Expand user path
        path = os.path.expanduser(path)
        
        safe, error = is_path_safe(path, for_write=True)
        if not safe:
            return SkillResult(success=False, output="", error=error)
        
        try:
            file_path = Path(path)
            
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write or append
            mode = 'a' if append else 'w'
            with open(file_path, mode, encoding=encoding) as f:
                f.write(content)
            
            size = file_path.stat().st_size
            
            return SkillResult(
                success=True,
                output=f"{'Appended to' if append else 'Wrote'} {path} ({len(content)} chars)",
                data={
                    "path": str(file_path.resolve()),
                    "size": size,
                    "mode": "append" if append else "write"
                }
            )
            
        except PermissionError:
            return SkillResult(
                success=False,
                output="",
                error=f"Permission denied: {path}"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                output="",
                error=f"Failed to write file: {str(e)}"
            )


if __name__ == "__main__":
    # Test
    ctx = SkillContext()
    
    # Test read
    read_skill = FileReadSkill()
    result = read_skill.execute({"path": "/etc/hostname"}, ctx)
    print(f"Read test: {result}")
    
    # Test write (to temp)
    write_skill = FileWriteSkill()
    result = write_skill.execute({
        "path": "/tmp/noctem_test.txt",
        "content": "Hello from Noctem!"
    }, ctx)
    print(f"Write test: {result}")
    
    # Verify write
    result = read_skill.execute({"path": "/tmp/noctem_test.txt"}, ctx)
    print(f"Verify: {result.output}")
