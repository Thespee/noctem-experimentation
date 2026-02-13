#!/usr/bin/env python3
"""
Noctem Daemon
Background orchestrator that processes tasks using LLM planning.
"""

import json
import time
import threading
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

import state
from skill_runner import run_skill, run_skill_chain, list_skills, load_config

# Set up logging
LOG_PATH = Path(__file__).parent / "logs" / "noctem.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("noctem")


class Daemon:
    """Background task processor with LLM orchestration."""
    
    def __init__(self):
        self.config = load_config()
        self.running = False
        self.current_task = None
        self._thread = None
    
    def get_model(self) -> str:
        """Get the configured model name."""
        return self.config.get("model", "qwen2.5:7b-instruct-q4_K_M")
    
    def check_ollama(self) -> bool:
        """Check if Ollama is running."""
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            urllib.request.urlopen(req, timeout=5)
            return True
        except:
            return False
    
    def call_llm(self, prompt: str, model: Optional[str] = None) -> str:
        """Call Ollama HTTP API with a prompt and return the response."""
        model = model or self.get_model()
        
        try:
            data = json.dumps({
                "model": model,
                "prompt": prompt,
                "stream": False
            }).encode()
            
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode())
                return result.get("response", "").strip()
                
        except urllib.error.URLError as e:
            logger.error(f"Ollama not reachable: {e}")
            return ""
        except TimeoutError:
            logger.error("Ollama call timed out (180s)")
            return ""
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return ""
    
    def plan_task(self, task_input: str) -> Dict:
        """
        Ask LLM to create a plan for the task.
        Returns {"skills": [...]} or {"direct_response": "..."} 
        """
        skills = list_skills()
        
        # Build skill descriptions for prompt
        skill_list = "\n".join([
            f"- {name}: {info['description']}\n  params: {json.dumps(info['parameters'])}"
            for name, info in skills.items()
        ])
        
        prompt = f"""You are Noctem, a task orchestrator. Given a user request, decide how to fulfill it.

Available skills:
{skill_list}

User request: "{task_input}"

Respond with ONLY valid JSON (no markdown, no explanation):
- If you need to use skills: {{"skills": [{{"name": "skill_name", "params": {{...}}}}]}}
- If you can answer directly without tools: {{"direct_response": "your answer"}}

Example for "what time is it": {{"skills": [{{"name": "shell", "params": {{"command": "date"}}}}]}}
Example for "hello": {{"direct_response": "Hello! I'm Noctem, your AI assistant. How can I help?"}}

JSON response:"""
        
        response = self.call_llm(prompt)
        
        if not response:
            return {"direct_response": "Sorry, I couldn't process that request."}
        
        # Parse JSON from response
        try:
            # Try to extract JSON from response (in case there's extra text)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                logger.warning(f"No JSON found in LLM response: {response[:100]}")
                return {"direct_response": response}
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return {"direct_response": response}
    
    def execute_task(self, task: Dict) -> str:
        """Execute a task and return the result."""
        task_id = task["id"]
        task_input = task["input"]
        
        logger.info(f"Executing task {task_id}: {task_input[:50]}...")
        
        # Mark task as running
        state.start_task(task_id)
        self.current_task = task
        
        # Store user message in memory
        state.add_memory("user", task_input, task_id)
        
        try:
            # Get plan from LLM
            plan = self.plan_task(task_input)
            
            # Store plan
            state.update_task(task_id, plan=json.dumps(plan))
            
            # Execute plan
            if "direct_response" in plan:
                result = plan["direct_response"]
            elif "skills" in plan and plan["skills"]:
                skill_result = run_skill_chain(plan["skills"], task_id)
                if skill_result.success:
                    result = skill_result.output
                else:
                    result = f"Error: {skill_result.error}"
            else:
                result = "I'm not sure how to help with that."
            
            # Store assistant response in memory
            state.add_memory("assistant", result, task_id)
            
            # Mark complete
            state.complete_task(task_id, result, success=True)
            logger.info(f"Task {task_id} completed: {result[:50]}...")
            
            return result
            
        except Exception as e:
            error_msg = f"Task failed: {str(e)}"
            logger.error(f"Task {task_id} failed: {e}")
            state.complete_task(task_id, error_msg, success=False)
            return error_msg
        finally:
            self.current_task = None
    
    def process_queue(self):
        """Process tasks from the queue."""
        while self.running:
            task = state.get_next_task()
            
            if task:
                self.execute_task(task)
            else:
                # No tasks, sleep briefly
                time.sleep(1)
    
    def start(self):
        """Start the daemon in a background thread."""
        if self.running:
            return
        
        self.running = True
        self._thread = threading.Thread(target=self.process_queue, daemon=True)
        self._thread.start()
        logger.info("Daemon started")
    
    def stop(self):
        """Stop the daemon."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Daemon stopped")
    
    def get_status(self) -> Dict:
        """Get current daemon status."""
        return {
            "running": self.running,
            "current_task": self.current_task,
            "pending_count": len(state.get_pending_tasks()),
            "running_tasks": state.get_running_tasks()
        }


# Global daemon instance
_daemon: Optional[Daemon] = None


def get_daemon() -> Daemon:
    """Get or create the global daemon instance."""
    global _daemon
    if _daemon is None:
        _daemon = Daemon()
    return _daemon


def quick_chat(message: str) -> str:
    """
    Handle a quick chat message without queuing.
    Uses the router model for fast responses.
    """
    daemon = get_daemon()
    config = daemon.config
    router_model = config.get("router_model", "qwen2.5:1.5b-instruct-q4_K_M")
    
    prompt = f"""You are Noctem, a helpful AI assistant. Be concise and direct.
User: {message}
Assistant:"""
    
    response = daemon.call_llm(prompt, model=router_model)
    
    # Store in memory
    state.add_memory("user", message)
    state.add_memory("assistant", response)
    
    return response if response else "Sorry, I couldn't respond to that."


if __name__ == "__main__":
    # Test daemon
    daemon = get_daemon()
    
    print("Testing LLM call...")
    response = daemon.call_llm("Say hello in exactly 5 words.")
    print(f"Response: {response}")
    
    print("\nTesting task planning...")
    plan = daemon.plan_task("What time is it?")
    print(f"Plan: {plan}")
    
    print("\nTesting quick chat...")
    response = quick_chat("Hello!")
    print(f"Response: {response}")
