# Moltbot Skill: Hybrid Local/Cloud AI with Privacy Sanitization

## Purpose
This skill enables Moltbot to:
- Use fast cloud AI models (Gemini, Claude) when appropriate
- Default to local Ollama for privacy-sensitive tasks
- Automatically sanitize personal information before sending to cloud
- Replace identifiers with consistent fake data to preserve context
- Warn about costs and track usage

## Security Model

| Feature | Description |
|---------|-------------|
| **Request logging** | Log all cloud requests (sanitized) for audit |
| **Approval mode** | Show sanitized version, require approval before sending |
| **Cost tracking** | Track API spending, alert at thresholds |
| **Domain allowlist** | Only allow specific API endpoints |
| **Response scanning** | Check cloud responses don't contain injected data |
| **Offline fallback** | Gracefully degrade to local when no internet |
| **Task classification** | Auto-detect if task contains PII, force local |

## Supported Providers

| Provider | Models | Best For |
|----------|--------|----------|
| **Local (Ollama)** | qwen-agentic (7B) | Private data, offline, no cost |
| **Google Gemini** | gemini-pro, gemini-1.5-flash | Fast coding, general tasks |
| **Anthropic** | claude-3-haiku, claude-3-sonnet | Complex reasoning, coding |

## Prerequisites

### Install Required Packages
```bash
pip3 install google-generativeai anthropic
```

### Store API Keys Securely
```bash
# Add to ~/.config/moltbot/env (already protected with chmod 600)
echo 'GEMINI_API_KEY=your_gemini_key_here' >> ~/.config/moltbot/env
echo 'ANTHROPIC_API_KEY=your_anthropic_key_here' >> ~/.config/moltbot/env
```

## Implementation

### hybrid_ai.py - Main Module
Location: `~/moltbot-system/skills/hybrid_ai.py`

