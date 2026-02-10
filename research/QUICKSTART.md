# 🚀 Research Agent Quick Start

## One-Command Start

```powershell
cd C:\Users\Rage4\Documents\GitHub\noctem\research
python research_agent.py
```

## What It Does

✅ Researches 100 questions across STEAM disciplines  
✅ Uses Warp CLI for AI-assisted research  
✅ Saves findings to markdown files  
✅ Auto-generates new questions when needed  
✅ Runs until: credits out, 100 questions done, or Ctrl+C  

## Initial Questions

**Q1 (Technology)**: Latest AI optimization for low-spec hardware  
**Q2 (Ethics)**: UN SDGs & human rights alignment for AI  
**Q3 (Mathematics)**: Algorithmic efficiency for edge computing  

## Files Created

- `state.json` - Progress tracking (auto-saves every 5min)
- `findings/[category]/` - Research results organized by topic
- `questions.json` - Question queue (auto-updates)

## Controls

**Stop**: Press `Ctrl+C` (saves state gracefully)  
**Resume**: Run `python research_agent.py` again  
**Monitor**: Watch console for real-time progress  

## Where to Find Results

```
research/
  findings/
    technology/     ← Q1 results here
    ethics/         ← Q2 results here  
    mathematics/    ← Q3 results here
    science/
    engineering/
    arts/
    sustainability/
    open_source/
```

## Expected Output

```
🌙 Noctem Research Agent Starting
============================================================

Target: 100 questions
Progress: 0 completed
Remaining: 100

🔍 Researching: What are the latest breakthroughs...
   Category: Technology
✓ Research completed (4523 chars)
📝 Saved finding: findings\technology\20260209_070930_q001.md

✅ Question 1/100 completed
💾 State saved (1/100 questions)
```

## Troubleshooting

**"Warp CLI not found"** → Install from https://www.warp.dev/  
**"Credits exhausted"** → Wait for Warp credits to refresh  
**Need to reset?** → Delete `state.json` (loses progress)  

## Full Documentation

See `README.md` for complete details, configuration options, and advanced usage.

---

**Ready to start?** Just run:
```powershell
python research_agent.py
```
