# Moltbot Skill: Router

## Purpose
The Router is the **primary interface** for all user requests. It's a tiny, fast model that:
1. Understands what the user wants
2. Decides the best way to fulfill it
3. Dispatches to the appropriate resource
4. Returns results

It does NOT do heavy lifting itself—it orchestrates.

## Design Philosophy
- **Fast over smart**: Speed matters more than capability for routing decisions
- **Silent operation**: Don't explain routing unless asked
- **Never auto-fallback to cloud**: User must explicitly approve cloud usage
- **Tool-first**: Check if a tool exists before using a model

---

## Routing Hierarchy

When a request comes in, the Router evaluates in this order:

### 1. Exact Tool Match
Does a script/tool exist that directly handles this?
```
"Check my calendar" → calendar_reader.py
"Scrape example.com" → web_scraper.py
"What's the weather" → weather.py (if exists)
```

### 2. Pattern Match (Previously Solved)
Does this match a known pattern with an existing solution?
```
"Scrape [any URL]" → web_scraper.py with URL parameter
"Summarize this email from..." → email_summarizer template
```

### 3. Simple Task (Handle Locally)
Is this simple enough for the router model itself?
```
"Hello" → Respond directly
"What time is it" → Run `date`, respond
"Convert 5km to miles" → Calculate, respond
```

### 4. Complex Task (Escalate to Primary Model)
Does this need deeper reasoning?
```
"Write a Python function to..." → qwen-agentic (7B)
"Explain how transformers work" → qwen-agentic (7B)
"Debug this code..." → qwen-agentic (7B)
```

### 5. Cloud Burst (User Must Approve)
Is this beyond local capability AND user requests cloud?
```
"Use cloud: Write a complex analysis..." → Sanitize → Cloud
```
**Never automatic.** User must say "use cloud" or similar.

---

## Tool Registry

The Router needs to know what tools exist. This is a simple JSON file.

### File: `~/moltbot-system/config/tools.json`

```json
{
  "tools": [
    {
      "name": "calendar_reader",
      "path": "~/moltbot-system/skills/calendar_reader.py",
      "triggers": ["calendar", "schedule", "meetings", "events", "what's on"],
      "description": "Read Google Calendar events",
      "requires_auth": true
    },
    {
      "name": "gmail_reader", 
      "path": "~/moltbot-system/skills/gmail_reader.py",
      "triggers": ["email", "gmail", "inbox", "unread"],
      "description": "Read and summarize emails",
      "requires_auth": true
    },
    {
      "name": "web_scraper",
      "path": "~/moltbot-system/skills/web_scraper.py",
      "triggers": ["scrape", "fetch", "get page", "website"],
      "params": ["url"],
      "description": "Scrape web pages"
    },
    {
      "name": "hybrid_ai",
      "path": "~/moltbot-system/skills/hybrid_ai.py",
      "triggers": ["use cloud", "cloud:", "fast mode"],
      "description": "Route to cloud AI with sanitization",
      "requires_approval": true
    }
  ],
  "patterns": [
    {
      "regex": "scrape\\s+(https?://\\S+)",
      "tool": "web_scraper",
      "extract": {"url": 1}
    },
    {
      "regex": "what('s| is) on my calendar",
      "tool": "calendar_reader"
    }
  ]
}
```

---

## Routing Logic (Pseudocode)

```python
def route(user_input):
    # 1. Check exact tool triggers
    for tool in tools:
        if any(trigger in user_input.lower() for trigger in tool.triggers):
            if tool.requires_approval and not user_approved():
                return ask_approval(tool)
            return execute_tool(tool, user_input)
    
    # 2. Check pattern matches
    for pattern in patterns:
        match = regex_match(pattern.regex, user_input)
        if match:
            params = extract_params(match, pattern.extract)
            return execute_tool(pattern.tool, params)
    
    # 3. Classify complexity
    complexity = classify(user_input)
    
    if complexity == "simple":
        # Router handles directly
        return router_model.generate(user_input)
    
    elif complexity == "complex":
        # Escalate to primary model
        return primary_model.generate(user_input)
    
    elif complexity == "cloud_requested":
        # User explicitly wants cloud
        return hybrid_ai.query(user_input, provider='auto')
    
    else:
        # Default: try router, escalate if needed
        response = router_model.generate(user_input)
        if response.quality < threshold:
            return primary_model.generate(user_input)
        return response
```

---

## Complexity Classification

The router model itself classifies requests. Prompt:

```
Classify this request into one category:
- SIMPLE: greeting, time, basic math, yes/no question, single fact
- COMPLEX: code generation, explanation, analysis, creative writing, debugging
- TOOL: mentions calendar, email, scraping, or other known tool
- CLOUD: explicitly requests cloud/fast mode

Request: "{user_input}"

Category:
```

