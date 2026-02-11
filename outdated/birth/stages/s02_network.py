#!/usr/bin/env python3
"""
Stage 2: Verify network connectivity.
"""

import socket
import urllib.request
import urllib.error

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage


class NetworkStage(Stage):
    """Verify network connectivity."""
    
    name = "network"
    description = "Checking network connectivity"
    birth_stage = BirthStage.NETWORK
    
    # Endpoints to test
    TEST_ENDPOINTS = [
        ("DNS", "8.8.8.8", 53),  # Google DNS
        ("HTTP", "http://connectivitycheck.gstatic.com/generate_204", None),
        ("Ollama", "https://ollama.ai", None),
        ("GitHub", "https://github.com", None),
    ]
    
    def check(self) -> bool:
        """Always check network."""
        return self.birth_stage.name not in self.state.completed_stages
    
    def run(self) -> StageOutput:
        """Check network connectivity."""
        results = {}
        failures = []
        
        for name, endpoint, port in self.TEST_ENDPOINTS:
            if port:
                # TCP connection test
                success = self._test_tcp(endpoint, port)
            else:
                # HTTP test
                success = self._test_http(endpoint)
            
            results[name] = success
            if not success:
                failures.append(name)
        
        self.state.config["network"] = results
        
        if failures:
            # If only some fail, it might be fine
            if "DNS" in failures:
                return StageOutput(
                    result=StageResult.FAILED,
                    message="Network check failed",
                    error=f"No network connectivity (DNS unreachable)",
                    data=results
                )
            elif len(failures) == len(self.TEST_ENDPOINTS):
                return StageOutput(
                    result=StageResult.FAILED,
                    message="Network check failed",
                    error="No network connectivity",
                    data=results
                )
            else:
                # Partial connectivity - warn but continue
                self.logger.warning(f"Some endpoints unreachable: {failures}")
        
        return StageOutput(
            result=StageResult.SUCCESS,
            message="Network connectivity OK",
            data=results
        )
    
    def _test_tcp(self, host: str, port: int, timeout: int = 5) -> bool:
        """Test TCP connection."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.close()
            return True
        except:
            return False
    
    def _test_http(self, url: str, timeout: int = 10) -> bool:
        """Test HTTP connection."""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Noctem-Birth/1.0"}
            )
            urllib.request.urlopen(req, timeout=timeout)
            return True
        except:
            return False
    
    def verify(self) -> bool:
        """Verify network is working."""
        return self._test_tcp("8.8.8.8", 53)
