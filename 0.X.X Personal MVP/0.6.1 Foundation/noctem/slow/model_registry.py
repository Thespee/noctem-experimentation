"""
Model Registry for Noctem v0.6.1.

Tracks available local LLM models, their capabilities, and performance.
Provides model discovery, benchmarking, and routing.

Design: Ollama-first with abstract ModelBackend for future vLLM/llama.cpp support.
"""
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, Dict, Tuple

import httpx

from ..db import get_db
from ..config import Config
from ..models import ModelInfo

logger = logging.getLogger(__name__)


# =============================================================================
# ABSTRACT MODEL BACKEND
# =============================================================================

class ModelBackend(ABC):
    """
    Abstract base class for model backends.
    
    Implement this for different model servers (Ollama, vLLM, llama.cpp).
    """
    
    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Return the backend identifier ('ollama', 'vllm', 'llamacpp')."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend server is available."""
        pass
    
    @abstractmethod
    def list_models(self) -> List[str]:
        """List all available model names."""
        pass
    
    @abstractmethod
    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Get detailed info about a specific model."""
        pass
    
    @abstractmethod
    def benchmark_model(self, model_name: str, prompt: str = "Hello") -> Optional[float]:
        """
        Run a quick benchmark and return tokens per second.
        Returns None if benchmark failed.
        """
        pass


# =============================================================================
# OLLAMA BACKEND
# =============================================================================

class OllamaBackend(ModelBackend):
    """Ollama model backend implementation."""
    
    def __init__(self, host: str = None):
        self.host = host or Config.get("ollama_host", "http://localhost:11434")
        self._timeout = 30.0
    
    @property
    def backend_name(self) -> str:
        return "ollama"
    
    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
    
    def list_models(self) -> List[str]:
        """List all models available in Ollama."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(f"{self.host}/api/tags")
                if response.status_code != 200:
                    return []
                data = response.json()
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []
    
    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Get detailed info about an Ollama model."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self.host}/api/show",
                    json={"name": model_name}
                )
                if response.status_code != 200:
                    return None
                
                data = response.json()
                
                # Parse model info
                info = ModelInfo(
                    name=model_name,
                    backend="ollama",
                )
                
                # Extract family and parameters from model name
                info.family, info.parameter_size, info.quantization = \
                    self._parse_model_name(model_name)
                
                # Get details from response
                details = data.get("details", {})
                info.family = info.family or details.get("family")
                info.parameter_size = info.parameter_size or details.get("parameter_size")
                info.quantization = info.quantization or details.get("quantization_level")
                
                # Model info section
                model_info = data.get("model_info", {})
                
                # Context length from various possible fields
                for key in model_info:
                    if "context" in key.lower():
                        try:
                            info.context_length = int(model_info[key])
                            break
                        except (ValueError, TypeError):
                            pass
                
                # Check capabilities
                template = data.get("template", "")
                info.supports_function_calling = "tool" in template.lower() or \
                                                 "function" in template.lower()
                info.supports_json_schema = "json" in template.lower()
                
                return info
                
        except Exception as e:
            logger.error(f"Failed to get Ollama model info for {model_name}: {e}")
            return None
    
    def benchmark_model(self, model_name: str, prompt: str = "Hello, how are you?") -> Optional[float]:
        """
        Run a quick benchmark to measure tokens/second.
        
        Uses a simple prompt and measures the generation time.
        """
        try:
            with httpx.Client(timeout=60.0) as client:
                start_time = time.perf_counter()
                
                response = client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": model_name,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_predict": 50,  # Generate ~50 tokens
                        }
                    }
                )
                
                elapsed = time.perf_counter() - start_time
                
                if response.status_code != 200:
                    return None
                
                data = response.json()
                
                # Try to get actual eval count
                eval_count = data.get("eval_count", 50)
                eval_duration_ns = data.get("eval_duration", 0)
                
                if eval_duration_ns > 0:
                    # Use Ollama's own timing
                    tokens_per_sec = eval_count / (eval_duration_ns / 1e9)
                else:
                    # Estimate from total time
                    tokens_per_sec = eval_count / elapsed
                
                return round(tokens_per_sec, 2)
                
        except Exception as e:
            logger.error(f"Failed to benchmark {model_name}: {e}")
            return None
    
    def _parse_model_name(self, name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse model family, parameter size, and quantization from name.
        
        Examples:
            qwen2.5:7b-instruct-q4_K_M -> (qwen2.5, 7b, q4_K_M)
            llama3:8b -> (llama3, 8b, None)
            mistral:latest -> (mistral, None, None)
        """
        family = None
        param_size = None
        quantization = None
        
        # Split on colon
        parts = name.split(":")
        family = parts[0] if parts else None
        
        if len(parts) > 1:
            tag = parts[1]
            
            # Look for parameter size (number followed by 'b')
            size_match = re.search(r'(\d+\.?\d*)b', tag.lower())
            if size_match:
                param_size = size_match.group(1) + "b"
            
            # Look for quantization (q4_K_M, q8_0, etc.)
            quant_match = re.search(r'(q\d+[_\w]*)', tag.lower())
            if quant_match:
                quantization = quant_match.group(1)
        
        return family, param_size, quantization


# =============================================================================
# MODEL REGISTRY
# =============================================================================

class ModelRegistry:
    """
    Central registry for managing local LLM models.
    
    Provides:
    - Model discovery from backends
    - Capability tracking
    - Performance benchmarking
    - Model routing by task type
    """
    
    def __init__(self):
        self.backends: Dict[str, ModelBackend] = {}
        
        # Register default backends
        self.register_backend(OllamaBackend())
    
    def register_backend(self, backend: ModelBackend):
        """Register a model backend."""
        self.backends[backend.backend_name] = backend
        logger.debug(f"Registered model backend: {backend.backend_name}")
    
    def discover_models(self, backend_name: str = None) -> List[ModelInfo]:
        """
        Discover all available models from backends.
        
        Args:
            backend_name: Specific backend to query, or None for all
            
        Returns:
            List of ModelInfo objects
        """
        models = []
        
        backends_to_check = [self.backends[backend_name]] if backend_name else self.backends.values()
        
        for backend in backends_to_check:
            if not backend.is_available():
                logger.info(f"Backend {backend.backend_name} not available")
                continue
            
            model_names = backend.list_models()
            logger.info(f"Found {len(model_names)} models in {backend.backend_name}")
            
            for name in model_names:
                info = backend.get_model_info(name)
                if info:
                    models.append(info)
        
        return models
    
    def benchmark_and_save(self, model_name: str, backend_name: str = "ollama") -> Optional[ModelInfo]:
        """
        Benchmark a model and save results to database.
        
        Returns:
            Updated ModelInfo or None if failed
        """
        backend = self.backends.get(backend_name)
        if not backend or not backend.is_available():
            return None
        
        # Get model info
        info = backend.get_model_info(model_name)
        if not info:
            return None
        
        # Run benchmark
        logger.info(f"Benchmarking {model_name}...")
        tokens_per_sec = backend.benchmark_model(model_name)
        
        if tokens_per_sec:
            info.tokens_per_sec = tokens_per_sec
            info.health = "ok" if tokens_per_sec > 10 else "slow"
        else:
            info.health = "error"
        
        info.last_benchmarked = datetime.now()
        
        # Save to database
        self._save_model(info)
        
        return info
    
    def get_model(self, model_name: str) -> Optional[ModelInfo]:
        """Get a model from the registry database."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM model_registry WHERE name = ?",
                (model_name,)
            ).fetchone()
            return ModelInfo.from_row(row) if row else None
    
    def get_all_models(self) -> List[ModelInfo]:
        """Get all models from the registry database."""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM model_registry ORDER BY tokens_per_sec DESC NULLS LAST"
            ).fetchall()
            return [ModelInfo.from_row(row) for row in rows]
    
    def get_best_model_for(self, task_type: str) -> Optional[ModelInfo]:
        """
        Get the best available model for a task type.
        
        Task types:
        - 'fast': Quick classification/extraction (prefer speed)
        - 'planning': Project planning (balance speed/quality)
        - 'reasoning': Complex reasoning (prefer quality)
        
        Returns:
            Best matching ModelInfo or None
        """
        models = self.get_all_models()
        if not models:
            return None
        
        # Filter to healthy models
        healthy = [m for m in models if m.health == "ok"]
        if not healthy:
            healthy = models  # Fall back to all models
        
        if task_type == "fast":
            # Prefer fastest model
            return max(healthy, key=lambda m: m.tokens_per_sec or 0, default=None)
        
        elif task_type == "planning":
            # Balance: prefer models with function calling, reasonable speed
            scored = []
            for m in healthy:
                score = (m.tokens_per_sec or 0) * 0.5
                if m.supports_function_calling:
                    score += 20
                if m.supports_json_schema:
                    score += 10
                scored.append((m, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[0][0] if scored else None
        
        elif task_type == "reasoning":
            # Prefer larger models (by parameter size)
            def param_score(m):
                if not m.parameter_size:
                    return 0
                try:
                    return float(m.parameter_size.replace("b", ""))
                except ValueError:
                    return 0
            return max(healthy, key=param_score, default=None)
        
        # Default: return configured slow_model or first available
        configured = Config.get("slow_model")
        for m in healthy:
            if m.name == configured or m.name.startswith(configured.split(":")[0]):
                return m
        
        return healthy[0] if healthy else None
    
    def record_usage(self, model_name: str, task_type: str):
        """Record that a model was used for a specific task type."""
        with get_db() as conn:
            conn.execute("""
                UPDATE model_registry 
                SET last_used_for = ?
                WHERE name = ?
            """, (task_type, model_name))
    
    def _save_model(self, info: ModelInfo):
        """Save or update a model in the database."""
        with get_db() as conn:
            conn.execute("""
                INSERT INTO model_registry 
                (name, backend, family, parameter_size, quantization, context_length,
                 supports_function_calling, supports_json_schema, tokens_per_sec,
                 memory_gb, quality_score, health, last_benchmarked, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    backend = excluded.backend,
                    family = excluded.family,
                    parameter_size = excluded.parameter_size,
                    quantization = excluded.quantization,
                    context_length = excluded.context_length,
                    supports_function_calling = excluded.supports_function_calling,
                    supports_json_schema = excluded.supports_json_schema,
                    tokens_per_sec = excluded.tokens_per_sec,
                    memory_gb = excluded.memory_gb,
                    quality_score = excluded.quality_score,
                    health = excluded.health,
                    last_benchmarked = excluded.last_benchmarked,
                    notes = excluded.notes
            """, (
                info.name,
                info.backend,
                info.family,
                info.parameter_size,
                info.quantization,
                info.context_length,
                info.supports_function_calling,
                info.supports_json_schema,
                info.tokens_per_sec,
                info.memory_gb,
                info.quality_score,
                info.health,
                info.last_benchmarked,
                info.notes,
            ))


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_registry_instance: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    """Get the global model registry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModelRegistry()
    return _registry_instance


def discover_and_benchmark_all() -> List[ModelInfo]:
    """
    Discover all models and benchmark them.
    
    Returns:
        List of ModelInfo with benchmark results
    """
    registry = get_registry()
    
    # Discover models
    models = registry.discover_models()
    
    # Benchmark each
    results = []
    for model in models:
        info = registry.benchmark_and_save(model.name, model.backend)
        if info:
            results.append(info)
    
    return results


def get_current_model_status() -> dict:
    """Get status summary of the model registry."""
    registry = get_registry()
    models = registry.get_all_models()
    
    configured = Config.get("slow_model")
    configured_info = registry.get_model(configured)
    
    return {
        "total_models": len(models),
        "healthy_models": len([m for m in models if m.health == "ok"]),
        "configured_model": configured,
        "configured_status": configured_info.health if configured_info else "not_found",
        "fastest_model": max(models, key=lambda m: m.tokens_per_sec or 0).name if models else None,
    }