Expected output: Single word (SIMPLE/COMPLEX/TOOL/CLOUD)

---

## Implementation Approach

### File: `~/moltbot-system/skills/router.py`

```
router.py route "user input"     # Route and execute
router.py classify "user input"  # Just classify, don't execute
router.py tools                   # List available tools
router.py add-tool <name> <path>  # Register new tool
```

### Core Functions

1. **load_tools()**: Read tools.json
2. **match_tool(input)**: Check triggers and patterns
3. **classify(input)**: Ask router model for classification
4. **execute_tool(tool, input)**: Run the tool script
5. **escalate(input)**: Send to primary model
6. **route(input)**: Main orchestration function

---

## Router Model Configuration

The router uses a tiny model optimized for classification and brief responses.

### Modelfile: `~/router.Modelfile`

```
FROM qwen2.5:1.5b-instruct-q4_K_M

SYSTEM """You are a task router. Be extremely concise.

When classifying:
- Respond with ONLY the category: SIMPLE, COMPLEX, TOOL, or CLOUD
- No explanation unless asked

When handling SIMPLE tasks:
- One sentence maximum
- Direct answers only
- No pleasantries

Available tools: {tools_summary}
"""

PARAMETER num_ctx 2048
PARAMETER temperature 0.2
PARAMETER num_thread 2
```

Low temperature (0.2) for consistent routing decisions.

---

## Interaction Flow

### Example 1: Tool Match
```
User: "What's on my calendar today?"
Router: [matches "calendar" trigger]
Router: [executes calendar_reader.py]
Output: "3 events today: standup at 9am, lunch at 12pm, review at 3pm."
```

### Example 2: Simple (Router Handles)
```
User: "What's 15% of 230?"
Router: [classifies as SIMPLE]
Router: [calculates directly]
Output: "34.5"
```

### Example 3: Complex (Escalate)
```
User: "Write a Python decorator that caches function results"
Router: [classifies as COMPLEX]
Router: [escalates to qwen-agentic]
Output: [7B model generates code]
```

### Example 4: Cloud (User Requested)
```
User: "Use cloud: analyze this complex dataset..."
Router: [classifies as CLOUD]
Router: [passes to hybrid_ai.py]
hybrid_ai: [sanitizes, sends to cloud, returns result]
```

### Example 5: Cloud (Not Requested, Complex Task)
```
User: "Analyze this complex dataset..."
Router: [classifies as COMPLEX]
Router: [escalates to local qwen-agentic]
Output: [Local model does its best]
```
**Does NOT auto-fallback to cloud.**

---

## Error Handling

### Tool Not Found
```
Router: "No tool found for that. Want me to try with the local model?"
```

### Tool Execution Fails
```
Router: "calendar_reader failed: [error]. Retrying or try manually?"
```

### Model Overloaded
```
Router: "System is busy. Queue position: 2. Wait or try simpler request?"
```

### Classification Uncertain
When router model isn't sure, default to COMPLEX (escalate).

---

## Logging

All routing decisions logged to `~/moltbot-system/logs/router.log`:

```
2026-02-08T02:00:00 | INPUT: "What's on my calendar" | MATCH: tool:calendar_reader | TIME: 0.1s
2026-02-08T02:00:05 | INPUT: "Write Python code" | CLASS: COMPLEX | ESCALATE: qwen-agentic | TIME: 12.3s
2026-02-08T02:00:20 | INPUT: "Hello" | CLASS: SIMPLE | DIRECT | TIME: 0.8s
```

---

## Integration Points

### With Optimizer
- Router checks `hardware.json` to know what primary model is available
- If no primary model configured, everything stays at router level or suggests cloud

### With Hybrid AI
- Router can invoke hybrid_ai.py for cloud requests
- Respects "never auto-fallback" rule

### With Moltbot/Clawdbot
- Router can be the default model in clawdbot.json
- Or Moltbot calls router.py as a tool

---

## Future Enhancements

1. **Learning from corrections**: If user says "that should have been COMPLEX", remember
2. **Confidence scoring**: Router reports confidence, escalate if low
3. **Multi-step routing**: Break complex requests into steps
4. **Caching**: Remember recent classifications
5. **Tool discovery**: Auto-detect new tools in skills directory

---

## Security Notes

- Router never sends data to cloud without explicit user request
- Tool execution is sandboxed by existing firewall rules
- Logging excludes sensitive content (just metadata)
- Classification prompts don't include full user data

---

*Think fast. Route smart. Execute right.*
