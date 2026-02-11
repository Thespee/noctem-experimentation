#!/usr/bin/env python3
"""
Skill: email_send
Sends emails via SMTP.

Parameters:
  - to (str, required): Recipient email address
  - subject (str, required): Email subject
  - body (str, required): Email body (plain text)
  - html (bool, optional): Send as HTML (default: false)

Returns:
  - success: {"status": "sent", "to": "...", "subject": "..."}
  - error: {"error": "..."}
"""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate
import sys
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.base import Skill, SkillResult, SkillContext, register_skill
from utils.vault import get_credential


def send_email_smtp(
    to: str,
    subject: str,
    body: str,
    html: bool = False,
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Send an email via SMTP.
    
    Returns (success, message).
    """
    # Get credentials from vault if not provided
    username = username or get_credential("email_user")
    password = password or get_credential("email_password")
    smtp_server = smtp_server or get_credential("email_smtp_server") or "smtp.fastmail.com"
    smtp_port = smtp_port or int(get_credential("email_smtp_port") or "587")
    from_name = get_credential("email_from_name") or "Noctem"
    
    if not username or not password:
        return False, "Email not configured. Run: python utils/vault.py"
    
    # Build message
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{username}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    
    if html:
        msg.set_content(body, subtype="html")
    else:
        msg.set_content(body)
    
    # Send
    try:
        context = ssl.create_default_context()
        
        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(username, password)
            server.send_message(msg)
        
        return True, f"Email sent to {to}"
        
    except smtplib.SMTPAuthenticationError as e:
        return False, f"SMTP authentication failed. Check app password. ({e})"
    except smtplib.SMTPRecipientsRefused as e:
        return False, f"Recipient rejected: {to}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except TimeoutError:
        return False, "Connection timed out"
    except Exception as e:
        return False, f"Send failed: {e}"


def test_smtp_connection() -> Tuple[bool, str]:
    """Test SMTP connection without sending."""
    username = get_credential("email_user")
    password = get_credential("email_password")
    smtp_server = get_credential("email_smtp_server") or "smtp.gmail.com"
    smtp_port = int(get_credential("email_smtp_port") or "587")
    
    if not username or not password:
        return False, "Email not configured"
    
    try:
        context = ssl.create_default_context()
        
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(username, password)
            server.noop()  # Just test the connection
        
        return True, f"SMTP connection OK ({smtp_server}:{smtp_port})"
        
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed - check app password"
    except Exception as e:
        return False, f"Connection failed: {e}"


@register_skill
class EmailSendSkill(Skill):
    """Send emails via SMTP."""
    
    name = "email_send"
    description = "Send an email via SMTP"
    parameters = {
        "to": "Recipient email address (required)",
        "subject": "Email subject (required)",
        "body": "Email body text (required)",
        "html": "Send as HTML (optional, default: false)",
    }
    
    def run(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        to = params.get("to")
        subject = params.get("subject")
        body = params.get("body")
        html = params.get("html", False)
        
        # Validation
        if not to or "@" not in to:
            return SkillResult(
                success=False,
                output="",
                error="Invalid recipient email address"
            )
        
        if not subject:
            return SkillResult(
                success=False,
                output="",
                error="Subject is required"
            )
        
        if not body:
            return SkillResult(
                success=False,
                output="",
                error="Body is required"
            )
        
        # Send
        success, message = send_email_smtp(to, subject, body, html)
        
        if success:
            return SkillResult(
                success=True,
                output=message,
                data={"to": to, "subject": subject, "status": "sent"}
            )
        else:
            return SkillResult(
                success=False,
                output="",
                error=message
            )


# Direct execution for testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Noctem Email Skill")
    parser.add_argument("--test", action="store_true", help="Test SMTP connection")
    parser.add_argument("--send", action="store_true", help="Send a test email")
    parser.add_argument("--to", help="Recipient for test email")
    args = parser.parse_args()
    
    if args.test:
        print("Testing SMTP connection...")
        success, msg = test_smtp_connection()
        print(f"{'✓' if success else '✗'} {msg}")
        sys.exit(0 if success else 1)
    
    if args.send:
        to = args.to or get_credential("email_recipient") or get_credential("email_user")
        if not to:
            print("No recipient specified. Use --to or configure email_recipient")
            sys.exit(1)
        
        print(f"Sending test email to {to}...")
        success, msg = send_email_smtp(
            to=to,
            subject="Noctem Test Email",
            body="This is a test email from Noctem.\n\nIf you received this, email is working!"
        )
        print(f"{'✓' if success else '✗'} {msg}")
        sys.exit(0 if success else 1)
    
    parser.print_help()
