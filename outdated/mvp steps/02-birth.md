# Phase 2: Birth Function Implementation Guide

**Objective**: Implement autonomous first-time setup with Signal-based error recovery and secure remote assistance.

**Prerequisites**: 
- Phase 1 complete (web skills working)
- signal-cli configured and working
- Understanding of systemd service management
- SSH basics

---

## Overview

The "birth" process is Noctem's autonomous first-time setup. It:
1. Attempts to configure itself without human intervention
2. Reports progress via Signal
3. Requests help when stuck (via `/umb` umbilical commands)
4. Sets up auto-start on system boot
5. Cleans up all setup artifacts when complete

---

## Step 1: Create Birth State Machine

### 1.1 Create `birth/state.py`

```python
"""Birth process state machine."""
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

class BirthStage(Enum):
    INIT = auto()           # Starting up
    CHECK_DEPS = auto()     # Checking dependencies
    INSTALL_DEPS = auto()   # Installing missing dependencies
    CONFIG_SIGNAL = auto()  # Configuring signal-cli
    CONFIG_OLLAMA = auto()  # Setting up Ollama
    PULL_MODELS = auto()    # Downloading AI models
    INIT_DB = auto()        # Initializing database
    TEST_SKILLS = auto()    # Testing core skills
    SETUP_AUTOSTART = auto() # Installing systemd service
    CLEANUP = auto()        # Cleaning up birth artifacts
    COMPLETE = auto()       # Birth complete
    ERROR = auto()          # Error state, waiting for help
    UMBILICAL = auto()      # Umbilical connection active

@dataclass
class BirthState:
    stage: BirthStage = BirthStage.INIT
    started_at: datetime = field(default_factory=datetime.now)
    errors: List[str] = field(default_factory=list)
    current_task: str = ""
    progress_pct: int = 0
    umbilical_active: bool = False
    ssh_port: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            "stage": self.stage.name,
            "started_at": self.started_at.isoformat(),
            "errors": self.errors,
            "current_task": self.current_task,
            "progress_pct": self.progress_pct,
            "umbilical_active": self.umbilical_active,
            "uptime_seconds": (datetime.now() - self.started_at).total_seconds()
        }
    
    def add_error(self, error: str):
        self.errors.append(f"[{datetime.now().isoformat()}] {error}")
        self.stage = BirthStage.ERROR

# Global birth state (in-memory only, never persisted)
_birth_state: Optional[BirthState] = None

def get_birth_state() -> Optional[BirthState]:
    return _birth_state

def init_birth_state() -> BirthState:
    global _birth_state
    _birth_state = BirthState()
    return _birth_state

def clear_birth_state():
    global _birth_state
    _birth_state = None
```

---

## Step 2: Create Signal Notification Helper

### 2.1 Create `birth/notify.py`

```python
"""Signal notifications for birth process."""
import subprocess
from pathlib import Path
from typing import Optional

# Load from config
SIGNAL_CLI_PATH = "signal-cli"
SIGNAL_NUMBER = None  # Set during birth from config

def set_signal_number(number: str):
    global SIGNAL_NUMBER
    SIGNAL_NUMBER = number

def send_signal(message: str, recipient: Optional[str] = None) -> bool:
    """Send a Signal message."""
    if not SIGNAL_NUMBER:
        print(f"[SIGNAL NOT CONFIGURED] {message}")
        return False
    
    target = recipient or SIGNAL_NUMBER
    
    try:
        result = subprocess.run(
            [SIGNAL_CLI_PATH, "-u", SIGNAL_NUMBER, "send", "-m", message, target],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[SIGNAL ERROR] {e}")
        return False

def notify_progress(stage: str, message: str, emoji: str = "🔧"):
    """Send progress notification."""
    send_signal(f"{emoji} Birth [{stage}]: {message}")

def notify_error(error: str, request_help: bool = True):
    """Send error notification."""
    msg = f"🚨 Birth ERROR: {error}"
    if request_help:
        msg += "\n\nReply /umb connect to help, or /umb abort to cancel."
    send_signal(msg)

def notify_complete():
    """Send completion notification."""
    send_signal("🌙 Noctem birth complete! Auto-start enabled. Send a message to begin.")
```

---

## Step 3: Implement Dependency Checker

