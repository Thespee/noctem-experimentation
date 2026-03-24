"""
Noctem v0.6.1 Logging Module.

Provides execution tracing for the full thought pipeline.
"""
from .execution_logger import ExecutionLogger, get_trace, get_recent_traces

__all__ = ["ExecutionLogger", "get_trace", "get_recent_traces"]
