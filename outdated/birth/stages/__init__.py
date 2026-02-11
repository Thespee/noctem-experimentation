#!/usr/bin/env python3
"""
Birth stages - modular installation steps.
"""

from .base import Stage, StageResult
from .s01_detect import DetectStage
from .s02_network import NetworkStage
from .s03_system_deps import SystemDepsStage
from .s04_python_deps import PythonDepsStage
from .s05_ollama import OllamaStage
from .s06_signal_cli import SignalCliStage
from .s07_noctem_init import NoctemInitStage
from .s08_test_skills import TestSkillsStage
from .s09_autostart import AutostartStage
from .s10_cleanup import CleanupStage

# Stage registry in execution order
STAGES = [
    DetectStage,
    NetworkStage,
    SystemDepsStage,
    PythonDepsStage,
    OllamaStage,
    SignalCliStage,
    NoctemInitStage,
    TestSkillsStage,
    AutostartStage,
    CleanupStage,
]

__all__ = [
    "Stage",
    "StageResult",
    "STAGES",
    "DetectStage",
    "NetworkStage",
    "SystemDepsStage",
    "PythonDepsStage",
    "OllamaStage",
    "SignalCliStage",
    "NoctemInitStage",
    "TestSkillsStage",
    "AutostartStage",
    "CleanupStage",
]