### 3.1 Create `birth/deps.py`

```python
"""Dependency checking and installation."""
import subprocess
import shutil
from typing import List, Tuple
from dataclasses import dataclass

@dataclass
class Dependency:
    name: str
    check_cmd: List[str]  # Command to check if installed
    install_cmd: List[str]  # Command to install (empty = manual)
    required: bool = True

# Core dependencies
DEPENDENCIES = [
    Dependency(
        name="python3",
        check_cmd=["python3", "--version"],
        install_cmd=[],  # Must be pre-installed
        required=True
    ),
    Dependency(
        name="pip",
        check_cmd=["pip3", "--version"],
        install_cmd=["sudo", "apt-get", "install", "-y", "python3-pip"],
        required=True
    ),
    Dependency(
        name="signal-cli",
        check_cmd=["signal-cli", "--version"],
        install_cmd=[],  # Complex install, handle separately
        required=True
    ),
    Dependency(
        name="ollama",
        check_cmd=["ollama", "--version"],
        install_cmd=["curl", "-fsSL", "https://ollama.ai/install.sh", "|", "sh"],
        required=True
    ),
    Dependency(
        name="jq",
        check_cmd=["jq", "--version"],
        install_cmd=["sudo", "apt-get", "install", "-y", "jq"],
        required=False
    ),
]

def check_dependency(dep: Dependency) -> Tuple[bool, str]:
    """Check if a dependency is installed. Returns (installed, version_or_error)."""
    try:
        result = subprocess.run(
            dep.check_cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            version = result.stdout.strip() or result.stderr.strip()
            return True, version
        return False, result.stderr.strip()
    except FileNotFoundError:
        return False, "Not found in PATH"
    except Exception as e:
        return False, str(e)

def check_all_dependencies() -> List[Tuple[Dependency, bool, str]]:
    """Check all dependencies. Returns list of (dep, installed, info)."""
    results = []
    for dep in DEPENDENCIES:
        installed, info = check_dependency(dep)
        results.append((dep, installed, info))
    return results

def install_dependency(dep: Dependency) -> Tuple[bool, str]:
    """Attempt to install a dependency. Returns (success, message)."""
    if not dep.install_cmd:
        return False, f"{dep.name} must be installed manually"
    
    try:
        # Handle piped commands specially
        cmd_str = " ".join(dep.install_cmd)
        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300  # 5 min timeout for installs
        )
        if result.returncode == 0:
            return True, f"{dep.name} installed successfully"
        return False, f"Install failed: {result.stderr}"
    except Exception as e:
        return False, f"Install error: {e}"

def check_python_packages() -> List[Tuple[str, bool]]:
    """Check required Python packages."""
    packages = ["requests", "beautifulsoup4", "ollama"]
    results = []
    
    for pkg in packages:
        try:
            __import__(pkg.replace("-", "_").split("[")[0])
            results.append((pkg, True))
        except ImportError:
            results.append((pkg, False))
    
    return results

def install_python_packages(packages: List[str]) -> Tuple[bool, str]:
    """Install Python packages via pip."""
    try:
        result = subprocess.run(
            ["pip3", "install", "--user"] + packages,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            return True, "Packages installed"
        return False, result.stderr
    except Exception as e:
        return False, str(e)
```

---

## Step 4: Implement Umbilical Protocol

### 4.1 Create `birth/umbilical.py`

