#!/usr/bin/env python3
"""
Birth Stage: Email Configuration

Configures email using pre-provisioned credentials from:
1. Environment variables (preferred)
2. data/email_config.json (for Option A pre-provisioning)

This stage verifies email connectivity but does NOT prompt for credentials.
Credentials should be provisioned before birth.
"""

import json
import os
from pathlib import Path
from typing import Optional

from .base import Stage, StageOutput, StageResult
from ..state import BirthStage

# Pre-provisioned config location
EMAIL_CONFIG_FILE = Path(__file__).parent.parent.parent / "data" / "email_config.json"


class EmailConfigStage(Stage):
    """Configure email for daily reports and notifications."""
    
    name = "email"
    description = "Configure email (Fastmail)"
    birth_stage = BirthStage.CONFIG_SIGNAL  # Reusing stage slot for now
    
    def check_preconditions(self) -> tuple[bool, str]:
        """Check if email credentials are available."""
        # Check environment variables
        if os.environ.get("NOCTEM_EMAIL_USER"):
            return True, "Email credentials found in environment"
        
        # Check pre-provisioned config file
        if EMAIL_CONFIG_FILE.exists():
            return True, "Email config file found"
        
        return False, "No email credentials found. Provision via env vars or data/email_config.json"
    
    def execute(self) -> StageOutput:
        """Configure email credentials and test connection."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        
        from utils.vault import init_vault, set_credential, get_credential
        from skills.email_send import test_smtp_connection
        from skills.email_fetch import test_imap_connection
        
        self.notify("Configuring email...")
        
        # Initialize vault
        init_vault()
        
        # Load credentials from pre-provisioned config if not in env
        if not os.environ.get("NOCTEM_EMAIL_USER") and EMAIL_CONFIG_FILE.exists():
            self.log("Loading credentials from config file")
            try:
                config = json.loads(EMAIL_CONFIG_FILE.read_text())
                
                # Store in vault
                for key, value in config.items():
                    if key.startswith("email_") and value:
                        set_credential(key, value)
                        self.log(f"Set {key}")
                
                self.notify("Credentials loaded from config file")
                
            except Exception as e:
                return StageOutput(
                    result=StageResult.FAILED,
                    error=f"Failed to load config: {e}"
                )
        
        # Verify we have minimum required credentials
        user = get_credential("email_user")
        password = get_credential("email_password")
        
        if not user or not password:
            return StageOutput(
                result=StageResult.FAILED,
                error="Email credentials incomplete. Need email_user and email_password."
            )
        
        # Test SMTP connection
        self.notify("Testing SMTP connection...")
        smtp_ok, smtp_msg = test_smtp_connection()
        
        if not smtp_ok:
            return StageOutput(
                result=StageResult.FAILED,
                error=f"SMTP test failed: {smtp_msg}"
            )
        
        self.log(f"SMTP OK: {smtp_msg}")
        
        # Test IMAP connection
        self.notify("Testing IMAP connection...")
        imap_ok, imap_msg = test_imap_connection()
        
        if not imap_ok:
            # IMAP is optional - warn but continue
            self.log(f"IMAP warning: {imap_msg}")
            self.notify(f"⚠️ IMAP: {imap_msg}")
        else:
            self.log(f"IMAP OK: {imap_msg}")
        
        # Send test email notification
        recipient = get_credential("email_recipient") or user
        self.notify(f"✓ Email configured: {user} → {recipient}")
        
        return StageOutput(
            result=StageResult.SUCCESS,
            message=f"Email configured: {user}"
        )


# Export for stage discovery
__all__ = ["EmailConfigStage"]