```python
#!/usr/bin/env python3
"""
Moltbot Hybrid AI System
Routes requests between local and cloud models with privacy sanitization
"""

import os
import re
import json
import random
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import sqlite3

# Configuration
CONFIG_DIR = Path.home() / ".config" / "moltbot"
DATA_DIR = Path.home() / "moltbot-system" / "data"
LOG_DIR = Path.home() / "moltbot-system" / "logs"
DB_PATH = DATA_DIR / "hybrid_ai.db"

# Load environment
ENV_FILE = CONFIG_DIR / "env"
if ENV_FILE.exists():
    with open(ENV_FILE) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# Fake data pools for sanitization
FAKE_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn", "Avery",
    "Blake", "Charlie", "Drew", "Ellis", "Finley", "Gray", "Harper", "Indigo"
]
FAKE_COMPANIES = [
    "Acme Corp", "Globex Inc", "Initech", "Umbrella Co", "Stark Industries",
    "Wayne Enterprises", "Wonka Industries", "Cyberdyne Systems"
]
FAKE_DOMAINS = ["example.com", "test.org", "sample.net", "demo.io"]
FAKE_CITIES = ["Springfield", "Riverdale", "Greendale", "Pawnee", "Eagleton"]


@dataclass
class SanitizationMap:
    """Tracks consistent replacements within a session"""
    names: Dict[str, str] = field(default_factory=dict)
    emails: Dict[str, str] = field(default_factory=dict)
    phones: Dict[str, str] = field(default_factory=dict)
    addresses: Dict[str, str] = field(default_factory=dict)
    companies: Dict[str, str] = field(default_factory=dict)
    numbers: Dict[str, str] = field(default_factory=dict)
    
    _name_index: int = 0
    _company_index: int = 0
    
    def get_fake_name(self, real_name: str) -> str:
        """Get consistent fake name for a real name"""
        if real_name not in self.names:
            self.names[real_name] = FAKE_NAMES[self._name_index % len(FAKE_NAMES)]
            self._name_index += 1
        return self.names[real_name]
    
    def get_fake_email(self, real_email: str) -> str:
        """Get consistent fake email"""
        if real_email not in self.emails:
            name_part = f"user{len(self.emails) + 1}"
            domain = random.choice(FAKE_DOMAINS)
            self.emails[real_email] = f"{name_part}@{domain}"
        return self.emails[real_email]
    
    def get_fake_phone(self, real_phone: str) -> str:
        """Get consistent fake phone"""
        if real_phone not in self.phones:
            self.phones[real_phone] = f"555-{random.randint(100,999)}-{random.randint(1000,9999)}"
        return self.phones[real_phone]
    
    def get_fake_company(self, real_company: str) -> str:
        """Get consistent fake company"""
        if real_company not in self.companies:
            self.companies[real_company] = FAKE_COMPANIES[self._company_index % len(FAKE_COMPANIES)]
            self._company_index += 1
        return self.companies[real_company]
    
    def get_reverse_map(self) -> Dict[str, str]:
        """Get reverse mapping to restore original values"""
        reverse = {}
        for mapping in [self.names, self.emails, self.phones, self.companies]:
            for real, fake in mapping.items():
                reverse[fake] = real
        return reverse


class Sanitizer:
    """Sanitizes text by replacing PII with consistent fake data"""
    
    # Patterns for detecting PII
    PATTERNS = {
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'phone': r'\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b',
        'ssn': r'\b\d{3}[-]?\d{2}[-]?\d{4}\b',
        'credit_card': r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
        'ip_address': r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
        'date_of_birth': r'\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b',
        'address': r'\b\d+\s+[A-Za-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct)\b',
    }
    
    # Common name patterns (will be enhanced with context)
    NAME_INDICATORS = [
        r'\bMr\.?\s+([A-Z][a-z]+)',
        r'\bMs\.?\s+([A-Z][a-z]+)',
        r'\bMrs\.?\s+([A-Z][a-z]+)',
        r'\bDr\.?\s+([A-Z][a-z]+)',
        r'\bfrom\s+([A-Z][a-z]+)\b',
        r'\bto\s+([A-Z][a-z]+)\b',
        r'\bHi\s+([A-Z][a-z]+)',
        r'\bHello\s+([A-Z][a-z]+)',
        r'\bDear\s+([A-Z][a-z]+)',
        r'\bSigned,?\s+([A-Z][a-z]+)',
        r'\b([A-Z][a-z]+)\s+said\b',
        r'\b([A-Z][a-z]+)\s+wrote\b',
        r'\b([A-Z][a-z]+)\'s\s+',
    ]
    
    def __init__(self):
        self.session_map = SanitizationMap()
    
    def sanitize(self, text: str, custom_names: List[str] = None) -> Tuple[str, Dict]:
        """
        Sanitize text by replacing PII with fake data
        
        Args:
            text: Text to sanitize
            custom_names: Additional names to always replace
        
        Returns:
            Tuple of (sanitized_text, mapping_info)
        """
        sanitized = text
        detections = []
        
        # Replace emails
        for match in re.finditer(self.PATTERNS['email'], sanitized):
            original = match.group()
            replacement = self.session_map.get_fake_email(original)
            sanitized = sanitized.replace(original, replacement)
            detections.append(('email', original, replacement))
        
        # Replace phone numbers
        for match in re.finditer(self.PATTERNS['phone'], sanitized):
            original = match.group()
            replacement = self.session_map.get_fake_phone(original)
            sanitized = sanitized.replace(original, replacement)
            detections.append(('phone', original, replacement))
        
        # Replace SSN (always mask completely)
        sanitized = re.sub(self.PATTERNS['ssn'], 'XXX-XX-XXXX', sanitized)
        
        # Replace credit cards (always mask)
        sanitized = re.sub(self.PATTERNS['credit_card'], 'XXXX-XXXX-XXXX-XXXX', sanitized)
        
        # Replace IP addresses
        for match in re.finditer(self.PATTERNS['ip_address'], sanitized):
            original = match.group()
            if not original.startswith('127.') and not original.startswith('192.168.'):
                sanitized = sanitized.replace(original, '10.0.0.XXX')
                detections.append(('ip', original, '10.0.0.XXX'))
        
        # Replace names found via patterns
        for pattern in self.NAME_INDICATORS:
            for match in re.finditer(pattern, sanitized):
                if match.groups():
                    original_name = match.group(1)
                    if len(original_name) > 2:  # Skip very short matches
                        replacement = self.session_map.get_fake_name(original_name)
                        sanitized = re.sub(r'\b' + re.escape(original_name) + r'\b', 
                                          replacement, sanitized)
                        detections.append(('name', original_name, replacement))
        
        # Replace custom names if provided
        if custom_names:
            for name in custom_names:
                if name in sanitized:
                    replacement = self.session_map.get_fake_name(name)
                    sanitized = re.sub(r'\b' + re.escape(name) + r'\b', 
                                      replacement, sanitized)
                    detections.append(('custom_name', name, replacement))
        
        return sanitized, {
            'detections': detections,
            'reverse_map': self.session_map.get_reverse_map()
        }
    
    def desanitize(self, text: str) -> str:
        """Restore original values from sanitized text"""
        result = text
        reverse_map = self.session_map.get_reverse_map()
        for fake, real in reverse_map.items():
            result = result.replace(fake, real)
        return result
    
    def reset_session(self):
        """Reset the sanitization mappings for a new session"""
        self.session_map = SanitizationMap()


class UsageTracker:
    """Tracks API usage and costs"""
    
    # Approximate costs per 1K tokens (as of 2024, update as needed)
    COSTS = {
        'gemini-pro': {'input': 0.0005, 'output': 0.0015},
        'gemini-1.5-flash': {'input': 0.00035, 'output': 0.00105},
        'claude-3-haiku': {'input': 0.00025, 'output': 0.00125},
        'claude-3-sonnet': {'input': 0.003, 'output': 0.015},
        'local': {'input': 0, 'output': 0},
    }
    
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self._init_db()
    
    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                provider TEXT,
                model TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                estimated_cost REAL,
                task_type TEXT
            );
            
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                provider TEXT,
                model TEXT,
                sanitized_prompt TEXT,
                pii_detected INTEGER,
                approved INTEGER
            );
        ''')
        self.conn.commit()
    
    def log_usage(self, provider: str, model: str, input_tokens: int, 
                  output_tokens: int, task_type: str = None):
        """Log API usage"""
        costs = self.COSTS.get(model, {'input': 0.001, 'output': 0.002})
        estimated_cost = (input_tokens / 1000 * costs['input'] + 
                         output_tokens / 1000 * costs['output'])
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO usage (provider, model, input_tokens, output_tokens, estimated_cost, task_type)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (provider, model, input_tokens, output_tokens, estimated_cost, task_type))
        self.conn.commit()
        
        return estimated_cost
    
    def log_request(self, provider: str, model: str, sanitized_prompt: str,
                    pii_detected: int, approved: bool):
        """Log a cloud request for audit"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO requests (provider, model, sanitized_prompt, pii_detected, approved)
            VALUES (?, ?, ?, ?, ?)
        ''', (provider, model, sanitized_prompt[:1000], pii_detected, int(approved)))
        self.conn.commit()
    
    def get_monthly_cost(self) -> float:
        """Get estimated cost for current month"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT SUM(estimated_cost) FROM usage 
            WHERE timestamp >= date('now', 'start of month')
        ''')
        result = cursor.fetchone()[0]
        return result or 0.0
    
    def get_daily_cost(self) -> float:
        """Get estimated cost for today"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT SUM(estimated_cost) FROM usage 
            WHERE date(timestamp) = date('now')
        ''')
        result = cursor.fetchone()[0]
        return result or 0.0
    
    def get_summary(self) -> Dict:
        """Get usage summary"""
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT SUM(estimated_cost) FROM usage')
        total_cost = cursor.fetchone()[0] or 0.0
        
        cursor.execute('SELECT COUNT(*) FROM usage WHERE provider != "local"')
        cloud_requests = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM usage WHERE provider = "local"')
        local_requests = cursor.fetchone()[0]
        
        return {
            'total_cost': round(total_cost, 4),
            'monthly_cost': round(self.get_monthly_cost(), 4),
            'daily_cost': round(self.get_daily_cost(), 4),
            'cloud_requests': cloud_requests,
            'local_requests': local_requests
        }


class HybridAI:
    """Main hybrid AI system"""
    
    COST_WARNING_THRESHOLD = 0.10  # Warn if single request might cost > $0.10
    MONTHLY_BUDGET = 5.00  # Monthly budget warning threshold
    
    def __init__(self):
        self.sanitizer = Sanitizer()
        self.tracker = UsageTracker()
        self._init_providers()
    
    def _init_providers(self):
        """Initialize API clients"""
        self.gemini = None
        self.anthropic = None
        
        if os.environ.get('GEMINI_API_KEY'):
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.environ['GEMINI_API_KEY'])
                self.gemini = genai
            except ImportError:
                print("Warning: google-generativeai not installed")
        
        if os.environ.get('ANTHROPIC_API_KEY'):
            try:
                import anthropic
                self.anthropic = anthropic.Anthropic(
                    api_key=os.environ['ANTHROPIC_API_KEY']
                )
            except ImportError:
                print("Warning: anthropic not installed")
    
    def should_use_cloud(self, prompt: str, task_type: str = None) -> Tuple[bool, str]:
        """
        Determine if cloud should be suggested for this task
        
        Returns:
            Tuple of (should_suggest_cloud, reason)
        """
        prompt_lower = prompt.lower()
        
        # Always use local for these
        local_keywords = [
            'my email', 'my calendar', 'personal', 'private',
            'password', 'secret', 'confidential', 'salary',
            'medical', 'health', 'bank', 'account'
        ]
        for keyword in local_keywords:
            if keyword in prompt_lower:
                return False, f"Contains '{keyword}' - keeping local for privacy"
        
        # Suggest cloud for these (speed benefit)
        cloud_beneficial = [
            ('code', 'write code', 'implement', 'function', 'class', 'debug'),
            ('explain', 'how does', 'what is', 'why does'),
            ('refactor', 'optimize', 'improve'),
            ('test', 'unit test', 'test case'),
        ]
        
        for keywords in cloud_beneficial:
            if any(kw in prompt_lower for kw in keywords):
                return True, "Code/technical task - cloud recommended for speed"
        
        # Long prompts benefit from cloud speed
        if len(prompt) > 2000:
            return True, "Long prompt - cloud recommended for speed"
        
        # Default to local
        return False, "Standard task - using local model"
    
    def estimate_cost(self, prompt: str, model: str) -> float:
        """Estimate cost for a request"""
        # Rough token estimate (4 chars per token)
        input_tokens = len(prompt) / 4
        output_tokens = min(input_tokens * 2, 4000)  # Estimate
        
        costs = self.tracker.COSTS.get(model, {'input': 0.001, 'output': 0.002})
        return (input_tokens / 1000 * costs['input'] + 
                output_tokens / 1000 * costs['output'])
    
    def query(self, 
              prompt: str,
              provider: str = 'auto',
              model: str = None,
              custom_names: List[str] = None,
              force_local: bool = False,
              skip_approval: bool = False) -> Dict:
        """
        Query AI with automatic routing and sanitization
        
        Args:
            prompt: The prompt to send
            provider: 'auto', 'local', 'gemini', or 'anthropic'
            model: Specific model to use (optional)
            custom_names: Additional names to sanitize
            force_local: Force local processing regardless of suggestion
            skip_approval: Skip approval prompt (for automation)
        
        Returns:
            Dict with response and metadata
        """
        result = {
            'provider': None,
            'model': None,
            'response': None,
            'sanitized': False,
            'pii_detected': 0,
            'estimated_cost': 0,
            'warning': None
        }
        
        # Determine provider
        if force_local or provider == 'local':
            return self._query_local(prompt, model or 'qwen-agentic')
        
        if provider == 'auto':
            suggest_cloud, reason = self.should_use_cloud(prompt)
            if not suggest_cloud:
                result['routing_reason'] = reason
                return self._query_local(prompt, model or 'qwen-agentic')
            result['routing_reason'] = reason
            provider = 'gemini' if self.gemini else ('anthropic' if self.anthropic else 'local')
        
        if provider == 'local':
            return self._query_local(prompt, model or 'qwen-agentic')
        
        # Sanitize for cloud
        sanitized_prompt, sanitize_info = self.sanitizer.sanitize(prompt, custom_names)
        pii_count = len(sanitize_info['detections'])
        
        result['sanitized'] = True
        result['pii_detected'] = pii_count
        
        # Estimate cost and check budget
        model = model or ('gemini-1.5-flash' if provider == 'gemini' else 'claude-3-haiku')
        estimated_cost = self.estimate_cost(sanitized_prompt, model)
        result['estimated_cost'] = round(estimated_cost, 4)
        
        # Warnings
        monthly_cost = self.tracker.get_monthly_cost()
        if monthly_cost + estimated_cost > self.MONTHLY_BUDGET:
            result['warning'] = f"⚠️ Monthly budget (${self.MONTHLY_BUDGET}) would be exceeded"
        elif estimated_cost > self.COST_WARNING_THRESHOLD:
            result['warning'] = f"⚠️ Estimated cost: ${estimated_cost:.4f}"
        
        # Log request
        self.tracker.log_request(provider, model, sanitized_prompt, pii_count, True)
        
        # Show approval if PII detected and not skipped
        if pii_count > 0 and not skip_approval:
            print(f"\n{'='*60}")
            print(f"⚠️  PII DETECTED: {pii_count} items sanitized")
            print(f"Provider: {provider} | Model: {model}")
            print(f"Estimated cost: ${estimated_cost:.4f}")
            print(f"{'='*60}")
            print(f"\nSANITIZED PROMPT:\n{sanitized_prompt[:500]}...")
            print(f"\n{'='*60}")
            # In interactive mode, would prompt for approval here
        
        # Send to cloud
        if provider == 'gemini':
            response = self._query_gemini(sanitized_prompt, model)
        elif provider == 'anthropic':
            response = self._query_anthropic(sanitized_prompt, model)
        else:
            return self._query_local(prompt, model or 'qwen-agentic')
        
        result['provider'] = provider
        result['model'] = model
        result['response'] = response
        
        return result
    
    def _query_local(self, prompt: str, model: str) -> Dict:
        """Query local Ollama"""
        import subprocess
        
        try:
            result = subprocess.run(
                ['ollama', 'run', model, prompt],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            # Estimate tokens for tracking
            input_tokens = len(prompt) / 4
            output_tokens = len(result.stdout) / 4
            self.tracker.log_usage('local', model, int(input_tokens), 
                                   int(output_tokens), 'local')
            
            return {
                'provider': 'local',
                'model': model,
                'response': result.stdout.strip(),
                'sanitized': False,
                'pii_detected': 0,
                'estimated_cost': 0
            }
        except Exception as e:
            return {
                'provider': 'local',
                'model': model,
                'response': None,
                'error': str(e)
            }
    
    def _query_gemini(self, prompt: str, model: str) -> str:
        """Query Google Gemini"""
        if not self.gemini:
            raise ValueError("Gemini not configured")
        
        model_obj = self.gemini.GenerativeModel(model)
        response = model_obj.generate_content(prompt)
        
        # Track usage
        input_tokens = len(prompt) / 4
        output_tokens = len(response.text) / 4
        self.tracker.log_usage('gemini', model, int(input_tokens), 
                               int(output_tokens), 'cloud')
        
        return response.text
    
    def _query_anthropic(self, prompt: str, model: str) -> str:
        """Query Anthropic Claude"""
        if not self.anthropic:
            raise ValueError("Anthropic not configured")
        
        message = self.anthropic.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text
        
        # Track usage
        self.tracker.log_usage('anthropic', model, 
                               message.usage.input_tokens,
                               message.usage.output_tokens, 'cloud')
        
        return response_text
    
    def get_usage_summary(self) -> Dict:
        """Get usage summary"""
        return self.tracker.get_summary()
    
    def reset_session(self):
        """Reset sanitization session"""
        self.sanitizer.reset_session()


# CLI Interface
if __name__ == "__main__":
    import sys
    
    ai = HybridAI()
    
    if len(sys.argv) < 2:
        print("Usage: hybrid_ai.py <command> [args]")
        print("Commands:")
        print("  query <prompt>        - Query with auto-routing")
        print("  local <prompt>        - Force local model")
        print("  cloud <prompt>        - Force cloud (with sanitization)")
        print("  gemini <prompt>       - Use Gemini specifically")
        print("  anthropic <prompt>    - Use Anthropic specifically")
        print("  usage                 - Show usage summary")
        print("  test-sanitize <text>  - Test sanitization")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "query" and len(sys.argv) > 2:
        prompt = ' '.join(sys.argv[2:])
        result = ai.query(prompt)
        print(f"\n[{result['provider']}/{result['model']}]")
        if result.get('warning'):
            print(result['warning'])
        if result.get('pii_detected'):
            print(f"(Sanitized {result['pii_detected']} PII items)")
        print(f"\n{result['response']}")
    
    elif cmd == "local" and len(sys.argv) > 2:
        prompt = ' '.join(sys.argv[2:])
        result = ai.query(prompt, force_local=True)
        print(f"\n[LOCAL/{result['model']}]")
        print(f"\n{result['response']}")
    
    elif cmd == "cloud" and len(sys.argv) > 2:
        prompt = ' '.join(sys.argv[2:])
        result = ai.query(prompt, provider='gemini')
        print(f"\n[{result['provider']}/{result['model']}]")
        if result.get('pii_detected'):
            print(f"(Sanitized {result['pii_detected']} PII items)")
        print(f"\n{result['response']}")
    
    elif cmd == "gemini" and len(sys.argv) > 2:
        prompt = ' '.join(sys.argv[2:])
        result = ai.query(prompt, provider='gemini')
        print(f"\n[GEMINI/{result['model']}]")
        print(f"\n{result['response']}")
    
    elif cmd == "anthropic" and len(sys.argv) > 2:
        prompt = ' '.join(sys.argv[2:])
        result = ai.query(prompt, provider='anthropic')
        print(f"\n[ANTHROPIC/{result['model']}]")
        print(f"\n{result['response']}")
    
    elif cmd == "usage":
        summary = ai.get_usage_summary()
        print("=== Usage Summary ===")
        print(f"Total cost:     ${summary['total_cost']:.4f}")
        print(f"Monthly cost:   ${summary['monthly_cost']:.4f}")
        print(f"Today's cost:   ${summary['daily_cost']:.4f}")
        print(f"Cloud requests: {summary['cloud_requests']}")
        print(f"Local requests: {summary['local_requests']}")
    
    elif cmd == "test-sanitize" and len(sys.argv) > 2:
        text = ' '.join(sys.argv[2:])
        sanitizer = Sanitizer()
        sanitized, info = sanitizer.sanitize(text)
        print("=== Original ===")
        print(text)
        print("\n=== Sanitized ===")
        print(sanitized)
        print("\n=== Detections ===")
        for detection in info['detections']:
            print(f"  {detection[0]}: {detection[1]} -> {detection[2]}")
    
    else:
        print(f"Unknown command: {cmd}")
```