```python
"""Umbilical cord - secure remote assistance during birth."""
import subprocess
import os
import tempfile
import secrets
from typing import Optional, Tuple
from dataclasses import dataclass
import threading
import time

@dataclass
class UmbilicalConnection:
    ssh_port: int
    connection_id: str
    started_at: float
    process: Optional[subprocess.Popen] = None

# Active connection (only one at a time)
_connection: Optional[UmbilicalConnection] = None
_timeout_thread: Optional[threading.Thread] = None

UMBILICAL_TIMEOUT = 1800  # 30 minutes

def generate_connection_id() -> str:
    """Generate a random connection ID."""
    return secrets.token_hex(8)

def find_free_port() -> int:
    """Find a free port for SSH."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def start_reverse_tunnel(relay_host: str, relay_port: int = 22) -> Tuple[bool, str]:
    """
    Start a reverse SSH tunnel to allow remote access.
    
    SECURITY: This creates an ephemeral tunnel. Keys are not persisted.
    For MVP, we use an existing SSH key; full version uses ephemeral keys.
    """
    global _connection, _timeout_thread
    
    if _connection is not None:
        return False, "Umbilical already active"
    
    local_port = 22  # Local SSH port
    remote_port = find_free_port()  # Port on relay
    connection_id = generate_connection_id()
    
    # Build reverse tunnel command
    # -R binds remote_port on relay to local_port here
    # -N = no command, -f = background (we don't use -f, we manage the process)
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-N",
        "-R", f"{remote_port}:localhost:{local_port}",
        f"{relay_host}"
    ]
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give it a moment to connect
        time.sleep(2)
        
        if process.poll() is not None:
            # Process already exited
            stderr = process.stderr.read().decode()
            return False, f"Tunnel failed: {stderr}"
        
        _connection = UmbilicalConnection(
            ssh_port=remote_port,
            connection_id=connection_id,
            started_at=time.time(),
            process=process
        )
        
        # Start timeout thread
        _timeout_thread = threading.Thread(target=_timeout_monitor, daemon=True)
        _timeout_thread.start()
        
        return True, f"Umbilical active. Connect via: ssh -p {remote_port} {relay_host}"
        
    except Exception as e:
        return False, f"Tunnel error: {e}"

def _timeout_monitor():
    """Monitor connection and close after timeout."""
    global _connection
    
    while _connection is not None:
        elapsed = time.time() - _connection.started_at
        if elapsed > UMBILICAL_TIMEOUT:
            close_umbilical()
            from .notify import send_signal
            send_signal("⏱️ Umbilical timed out after 30 minutes. Reply /umb connect to reconnect.")
            break
        time.sleep(60)  # Check every minute

def close_umbilical() -> Tuple[bool, str]:
    """Close the umbilical connection."""
    global _connection
    
    if _connection is None:
        return False, "No active umbilical"
    
    try:
        if _connection.process:
            _connection.process.terminate()
            _connection.process.wait(timeout=5)
    except:
        pass
    
    _connection = None
    return True, "Umbilical closed"

def get_umbilical_status() -> Optional[dict]:
    """Get current umbilical status."""
    if _connection is None:
        return None
    
    return {
        "connection_id": _connection.connection_id,
        "ssh_port": _connection.ssh_port,
        "uptime_seconds": time.time() - _connection.started_at,
        "timeout_remaining": UMBILICAL_TIMEOUT - (time.time() - _connection.started_at)
    }

def handle_umb_command(command: str) -> str:
    """
    Handle /umb commands.
    
    Commands:
      /umb connect [relay_host] - Start umbilical
      /umb status - Get status
      /umb close - Close umbilical
      /umb abort - Abort birth entirely
    """
    parts = command.strip().split(maxsplit=2)
    
    if len(parts) < 2:
        return "Usage: /umb <connect|status|close|abort> [args]"
    
    action = parts[1].lower()
    
    if action == "connect":
        relay = parts[2] if len(parts) > 2 else None
        if not relay:
            return "Usage: /umb connect <relay_host>\nExample: /umb connect user@myserver.com"
        
        success, message = start_reverse_tunnel(relay)
        return message
    
    elif action == "status":
        status = get_umbilical_status()
        if status:
            return (f"🔗 Umbilical active\n"
                   f"Port: {status['ssh_port']}\n"
                   f"Uptime: {int(status['uptime_seconds'])}s\n"
                   f"Timeout in: {int(status['timeout_remaining'])}s")
        return "No active umbilical"
    
    elif action == "close":
        success, message = close_umbilical()
        return message
    
    elif action == "abort":
        close_umbilical()
        # Signal to main birth process to abort
        from .state import get_birth_state, BirthStage
        state = get_birth_state()
        if state:
            state.stage = BirthStage.CLEANUP
        return "🛑 Birth aborted. Cleaning up..."
    
    else:
        return f"Unknown command: {action}\nValid: connect, status, close, abort"
```

---

## Step 5: Implement Auto-Start Setup

### 5.1 Create `birth/autostart.py`

