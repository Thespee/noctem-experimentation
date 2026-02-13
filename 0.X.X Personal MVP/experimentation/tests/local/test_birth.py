#!/usr/bin/env python3
"""
Tests for birth process components.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from birth.state import (
    BirthStage, BirthState, STAGE_ORDER,
    save_state, load_state, clear_state,
    init_birth_state, get_birth_state
)
from birth.stages.base import Stage, StageOutput, StageResult


class TestBirthState(unittest.TestCase):
    """Tests for birth state machine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        # Patch STATE_FILE to use temp directory
        self.state_file = Path(self.temp_dir) / ".birth_state.json"
        
    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_birth_state_creation(self):
        """Test creating a new birth state."""
        state = BirthState()
        
        self.assertEqual(state.stage, BirthStage.INIT)
        self.assertEqual(state.progress_percent, 0)
        self.assertEqual(len(state.completed_stages), 0)
        self.assertEqual(len(state.errors), 0)
        self.assertFalse(state.umbilical_active)
    
    def test_mark_stage_complete(self):
        """Test marking stages as complete."""
        state = BirthState()
        
        state.mark_stage_complete(BirthStage.DETECT)
        self.assertIn("DETECT", state.completed_stages)
        self.assertEqual(state.progress_percent, 10)  # 1/10 stages
        
        state.mark_stage_complete(BirthStage.NETWORK)
        self.assertIn("NETWORK", state.completed_stages)
        self.assertEqual(state.progress_percent, 20)  # 2/10 stages
    
    def test_add_error(self):
        """Test adding errors."""
        state = BirthState()
        
        state.add_error(BirthStage.NETWORK, "Connection failed", recoverable=True)
        
        self.assertEqual(len(state.errors), 1)
        self.assertEqual(state.errors[0]["stage"], "NETWORK")
        self.assertEqual(state.errors[0]["error"], "Connection failed")
        # Stage shouldn't change for recoverable errors
        self.assertNotEqual(state.stage, BirthStage.ERROR)
        
        # Non-recoverable error should set ERROR state
        state.add_error(BirthStage.SYSTEM_DEPS, "Critical failure", recoverable=False)
        self.assertEqual(state.stage, BirthStage.ERROR)
    
    def test_get_next_stage(self):
        """Test getting next stage."""
        state = BirthState()
        
        self.assertEqual(state.get_next_stage(), BirthStage.DETECT)
        
        state.mark_stage_complete(BirthStage.DETECT)
        self.assertEqual(state.get_next_stage(), BirthStage.NETWORK)
        
        # Complete all stages
        for stage in STAGE_ORDER:
            state.mark_stage_complete(stage)
        
        self.assertIsNone(state.get_next_stage())
    
    def test_is_complete(self):
        """Test completion check."""
        state = BirthState()
        
        self.assertFalse(state.is_complete())
        
        for stage in STAGE_ORDER:
            state.mark_stage_complete(stage)
        
        self.assertTrue(state.is_complete())
    
    def test_serialization(self):
        """Test state serialization to/from dict."""
        state = BirthState()
        state.mark_stage_complete(BirthStage.DETECT)
        state.config["test_key"] = "test_value"
        
        # Convert to dict
        data = state.to_dict()
        
        self.assertEqual(data["stage"], "INIT")
        self.assertIn("DETECT", data["completed_stages"])
        self.assertEqual(data["config"]["test_key"], "test_value")
        
        # Convert back
        restored = BirthState.from_dict(data)
        
        self.assertEqual(restored.stage, state.stage)
        self.assertEqual(restored.completed_stages, state.completed_stages)
        self.assertEqual(restored.config["test_key"], "test_value")


class TestStageBase(unittest.TestCase):
    """Tests for base stage class."""
    
    def test_stage_output_creation(self):
        """Test creating stage output."""
        output = StageOutput(
            result=StageResult.SUCCESS,
            message="Test complete"
        )
        
        self.assertEqual(output.result, StageResult.SUCCESS)
        self.assertEqual(output.message, "Test complete")
        self.assertIsNone(output.error)
    
    def test_stage_output_with_error(self):
        """Test stage output with error."""
        output = StageOutput(
            result=StageResult.FAILED,
            message="Test failed",
            error="Connection refused"
        )
        
        self.assertEqual(output.result, StageResult.FAILED)
        self.assertEqual(output.error, "Connection refused")


