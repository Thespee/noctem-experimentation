#!/usr/bin/env python3
"""
Noctem Birth Process - Entry Point

Run this on first boot to automatically configure the system.

Usage:
    python3 birth/run.py [--signal-phone PHONE] [--resume] [--stage STAGE]

Options:
    --signal-phone  Phone number for Signal notifications (e.g., +15551234567)
    --resume        Resume from last checkpoint (default behavior)
    --stage         Start from a specific stage
    --no-signal     Run without Signal notifications (console only)
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Setup logging
LOG_PATH = Path(__file__).parent.parent / "logs" / "birth.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("noctem.birth")


def run_birth(
    signal_phone: str = None,
    resume: bool = True,
    start_stage: str = None,
    no_signal: bool = False
) -> bool:
    """
    Run the birth process.
    
    Args:
        signal_phone: Phone number for Signal notifications
        resume: Whether to resume from last checkpoint
        start_stage: Specific stage to start from
        no_signal: Disable Signal notifications
    
    Returns:
        True if birth completed successfully
    """
    from .state import init_birth_state, save_state, clear_state, BirthStage
    from .notify import configure, notify_progress, notify_error, notify_complete
    from .stages import STAGES, StageResult
    
    print("""
    ╔═══════════════════════════════════════════╗
    ║          🌙 Noctem Birth Process          ║
    ╠═══════════════════════════════════════════╣
    ║  Autonomous first-time setup beginning... ║
    ╚═══════════════════════════════════════════╝
    """)
    
    # Initialize state
    state = init_birth_state(resume=resume)
    
    # Configure Signal notifications
    if signal_phone:
        state.config["signal_phone"] = signal_phone
        configure(signal_phone)
    elif not no_signal and state.config.get("signal_phone"):
        configure(state.config["signal_phone"])
    
    # Check if already complete
    if state.is_complete():
        logger.info("Birth already complete")
        print("✓ Birth already complete. Noctem is ready!")
        return True
    
    # Notify start
    if state.progress_percent > 0:
        notify_progress("RESUME", f"Resuming from {state.progress_percent}%")
    else:
        notify_progress("START", "Birth process starting...")
    
    # Find starting stage
    start_idx = 0
    if start_stage:
        for i, stage_cls in enumerate(STAGES):
            if stage_cls.name == start_stage:
                start_idx = i
                break
    
    # Run stages
    for stage_cls in STAGES[start_idx:]:
        # Check if stage already complete
        if stage_cls.birth_stage.name in state.completed_stages:
            logger.info(f"Skipping completed stage: {stage_cls.name}")
            continue
        
        # Update state
        state.stage = stage_cls.birth_stage
        state.current_task = stage_cls.description
        save_state(state)
        
        # Create and execute stage
        stage = stage_cls(state)
        logger.info(f"Running stage: {stage.name}")
        
        output = stage.execute()
        
        if output.result == StageResult.SUCCESS:
            state.mark_stage_complete(stage_cls.birth_stage)
            save_state(state)
            logger.info(f"Stage {stage.name} complete")
            
        elif output.result == StageResult.SKIPPED:
            state.mark_stage_complete(stage_cls.birth_stage)
            save_state(state)
            logger.info(f"Stage {stage.name} skipped")
            
        elif output.result == StageResult.FAILED:
            state.add_error(stage_cls.birth_stage, output.error or "Unknown error")
            save_state(state)
            logger.error(f"Stage {stage.name} failed: {output.error}")
            
            # Wait for help or timeout
            if not no_signal:
                print(f"\n❌ Stage {stage.name} failed: {output.error}")
                print("Waiting for remote assistance...")
                print("Send /umb commands via Signal, or Ctrl+C to abort.\n")
                
                # Wait loop - check for state changes from umbilical commands
                try:
                    wait_start = time.time()
                    while time.time() - wait_start < 3600:  # 1 hour max
                        time.sleep(10)
                        
                        # Reload state to check for changes
                        state = init_birth_state(resume=True)
                        
                        if state.stage != BirthStage.ERROR:
                            # State changed, retry or continue
                            logger.info("State changed, resuming...")
                            break
                    else:
                        logger.error("Birth timed out waiting for assistance")
                        return False
                        
                except KeyboardInterrupt:
                    logger.info("Birth aborted by user")
                    print("\n🛑 Birth aborted.")
                    return False
            else:
                return False
    
    # All stages complete
    state.stage = BirthStage.COMPLETE
    save_state(state)
    
    notify_complete()
    
    print("""
    ╔═══════════════════════════════════════════╗
    ║       🌙 Noctem Birth Complete! 🌙        ║
    ╠═══════════════════════════════════════════╣
    ║  ✓ All systems configured                 ║
    ║  ✓ Auto-start enabled                     ║
    ║  ✓ Ready to receive messages              ║
    ╚═══════════════════════════════════════════╝
    
    Start Noctem with:  python3 main.py
    Or reboot to auto-start.
    """)
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Noctem Birth Process - First-time setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--signal-phone",
        help="Phone number for Signal notifications (e.g., +15551234567)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from last checkpoint (default)"
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Start fresh, ignoring any previous progress"
    )
    parser.add_argument(
        "--stage",
        help="Start from a specific stage name"
    )
    parser.add_argument(
        "--no-signal",
        action="store_true",
        help="Disable Signal notifications"
    )
    parser.add_argument(
        "--list-stages",
        action="store_true",
        help="List all stages and exit"
    )
    
    args = parser.parse_args()
    
    if args.list_stages:
        from .stages import STAGES
        print("Birth stages:")
        for i, stage in enumerate(STAGES, 1):
            print(f"  {i:2}. {stage.name:15} - {stage.description}")
        return 0
    
    if args.fresh:
        from .state import clear_state
        clear_state()
        print("Cleared previous birth state.")
    
    success = run_birth(
        signal_phone=args.signal_phone,
        resume=not args.fresh,
        start_stage=args.stage,
        no_signal=args.no_signal
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