```python
"""Auto-start configuration for Noctem."""
import subprocess
import os
from pathlib import Path
from typing import Tuple

SYSTEMD_SERVICE_TEMPLATE = """[Unit]
Description=Noctem Personal AI Assistant
After=network.target ollama.service

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={working_dir}
ExecStart={python_path} {main_script} --headless
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={working_dir}
PrivateTmp=true

[Install]
WantedBy=multi-user.target
"""

SERVICE_NAME = "noctem.service"
SERVICE_PATH = f"/etc/systemd/system/{SERVICE_NAME}"

def generate_service_file(working_dir: Path) -> str:
    """Generate systemd service file content."""
    import getpass
    import grp
    
    user = getpass.getuser()
    try:
        group = grp.getgrgid(os.getgid()).gr_name
    except:
        group = user
    
    python_path = subprocess.run(
        ["which", "python3"],
        capture_output=True,
        text=True
    ).stdout.strip()
    
    main_script = working_dir / "main.py"
    
    return SYSTEMD_SERVICE_TEMPLATE.format(
        user=user,
        group=group,
        working_dir=working_dir,
        python_path=python_path,
        main_script=main_script
    )

def install_systemd_service(working_dir: Path) -> Tuple[bool, str]:
    """Install and enable the systemd service."""
    service_content = generate_service_file(working_dir)
    
    # Write service file (requires sudo)
    try:
        # Write to temp file first
        temp_path = Path("/tmp/noctem.service")
        temp_path.write_text(service_content)
        
        # Move to systemd directory
        result = subprocess.run(
            ["sudo", "cp", str(temp_path), SERVICE_PATH],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return False, f"Failed to copy service file: {result.stderr}"
        
        # Set permissions
        subprocess.run(["sudo", "chmod", "644", SERVICE_PATH], check=True)
        
        # Reload systemd
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
        
        # Enable service
        subprocess.run(["sudo", "systemctl", "enable", SERVICE_NAME], check=True)
        
        # Clean up temp file
        temp_path.unlink()
        
        return True, f"Service installed and enabled: {SERVICE_NAME}"
        
    except subprocess.CalledProcessError as e:
        return False, f"systemctl error: {e}"
    except Exception as e:
        return False, f"Install error: {e}"

def start_service() -> Tuple[bool, str]:
    """Start the Noctem service."""
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "start", SERVICE_NAME],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True, "Service started"
        return False, result.stderr
    except Exception as e:
        return False, str(e)

def get_service_status() -> dict:
    """Get current service status."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True
        )
        is_active = result.stdout.strip() == "active"
        
        result = subprocess.run(
            ["systemctl", "is-enabled", SERVICE_NAME],
            capture_output=True,
            text=True
        )
        is_enabled = result.stdout.strip() == "enabled"
        
        return {
            "installed": Path(SERVICE_PATH).exists(),
            "active": is_active,
            "enabled": is_enabled
        }
    except:
        return {"installed": False, "active": False, "enabled": False}

def uninstall_service() -> Tuple[bool, str]:
    """Remove the systemd service."""
    try:
        subprocess.run(["sudo", "systemctl", "stop", SERVICE_NAME], capture_output=True)
        subprocess.run(["sudo", "systemctl", "disable", SERVICE_NAME], capture_output=True)
        subprocess.run(["sudo", "rm", "-f", SERVICE_PATH], capture_output=True)
        subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True)
        return True, "Service uninstalled"
    except Exception as e:
        return False, str(e)
```

---

## Step 6: Implement Main Birth Process

### 6.1 Create `birth/process.py`