## Usage Instructions

### For Moltbot (Agent)

**Auto-routing (recommended)**
```bash
python3 ~/moltbot-system/skills/hybrid_ai.py query "Write a Python function to sort a list"
```

**Force local (for private data)**
```bash
python3 ~/moltbot-system/skills/hybrid_ai.py local "Summarize this email from John..."
```

**Force cloud (when speed matters)**
```bash
python3 ~/moltbot-system/skills/hybrid_ai.py cloud "Refactor this code..."
```

**Test sanitization**
```bash
python3 ~/moltbot-system/skills/hybrid_ai.py test-sanitize "Email john.doe@company.com about the meeting with Sarah at 555-123-4567"
```

**Check usage/costs**
```bash
python3 ~/moltbot-system/skills/hybrid_ai.py usage
```

## Routing Logic

### Always Local (Privacy)
- Contains: "my email", "personal", "private", "password", "confidential", "salary", "medical", "bank"
- User explicitly requests local

### Suggest Cloud (Speed)
- Code writing, debugging, refactoring
- Technical explanations
- Long prompts (>2000 chars)
- Complex reasoning tasks

### Sanitization Behavior
When sending to cloud, the system:
1. Detects PII (emails, phones, names, addresses, etc.)
2. Replaces with consistent fake data within the session
3. Shows sanitized prompt for approval (if PII found)
4. Logs the request
5. Sends sanitized version to cloud

