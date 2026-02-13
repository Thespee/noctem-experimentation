#!/usr/bin/env python3
"""
Noctem Email Verification Script

Verifies that email is properly configured and working.
Run this after setting up credentials to confirm everything works.

Usage:
    python scripts/verify_email.py
    python scripts/verify_email.py --send-test
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_credentials():
    """Check if credentials are configured."""
    print("\n1. Checking credentials...")
    
    from utils.vault import get_vault, init_vault
    
    init_vault()
    vault = get_vault()
    status = vault.status()
    
    print(f"   Backend: {status['backend']}")
    print(f"   Has crypto: {status['has_crypto']}")
    
    required = ["email_user", "email_password"]
    optional = ["email_smtp_server", "email_imap_server", "email_recipient", "email_from_name"]
    
    all_ok = True
    for key in required:
        if vault.has(key):
            val = vault.get(key)
            # Mask password
            if "password" in key:
                val = val[:3] + "***" if val else None
            print(f"   ✓ {key}: {val}")
        else:
            print(f"   ✗ {key}: NOT SET (required)")
            all_ok = False
    
    for key in optional:
        if vault.has(key):
            val = vault.get(key)
            print(f"   ✓ {key}: {val}")
        else:
            print(f"   - {key}: not set (optional)")
    
    return all_ok


def check_smtp():
    """Test SMTP connection."""
    print("\n2. Testing SMTP connection...")
    
    from skills.email_send import test_smtp_connection
    
    success, msg = test_smtp_connection()
    
    if success:
        print(f"   ✓ {msg}")
    else:
        print(f"   ✗ {msg}")
    
    return success


def check_imap():
    """Test IMAP connection."""
    print("\n3. Testing IMAP connection...")
    
    from skills.email_fetch import test_imap_connection
    
    success, msg = test_imap_connection()
    
    if success:
        print(f"   ✓ {msg}")
    else:
        print(f"   ✗ {msg}")
    
    return success


def send_test_email():
    """Send a test email."""
    print("\n4. Sending test email...")
    
    from skills.email_send import send_email_smtp
    from utils.vault import get_credential
    import socket
    
    recipient = get_credential("email_recipient") or get_credential("email_user")
    hostname = socket.gethostname()
    
    success, msg = send_email_smtp(
        to=recipient,
        subject=f"🌙 Noctem Email Test - {hostname}",
        body=f"""This is a test email from Noctem.

If you received this, email is working correctly!

---
Sent from: {hostname}
Recipient: {recipient}
"""
    )
    
    if success:
        print(f"   ✓ Test email sent to {recipient}")
    else:
        print(f"   ✗ {msg}")
    
    return success


def check_daily_report():
    """Test daily report generation."""
    print("\n5. Testing daily report generation...")
    
    from skills.daily_report import generate_report
    
    try:
        report, stats = generate_report(period_hours=24)
        print(f"   ✓ Report generated ({stats['tasks_completed']} tasks, {stats['incidents_count']} incidents)")
        print(f"   Preview: {report[:100]}...")
        return True
    except Exception as e:
        print(f"   ✗ {e}")
        return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Verify Noctem email setup")
    parser.add_argument("--send-test", action="store_true", help="Send a test email")
    parser.add_argument("--full", action="store_true", help="Run all checks including test email")
    args = parser.parse_args()
    
    print("=" * 50)
    print("🌙 Noctem Email Verification")
    print("=" * 50)
    
    results = {}
    
    # Always check credentials
    results["credentials"] = check_credentials()
    
    if not results["credentials"]:
        print("\n❌ Credentials not configured!")
        print("   Run: python utils/vault.py")
        print("   Or create: data/email_config.json")
        return 1
    
    # Check SMTP
    results["smtp"] = check_smtp()
    
    # Check IMAP
    results["imap"] = check_imap()
    
    # Check report generation
    results["report"] = check_daily_report()
    
    # Send test email if requested
    if args.send_test or args.full:
        results["send"] = send_test_email()
    
    # Summary
    print("\n" + "=" * 50)
    print("Summary:")
    print("=" * 50)
    
    all_ok = True
    for name, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")
        if not ok and name not in ["imap"]:  # IMAP is optional
            all_ok = False
    
    if all_ok:
        print("\n✅ Email is properly configured!")
        if not args.send_test:
            print("   Run with --send-test to verify end-to-end")
    else:
        print("\n❌ Some checks failed. Review the output above.")
    
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