```python
"""Main birth process orchestrator."""
import time
import sys
from pathlib import Path
from typing import Optional

from .state import (
    BirthState, BirthStage, init_birth_state, 
    get_birth_state, clear_birth_state
)
from .notify import (
    notify_progress, notify_error, notify_complete,
    set_signal_number
)
from .deps import (
    check_all_dependencies, check_python_packages,
    install_python_packages, install_dependency
)
from .autostart import install_systemd_service
from .umbilical import handle_umb_command, close_umbilical

class BirthProcess:
    def __init__(self, working_dir: Path, signal_number: str):
        self.working_dir = working_dir
        self.signal_number = signal_number
        self.state: Optional[BirthState] = None
        
    def run(self) -> bool:
        """Run the full birth process. Returns True on success."""
        set_signal_number(self.signal_number)
        self.state = init_birth_state()
        
        notify_progress("INIT", "Birth process starting...")
        
        stages = [
            (BirthStage.CHECK_DEPS, self._check_dependencies),
            (BirthStage.INSTALL_DEPS, self._install_dependencies),
            (BirthStage.CONFIG_OLLAMA, self._configure_ollama),
            (BirthStage.PULL_MODELS, self._pull_models),
            (BirthStage.INIT_DB, self._init_database),
            (BirthStage.TEST_SKILLS, self._test_skills),
            (BirthStage.SETUP_AUTOSTART, self._setup_autostart),
            (BirthStage.CLEANUP, self._cleanup),
        ]
        
        for stage, handler in stages:
            if self.state.stage == BirthStage.ERROR:
                # Wait for help via umbilical
                if not self._wait_for_recovery():
                    return False
            
            self.state.stage = stage
            self.state.progress_pct = int((stages.index((stage, handler)) / len(stages)) * 100)
            
            success = handler()
            if not success:
                return False
        
        self.state.stage = BirthStage.COMPLETE
        notify_complete()
        clear_birth_state()
        return True
    
    def _check_dependencies(self) -> bool:
        """Check all required dependencies."""
        notify_progress("CHECK", "Checking dependencies...", "🔍")
        
        results = check_all_dependencies()
        missing = [(dep, info) for dep, installed, info in results if not installed and dep.required]
        
        if missing:
            self.state.current_task = f"Missing: {', '.join(d.name for d, _ in missing)}"
            notify_progress("CHECK", f"Missing dependencies: {', '.join(d.name for d, _ in missing)}", "⚠️")
            return True  # Continue to install phase
        
        notify_progress("CHECK", "All dependencies found ✓", "✅")
        return True
    
    def _install_dependencies(self) -> bool:
        """Install missing dependencies."""
        # Check Python packages
        pkg_results = check_python_packages()
        missing_pkgs = [pkg for pkg, installed in pkg_results if not installed]
        
        if missing_pkgs:
            notify_progress("INSTALL", f"Installing Python packages: {', '.join(missing_pkgs)}", "📦")
            success, msg = install_python_packages(missing_pkgs)
            if not success:
                self.state.add_error(f"Failed to install packages: {msg}")
                notify_error(f"Package install failed: {msg}")
                return False
        
        # Check system dependencies
        results = check_all_dependencies()
        missing = [(dep, info) for dep, installed, info in results if not installed and dep.required]
        
        for dep, info in missing:
            if dep.install_cmd:
                notify_progress("INSTALL", f"Installing {dep.name}...", "📦")
                success, msg = install_dependency(dep)
                if not success:
                    self.state.add_error(f"Failed to install {dep.name}: {msg}")
                    notify_error(f"Cannot install {dep.name}: {msg}")
                    return False
            else:
                # Manual install required
                self.state.add_error(f"{dep.name} must be installed manually")
                notify_error(f"{dep.name} must be installed manually. {info}")
                return False
        
        notify_progress("INSTALL", "Dependencies installed ✓", "✅")
        return True
    
    def _configure_ollama(self) -> bool:
        """Ensure Ollama is running."""
        import subprocess
        
        notify_progress("OLLAMA", "Checking Ollama service...", "🤖")
        
        try:
            # Try to connect to Ollama
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=5)
            if resp.status_code == 200:
                notify_progress("OLLAMA", "Ollama running ✓", "✅")
                return True
        except:
            pass
        
        # Try to start Ollama
        notify_progress("OLLAMA", "Starting Ollama service...", "🔄")
        try:
            subprocess.run(["ollama", "serve"], start_new_session=True)
            time.sleep(3)  # Give it time to start
            
            # Verify
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=5)
            if resp.status_code == 200:
                notify_progress("OLLAMA", "Ollama started ✓", "✅")
                return True
        except Exception as e:
            self.state.add_error(f"Ollama start failed: {e}")
            notify_error(f"Cannot start Ollama: {e}")
            return False
        
        return False
    
    def _pull_models(self) -> bool:
        """Pull required AI models."""
        import subprocess
        
        models = ["qwen2.5:1.5b", "qwen2.5:7b"]  # Router and worker
        
        for model in models:
            notify_progress("MODELS", f"Pulling {model}...", "⬇️")
            
            try:
                result = subprocess.run(
                    ["ollama", "pull", model],
                    capture_output=True,
                    text=True,
                    timeout=1800  # 30 min timeout
                )
                if result.returncode != 0:
                    self.state.add_error(f"Failed to pull {model}: {result.stderr}")
                    notify_error(f"Model pull failed: {model}")
                    return False
            except subprocess.TimeoutExpired:
                self.state.add_error(f"Timeout pulling {model}")
                notify_error(f"Model pull timed out: {model}")
                return False
            except Exception as e:
                self.state.add_error(f"Model pull error: {e}")
                notify_error(f"Model pull error: {e}")
                return False
        
        notify_progress("MODELS", "Models ready ✓", "✅")
        return True
    
    def _init_database(self) -> bool:
        """Initialize the SQLite database."""
        notify_progress("DATABASE", "Initializing database...", "🗄️")
        
        try:
            db_path = self.working_dir / "noctem.db"
            
            # Import and run state initialization
            sys.path.insert(0, str(self.working_dir))
            from state import init_db
            init_db(str(db_path))
            
            notify_progress("DATABASE", "Database ready ✓", "✅")
            return True
        except Exception as e:
            self.state.add_error(f"Database init failed: {e}")
            notify_error(f"Database error: {e}")
            return False
    
    def _test_skills(self) -> bool:
        """Test that core skills work."""
        notify_progress("TEST", "Testing core skills...", "🧪")
        
        try:
            sys.path.insert(0, str(self.working_dir))
            
            # Test shell skill
            from skills.shell import run as shell_run
            result = shell_run("echo 'test'")
            if "error" in result:
                raise Exception(f"Shell skill failed: {result['error']}")
            
            # Test web_fetch skill
            from skills.web_fetch import run as fetch_run
            result = fetch_run("https://example.com")
            if "error" in result:
                raise Exception(f"Web fetch failed: {result['error']}")
            
            notify_progress("TEST", "Skills working ✓", "✅")
            return True
        except Exception as e:
            self.state.add_error(f"Skill test failed: {e}")
            notify_error(f"Skill test failed: {e}")
            return False
    
    def _setup_autostart(self) -> bool:
        """Install systemd service for auto-start."""
        notify_progress("AUTOSTART", "Setting up auto-start...", "⚙️")
        
        success, msg = install_systemd_service(self.working_dir)
        if not success:
            # Non-fatal - warn but continue
            notify_progress("AUTOSTART", f"Auto-start setup failed (non-fatal): {msg}", "⚠️")
            return True  # Continue anyway
        
        notify_progress("AUTOSTART", "Auto-start configured ✓", "✅")
        return True
    
    def _cleanup(self) -> bool:
        """Clean up birth artifacts."""
        notify_progress("CLEANUP", "Cleaning up...", "🧹")
        
        # Close any umbilical connection
        close_umbilical()
        
        # Remove any temporary files
        temp_files = [
            self.working_dir / ".birth_log",
            self.working_dir / ".birth_state",
        ]
        for f in temp_files:
            if f.exists():
                f.unlink()
        
        notify_progress("CLEANUP", "Cleanup complete ✓", "✅")
        return True
    
    def _wait_for_recovery(self) -> bool:
        """Wait for user help via umbilical. Returns True to retry, False to abort."""
        notify_progress("WAITING", "Waiting for assistance...", "⏳")
        
        # In practice, this would be integrated with the Signal receiver
        # For now, we just wait and check state periodically
        max_wait = 3600  # 1 hour max
        waited = 0
        
        while waited < max_wait:
            time.sleep(30)
            waited += 30
            
            # Check if state changed (via umbilical commands)
            if self.state.stage == BirthStage.CLEANUP:
                return False  # Abort
            if self.state.stage != BirthStage.ERROR:
                return True  # Retry
        
        # Timeout
        notify_error("Birth timed out waiting for assistance", request_help=False)
        return False


def run_birth(working_dir: str, signal_number: str) -> bool:
    """Entry point for birth process."""
    process = BirthProcess(Path(working_dir), signal_number)
    return process.run()
```