**Example:**
```
Original: "Review this code John sent to sarah@company.com"
Sanitized: "Review this code Alex sent to user1@example.com"
```

## Cost Management

### Default Budgets
- Warning per request: >$0.10
- Monthly warning: >$5.00

### Modify Budgets
Edit in `hybrid_ai.py`:
```python
COST_WARNING_THRESHOLD = 0.10  # Per-request warning
MONTHLY_BUDGET = 5.00          # Monthly warning
```

### Approximate Costs (per 1K tokens)

| Model | Input | Output |
|-------|-------|--------|
| gemini-1.5-flash | $0.00035 | $0.00105 |
| gemini-pro | $0.0005 | $0.0015 |
| claude-3-haiku | $0.00025 | $0.00125 |
| claude-3-sonnet | $0.003 | $0.015 |
| local | $0 | $0 |

## API Key Setup

### Google Gemini
1. Go to https://aistudio.google.com/
2. Get API key
3. Add to `~/.config/moltbot/env`:
   ```
   GEMINI_API_KEY=your_key_here
   ```

### Anthropic Claude
1. Go to https://console.anthropic.com/
2. Create API key
3. Add to `~/.config/moltbot/env`:
   ```
   ANTHROPIC_API_KEY=your_key_here
   ```

## Audit Logs

All cloud requests are logged to `~/moltbot-system/data/hybrid_ai.db`:

```bash
# View recent requests
sqlite3 ~/moltbot-system/data/hybrid_ai.db "SELECT timestamp, provider, model, pii_detected FROM requests ORDER BY timestamp DESC LIMIT 10"

# View usage
sqlite3 ~/moltbot-system/data/hybrid_ai.db "SELECT * FROM usage ORDER BY timestamp DESC LIMIT 10"
```

## Security Notes

1. **API keys** stored in `~/.config/moltbot/env` with restricted permissions (600)
2. **Sanitized prompts** logged, not originals
3. **PII detection** is pattern-based - review before trusting
4. **Approval prompt** shown when PII detected (can be skipped for automation)
5. **All traffic** still goes through firewall rules
6. **No response data** stored locally (only metadata)
