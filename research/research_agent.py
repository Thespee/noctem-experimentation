#!/usr/bin/env python3
"""
Noctem Research Agent
Automated research system using Warp CLI for continuous learning.

This agent will:
- Systematically pursue research questions across STEAM disciplines
- Use Warp CLI for AI-assisted research
- Save findings regularly to prevent data loss
- Track progress and manage research queue
- Run until credits exhausted or 100 questions answered
"""

import json
import subprocess
import time
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import signal
import traceback

# Configuration
RESEARCH_DIR = Path(__file__).parent
FINDINGS_DIR = RESEARCH_DIR / "findings"
QUESTIONS_FILE = RESEARCH_DIR / "questions.json"
PROGRESS_FILE = RESEARCH_DIR / "progress.json"
STATE_FILE = RESEARCH_DIR / "state.json"

MAX_QUESTIONS = 100
SAVE_INTERVAL_MINUTES = 5
WARP_TIMEOUT_SECONDS = 300


class ResearchState:
    """Manages research progress and state."""
    
    def __init__(self):
        self.questions_answered = 0
        self.current_question = None
        self.start_time = None
        self.last_save = None
        self.findings = []
        self.active = True
        self.load()
    
    def load(self):
        """Load state from disk."""
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text())
                self.questions_answered = data.get("questions_answered", 0)
                self.start_time = data.get("start_time")
                self.last_save = data.get("last_save")
                print(f"📊 Loaded state: {self.questions_answered} questions answered")
            except Exception as e:
                print(f"⚠️ Could not load state: {e}")
    
    def save(self):
        """Save state to disk."""
        try:
            data = {
                "questions_answered": self.questions_answered,
                "current_question": self.current_question,
                "start_time": self.start_time,
                "last_save": datetime.now().isoformat(),
                "findings_count": len(self.findings)
            }
            STATE_FILE.write_text(json.dumps(data, indent=2))
            self.last_save = datetime.now()
            print(f"💾 State saved ({self.questions_answered}/{MAX_QUESTIONS} questions)")
        except Exception as e:
            print(f"❌ Could not save state: {e}")
    
    def should_save(self) -> bool:
        """Check if it's time to save."""
        if self.last_save is None:
            return True
        elapsed = datetime.now() - self.last_save
        return elapsed > timedelta(minutes=SAVE_INTERVAL_MINUTES)


class QuestionManager:
    """Manages research question queue."""
    
    def __init__(self):
        self.questions: List[Dict] = []
        self.load()
    
    def load(self):
        """Load questions from file."""
        if QUESTIONS_FILE.exists():
            try:
                self.questions = json.loads(QUESTIONS_FILE.read_text())
                print(f"📋 Loaded {len(self.questions)} research questions")
            except Exception as e:
                print(f"❌ Could not load questions: {e}")
                self.questions = []
    
    def save(self):
        """Save questions to file."""
        try:
            QUESTIONS_FILE.write_text(json.dumps(self.questions, indent=2))
        except Exception as e:
            print(f"❌ Could not save questions: {e}")
    
    def get_next(self) -> Optional[Dict]:
        """Get next unanswered question."""
        for q in self.questions:
            if q.get("status") == "pending":
                return q
        return None
    
    def mark_completed(self, question_id: str):
        """Mark a question as completed."""
        for q in self.questions:
            if q.get("id") == question_id:
                q["status"] = "completed"
                q["completed_at"] = datetime.now().isoformat()
                break
        self.save()
    
    def mark_failed(self, question_id: str, error: str):
        """Mark a question as failed."""
        for q in self.questions:
            if q.get("id") == question_id:
                q["status"] = "failed"
                q["error"] = error
                q["failed_at"] = datetime.now().isoformat()
                break
        self.save()
    
    def add_question(self, question: str, category: str, priority: int = 5):
        """Add a new research question."""
        question_id = f"q{len(self.questions) + 1:03d}"
        self.questions.append({
            "id": question_id,
            "question": question,
            "category": category,
            "priority": priority,
            "status": "pending",
            "created_at": datetime.now().isoformat()
        })
        self.save()
        return question_id
    
    def needs_new_questions(self) -> bool:
        """Check if we need to generate new questions."""
        pending = sum(1 for q in self.questions if q.get("status") == "pending")
        return pending < 3