---

## Step 7: Create CLI Entry Point

### 7.1 Update `main.py` with Birth Mode

Add to `main.py`:

```python
import argparse

def main():
    parser = argparse.ArgumentParser(description="Noctem Personal AI Assistant")
    parser.add_argument("--birth", action="store_true", help="Run first-time setup")
    parser.add_argument("--headless", action="store_true", help="Run without interactive output")
    parser.add_argument("--signal-number", help="Your Signal phone number (for birth)")
    
    args = parser.parse_args()
    
    if args.birth:
        from birth.process import run_birth
        
        if not args.signal_number:
            print("Error: --signal-number required for birth")
            print("Usage: python main.py --birth --signal-number +1234567890")
            sys.exit(1)
        
        success = run_birth(
            working_dir=str(Path(__file__).parent),
            signal_number=args.signal_number
        )
        sys.exit(0 if success else 1)
    
    # Normal operation
    # ... existing code ...
```

### 7.2 Update `quickstart.sh`

Add birth option:

```bash
#!/bin/bash

if [ "$1" == "--birth" ]; then
    echo "🌙 Starting Noctem birth process..."
    read -p "Enter your Signal phone number (e.g., +1234567890): " SIGNAL_NUMBER
    python3 main.py --birth --signal-number "$SIGNAL_NUMBER"
    exit $?
fi

# ... existing quickstart code ...
```

