"""
Ollama client for Noctem v0.6.0 slow mode.

Provides LLM generation with graceful degradation when Ollama is unavailable.
"""
import httpx
import logging
from typing import Optional
from datetime import datetime, timedelta

from ..config import Config

logger = logging.getLogger(__name__)

# Cache for health check to avoid hammering the API
_health_cache = {
    "healthy": None,
    "checked_at": None,
    "cache_duration": timedelta(seconds=30),
}


class OllamaClient:
    """Client for interacting with Ollama API."""
    
    def __init__(self, host: str = None, model: str = None, timeout: float = 60.0):
        self.host = host or Config.get("ollama_host", "http://localhost:11434")
        self.model = model or Config.get("slow_model", "qwen2.5:7b-instruct-q4_K_M")
        self.timeout = timeout
    
    def check_health(self, use_cache: bool = True) -> bool:
        """
        Check if Ollama is available and responsive.
        
        Args:
            use_cache: If True, return cached result if recent (default 30s)
            
        Returns:
            True if Ollama is healthy, False otherwise
        """
        # Check cache
        if use_cache and _health_cache["checked_at"]:
            age = datetime.now() - _health_cache["checked_at"]
            if age < _health_cache["cache_duration"]:
                return _health_cache["healthy"]
        
        # Ping Ollama
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.host}/api/tags")
                healthy = response.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama health check failed: {e}")
            healthy = False
        
        # Update cache
        _health_cache["healthy"] = healthy
        _health_cache["checked_at"] = datetime.now()
        
        return healthy
    
    def health_check(self) -> tuple:
        """
        Check health and return (healthy, message) tuple.
        
        Returns:
            Tuple of (is_healthy: bool, status_message: str)
        """
        healthy = self.check_health()
        if healthy:
            if self.is_model_available():
                return (True, f"Connected, model {self.model} ready")
            else:
                return (True, f"Connected, but model {self.model} not found")
        else:
            return (False, "Not connected (is Ollama running?)")
    
    def is_model_available(self) -> bool:
        """Check if the configured model is available."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.host}/api/tags")
                if response.status_code != 200:
                    return False
                
                data = response.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                
                # Check for exact match or partial match (with/without tag)
                model_base = self.model.split(":")[0]
                for m in models:
                    if m == self.model or m.startswith(model_base):
                        return True
                return False
        except Exception as e:
            logger.debug(f"Model availability check failed: {e}")
            return False
    
    def generate(self, prompt: str, system: str = None, temperature: float = 0.7) -> Optional[str]:
        """
        Generate text using Ollama.
        
        Args:
            prompt: The user prompt
            system: Optional system prompt
            temperature: Sampling temperature (0.0-1.0)
            
        Returns:
            Generated text, or None if generation failed
        """
        if not self.check_health():
            logger.warning("Ollama unavailable, skipping generation")
            return None
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        
        if system:
            payload["system"] = system
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.host}/api/generate",
                    json=payload,
                )
                
                if response.status_code != 200:
                    logger.error(f"Ollama generation failed: {response.status_code}")
                    return None
                
                data = response.json()
                return data.get("response", "").strip()
                
        except httpx.TimeoutException:
            logger.warning(f"Ollama generation timed out after {self.timeout}s")
            return None
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            return None
    
    def generate_with_retry(self, prompt: str, system: str = None, 
                           retries: int = 2, temperature: float = 0.7) -> Optional[str]:
        """Generate with automatic retry on failure."""
        for attempt in range(retries + 1):
            result = self.generate(prompt, system, temperature)
            if result:
                return result
            
            if attempt < retries:
                logger.info(f"Retrying generation (attempt {attempt + 2}/{retries + 1})")
        
        return None


class GracefulDegradation:
    """
    Manages system status and graceful degradation.
    
    When LLM is unavailable:
    - Slow mode pauses
    - Work stays in queue
    - Fast mode continues normally
    - When LLM returns, process queue
    """
    
    FULL = "full"           # Everything working
    DEGRADED = "degraded"   # LLM unavailable, fast mode works
    OFFLINE = "offline"     # Major issues
    
    @staticmethod
    def get_system_status() -> str:
        """Get current system status."""
        client = OllamaClient()
        
        if client.check_health():
            if client.is_model_available():
                return GracefulDegradation.FULL
            else:
                return GracefulDegradation.DEGRADED
        else:
            return GracefulDegradation.DEGRADED
    
    @staticmethod
    def get_status_message() -> str:
        """Get human-readable status message."""
        status = GracefulDegradation.get_system_status()
        
        if status == GracefulDegradation.FULL:
            return "🟢 Full: All systems operational"
        elif status == GracefulDegradation.DEGRADED:
            return "🟡 Degraded: Fast mode active, slow mode paused (Ollama unavailable)"
        else:
            return "🔴 Offline: System experiencing issues"
    
    @staticmethod
    def can_run_slow_mode() -> bool:
        """Check if slow mode can run."""
        if not Config.get("slow_mode_enabled", True):
            return False
        
        return GracefulDegradation.get_system_status() == GracefulDegradation.FULL


# Convenience functions
def llm_available() -> bool:
    """Quick check if LLM is available."""
    return OllamaClient().check_health()


def llm_generate(prompt: str, system: str = None) -> Optional[str]:
    """Generate text using the default client."""
    return OllamaClient().generate(prompt, system)