class TestUmbilical(unittest.TestCase):
    """Tests for umbilical protocol."""
    
    def test_handle_umb_help(self):
        """Test /umb help command."""
        from birth.umbilical import handle_umb_command
        
        result = handle_umb_command("/umb")
        
        self.assertIn("connect", result)
        self.assertIn("status", result)
        self.assertIn("close", result)
    
    def test_handle_umb_status_no_connection(self):
        """Test /umb status with no active connection."""
        from birth.umbilical import handle_umb_command
        
        result = handle_umb_command("/umb status")
        
        self.assertIn("No active", result.lower())
    
    def test_handle_umb_connect_missing_relay(self):
        """Test /umb connect without relay host."""
        from birth.umbilical import handle_umb_command
        
        result = handle_umb_command("/umb connect")
        
        self.assertIn("Usage", result)


class TestNotify(unittest.TestCase):
    """Tests for notification module."""
    
    def test_configure(self):
        """Test configuring Signal numbers."""
        from birth.notify import configure, _signal_number, _recipient_number
        
        configure("+15551234567", "+15559876543")
        
        from birth import notify
        self.assertEqual(notify._signal_number, "+15551234567")
        self.assertEqual(notify._recipient_number, "+15559876543")
    
    @patch('birth.notify._send_via_daemon')
    @patch('birth.notify._send_via_cli')
    def test_send_signal_truncation(self, mock_cli, mock_daemon):
        """Test message truncation for long messages."""
        from birth.notify import send_signal, configure
        
        configure("+15551234567")
        mock_daemon.return_value = True
        
        # Send a very long message
        long_message = "x" * 3000
        send_signal(long_message)
        
        # Check it was truncated
        call_args = mock_daemon.call_args[0]
        self.assertLessEqual(len(call_args[0]), 2000)
        self.assertTrue(call_args[0].endswith("..."))


class TestStageImports(unittest.TestCase):
    """Test that all stages can be imported."""
    
    def test_import_all_stages(self):
        """Test importing all stage modules."""
        from birth.stages import (
            DetectStage,
            NetworkStage,
            SystemDepsStage,
            PythonDepsStage,
            OllamaStage,
            SignalCliStage,
            NoctemInitStage,
            TestSkillsStage,
            AutostartStage,
            CleanupStage,
        )
        
        # Verify they're all Stage subclasses
        from birth.stages.base import Stage
        
        stages = [
            DetectStage,
            NetworkStage,
            SystemDepsStage,
            PythonDepsStage,
            OllamaStage,
            SignalCliStage,
            NoctemInitStage,
            TestSkillsStage,
            AutostartStage,
            CleanupStage,
        ]
        
        for stage_cls in stages:
            self.assertTrue(issubclass(stage_cls, Stage))
            self.assertTrue(hasattr(stage_cls, 'name'))
            self.assertTrue(hasattr(stage_cls, 'description'))


class TestRunModule(unittest.TestCase):
    """Tests for birth/run.py module."""
    
    def test_list_stages(self):
        """Test --list-stages option."""
        from birth.stages import STAGES
        
        self.assertEqual(len(STAGES), 10)
        
        # Verify stage order
        expected_order = [
            "detect", "network", "system_deps", "python_deps", "ollama",
            "signal_cli", "noctem_init", "test_skills", "autostart", "cleanup"
        ]
        
        for i, stage_cls in enumerate(STAGES):
            self.assertEqual(stage_cls.name, expected_order[i])


def run_tests():
    """Run all birth tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestBirthState))
    suite.addTests(loader.loadTestsFromTestCase(TestStageBase))
    suite.addTests(loader.loadTestsFromTestCase(TestUmbilical))
    suite.addTests(loader.loadTestsFromTestCase(TestNotify))
    suite.addTests(loader.loadTestsFromTestCase(TestStageImports))
    suite.addTests(loader.loadTestsFromTestCase(TestRunModule))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return len(result.failures) + len(result.errors) == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