---

## Step 8: Handle /umb Commands in Signal Receiver

### 8.1 Update `signal_receiver.py`

Add umbilical command handling:

```python
# In the message handler function:

def handle_message(message: str, sender: str) -> str:
    """Handle incoming Signal message."""
    
    # Check for umbilical commands during birth
    if message.strip().lower().startswith("/umb"):
        from birth.umbilical import handle_umb_command
        from birth.state import get_birth_state
        
        state = get_birth_state()
        if state is None:
            return "Birth process not active. /umb commands only work during birth."
        
        return handle_umb_command(message)
    
    # Normal message handling
    # ... existing code ...
```

---

## Step 9: Security Hardening

### 9.1 Create `birth/security.py`

```python
"""Security utilities for birth process."""
import os
import secrets
from pathlib import Path

def secure_delete(path: Path):
    """Securely delete a file by overwriting with random data."""
    if not path.exists():
        return
    
    size = path.stat().st_size
    
    # Overwrite with random data 3 times
    for _ in range(3):
        with open(path, 'wb') as f:
            f.write(secrets.token_bytes(size))
            f.flush()
            os.fsync(f.fileno())
    
    # Finally delete
    path.unlink()

def secure_clear_memory(data: bytearray):
    """Clear sensitive data from memory."""
    for i in range(len(data)):
        data[i] = 0

def generate_ephemeral_key() -> tuple[bytes, bytes]:
    """Generate an ephemeral Ed25519 keypair in memory."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    )
    
    return private_bytes, public_bytes
```

---

## Completion Checklist

- [ ] `birth/__init__.py` created
- [ ] `birth/state.py` created
- [ ] `birth/notify.py` created
- [ ] `birth/deps.py` created
- [ ] `birth/umbilical.py` created
- [ ] `birth/autostart.py` created
- [ ] `birth/process.py` created
- [ ] `birth/security.py` created
- [ ] `main.py` updated with --birth flag
- [ ] `quickstart.sh` updated with birth option
- [ ] `signal_receiver.py` handles /umb commands
- [ ] Tested full birth process on clean system
- [ ] Auto-start works after reboot
- [ ] Umbilical connection works
- [ ] All artifacts cleaned up after birth

---

## Testing

### Test Birth Process

```bash
# On a fresh system or VM:
cd /path/to/noctem
./quickstart.sh --birth

# Verify via Signal:
# - Progress messages received
# - /umb status works
# - /umb connect [relay] establishes tunnel
# - Completion message received
```

### Test Auto-Start

```bash
# After birth:
sudo systemctl status noctem
sudo reboot

# After reboot:
sudo systemctl status noctem  # Should be active
```

---

## Troubleshooting

### Birth hangs at "Pulling models"
- Models can be large (several GB)
- Check network connection
- Verify Ollama is running: `curl localhost:11434/api/tags`

### /umb connect fails
- Ensure SSH is installed and running locally
- Verify relay host is accessible
- Check firewall settings

### Auto-start fails
- May need sudo password
- Verify systemd is available (not all systems use it)
- Check service status: `journalctl -u noctem`