class WarpResearcher:
    """Handles Warp CLI interactions for research."""
    
    def __init__(self):
        # Try to find warp executable
        import shutil
        self.warp_cmd = shutil.which("warp")
        if self.warp_cmd is None:
            # Try common installation paths
            import os
            possible_paths = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Warp\bin\warp.cmd"),
                os.path.expandvars(r"%PROGRAMFILES%\Warp\warp.exe"),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    self.warp_cmd = path
                    break
        self.check_warp_available()
    
    def check_warp_available(self) -> bool:
        """Check if Warp CLI is available."""
        if self.warp_cmd is None:
            print(f"❌ Warp CLI not found in PATH")
            print(f"   Install from: https://www.warp.dev/")
            sys.exit(1)
        
        try:
            result = subprocess.run(
                [self.warp_cmd, "--help"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                print(f"✓ Warp CLI available: {self.warp_cmd}")
                return True
            else:
                print(f"⚠️ Warp CLI not responding properly")
                return False
        except Exception as e:
            print(f"❌ Error checking Warp: {e}")
            return False
    
    def research_question(self, question: str, category: str) -> Tuple[bool, str, Optional[str]]:
        """
        Use Warp to research a question.
        
        Returns: (success, result_text, error)
        """
        print(f"\n🔍 Researching: {question}")
        print(f"   Category: {category}")
        
        # Construct a comprehensive research prompt
        prompt = f"""Research Question: {question}

Please provide a comprehensive answer covering:
1. Current state of the art / latest developments
2. Key research papers, projects, or implementations
3. Practical implications for the Noctem project (a lightweight AI assistant for low-spec hardware)
4. Concrete recommendations or action items
5. Related questions worth exploring

Focus on actionable insights and cite specific sources when possible.
Category: {category}"""
        
        try:
            # Use Warp CLI to get research
            result = subprocess.run(
                [self.warp_cmd, "agent", "run", "--prompt", prompt],
                capture_output=True,
                text=True,
                timeout=WARP_TIMEOUT_SECONDS
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    print(f"✓ Research completed ({len(output)} chars)")
                    return True, output, None
                else:
                    error = "Empty response from Warp"
                    print(f"❌ {error}")
                    return False, "", error
            else:
                error = result.stderr.strip() or "Warp command failed"
                print(f"❌ {error}")
                return False, "", error
                
        except subprocess.TimeoutExpired:
            error = f"Warp timed out after {WARP_TIMEOUT_SECONDS}s"
            print(f"⏱️ {error}")
            return False, "", error
        except Exception as e:
            error = f"Research failed: {str(e)}"
            print(f"❌ {error}")
            traceback.print_exc()
            return False, "", error
    
    def generate_new_questions(self, existing_questions: List[Dict]) -> List[Dict]:
        """Use Warp to generate new research questions."""
        print(f"\n🤔 Generating new research questions...")
        
        # Get categories we've covered
        categories = set(q.get("category") for q in existing_questions)
        
        prompt = f"""Generate 5 new research questions for the Noctem project (a lightweight agentic AI assistant framework for low-spec hardware).

Existing categories covered: {', '.join(categories)}

Generate questions across STEAM disciplines:
- Science: AI/ML advances, cognitive science, neuroscience
- Technology: Hardware optimization, edge computing, distributed systems
- Engineering: System design, reliability, deployment
- Arts: UX/UI, accessibility, human factors
- Mathematics: Algorithms, optimization, complexity theory

Also consider:
- UN Sustainable Development Goals alignment
- Ethical AI and human rights
- Open source best practices
- Real-world deployment challenges

Format each question as:
{{
  "question": "Clear, specific research question",
  "category": "One of: Science, Technology, Engineering, Arts, Math, Ethics, Sustainability, Open Source",
  "priority": 1-10 (1=highest)
}}

Return ONLY valid JSON array of 5 questions."""
        
        try:
            result = subprocess.run(
                [self.warp_cmd, "agent", "run", "--prompt", prompt],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                
                # Try to extract JSON from output
                # Look for JSON array markers
                start = output.find('[')
                end = output.rfind(']') + 1
                
                if start >= 0 and end > start:
                    json_str = output[start:end]
                    questions = json.loads(json_str)
                    
                    if isinstance(questions, list) and len(questions) > 0:
                        print(f"✓ Generated {len(questions)} new questions")
                        return questions
                
                print(f"⚠️ Could not parse questions from Warp output")
                return []
            else:
                print(f"❌ Question generation failed")
                return []
                
        except Exception as e:
            print(f"❌ Error generating questions: {e}")
            return []


class FindingsWriter:
    """Handles writing research findings to disk."""
    
    @staticmethod
    def save_finding(question: Dict, result: str):
        """Save a research finding to a markdown file."""
        question_id = question.get("id", "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        category = question.get("category", "general")
        
        # Create category subdirectory
        category_dir = FINDINGS_DIR / category.lower().replace(" ", "_")
        category_dir.mkdir(exist_ok=True)
        
        # Generate filename
        filename = f"{timestamp}_{question_id}.md"
        filepath = category_dir / filename
        
        # Build markdown content
        content = f"""# {question.get('question')}

**Question ID**: {question_id}  
**Category**: {category}  
**Priority**: {question.get('priority', 'N/A')}  
**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Research Findings

{result}

---

## Metadata

```json
{json.dumps(question, indent=2)}
```

*Generated by Noctem Research Agent*
"""
        
        try:
            filepath.write_text(content, encoding='utf-8')
            print(f"📝 Saved finding: {filepath.relative_to(RESEARCH_DIR)}")
            return True
        except Exception as e:
            print(f"❌ Could not save finding: {e}")
            return False


class ResearchAgent:
    """Main research agent orchestrator."""
    
    def __init__(self):
        self.state = ResearchState()
        self.questions = QuestionManager()
        self.researcher = WarpResearcher()
        self.writer = FindingsWriter()
        self.running = True
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
    
    def handle_shutdown(self, signum, frame):
        """Handle graceful shutdown."""
        print(f"\n\n🛑 Shutdown signal received")
        self.running = False
        self.state.save()
        print(f"✓ State saved. Research can be resumed later.")
        sys.exit(0)
    
    def run(self):
        """Main research loop."""
        print(f"\n{'='*60}")
        print(f"🌙 Noctem Research Agent Starting")
        print(f"{'='*60}\n")
        print(f"Target: {MAX_QUESTIONS} questions")
        print(f"Progress: {self.state.questions_answered} completed")
        print(f"Remaining: {MAX_QUESTIONS - self.state.questions_answered}")
        print(f"\nFindings will be saved to: {FINDINGS_DIR}")
        print(f"\n{'='*60}\n")
        
        if self.state.start_time is None:
            self.state.start_time = datetime.now().isoformat()
            self.state.save()
        
        while self.running and self.state.questions_answered < MAX_QUESTIONS:
            try:
                # Check if we need new questions
                if self.questions.needs_new_questions():
                    print(f"\n🎯 Generating new research questions...")
                    new_questions = self.researcher.generate_new_questions(self.questions.questions)
                    for q in new_questions:
                        self.questions.add_question(
                            q.get("question"),
                            q.get("category"),
                            q.get("priority", 5)
                        )
                
                # Get next question
                question = self.questions.get_next()
                if not question:
                    print(f"\n✅ All questions answered!")
                    break
                
                self.state.current_question = question.get("id")
                
                # Research the question
                success, result, error = self.researcher.research_question(
                    question.get("question"),
                    question.get("category")
                )
                
                if success:
                    # Save finding
                    self.writer.save_finding(question, result)
                    self.questions.mark_completed(question.get("id"))
                    self.state.questions_answered += 1
                    self.state.findings.append(question.get("id"))
                    
                    print(f"\n✅ Question {self.state.questions_answered}/{MAX_QUESTIONS} completed")
                else:
                    # Mark as failed
                    self.questions.mark_failed(question.get("id"), error)
                    print(f"\n⚠️ Question failed, moving to next")
                
                # Periodic save
                if self.state.should_save():
                    self.state.save()
                
                # Brief pause between questions
                time.sleep(2)
                
            except KeyboardInterrupt:
                print(f"\n\n⏸️ Interrupted by user")
                break
            except Exception as e:
                print(f"\n❌ Unexpected error: {e}")
                traceback.print_exc()
                # Continue with next question
                time.sleep(5)
        
        # Final save
        self.state.save()
        
        # Summary
        print(f"\n\n{'='*60}")
        print(f"🏁 Research Session Complete")
        print(f"{'='*60}\n")
        print(f"Questions answered: {self.state.questions_answered}/{MAX_QUESTIONS}")
        print(f"Findings saved in: {FINDINGS_DIR}")
        
        if self.state.start_time:
            start = datetime.fromisoformat(self.state.start_time)
            duration = datetime.now() - start
            print(f"Duration: {duration}")
        
        print(f"\n{'='*60}\n")


def main():
    """Entry point."""
    try:
        agent = ResearchAgent()
        agent.run()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
