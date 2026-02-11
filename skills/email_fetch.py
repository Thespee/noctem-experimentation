#!/usr/bin/env python3
"""
Skill: email_fetch
Fetches emails from IMAP server.

Parameters:
  - folder (str, optional): Mail folder (default: INBOX)
  - limit (int, optional): Max emails to fetch (default: 10)
  - unread_only (bool, optional): Only fetch unread (default: true)
  - since_hours (int, optional): Only fetch from last N hours (default: 24)
  - mark_read (bool, optional): Mark fetched emails as read (default: false)

Returns:
  - success: {"emails": [...], "count": N}
  - error: {"error": "..."}
"""

import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import sys
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.base import Skill, SkillResult, SkillContext, register_skill
from utils.vault import get_credential


def decode_mime_header(header: str) -> str:
    """Decode MIME encoded header to string."""
    if not header:
        return ""
    
    decoded_parts = []
    for part, encoding in decode_header(header):
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(encoding or 'utf-8', errors='replace'))
        else:
            decoded_parts.append(part)
    
    return ' '.join(decoded_parts)


def extract_email_body(msg: email.message.Message) -> Tuple[str, bool]:
    """
    Extract body from email message.
    Returns (body_text, is_html).
    """
    body = ""
    is_html = False
    
    if msg.is_multipart():
        # Walk through parts, prefer plain text
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            # Skip attachments
            if "attachment" in content_disposition:
                continue
            
            if content_type == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='replace')
                    is_html = False
                    break  # Prefer plain text
                except:
                    pass
            elif content_type == "text/html" and not body:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='replace')
                    is_html = True
                except:
                    pass
    else:
        # Single part message
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                body = payload.decode(charset, errors='replace')
                is_html = msg.get_content_type() == "text/html"
        except:
            pass
    
    # Clean up HTML if needed (basic strip)
    if is_html:
        # Remove HTML tags for preview
        body = re.sub(r'<style[^>]*>.*?</style>', '', body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r'<[^>]+>', ' ', body)
        body = re.sub(r'\s+', ' ', body)
    
    return body.strip(), is_html


def parse_email_address(addr_str: str) -> Dict[str, str]:
    """Parse email address into name and address."""
    if not addr_str:
        return {"name": "", "address": ""}
    
    # Decode if MIME encoded
    addr_str = decode_mime_header(addr_str)
    
    # Parse
    match = re.match(r'^(.*?)\s*<([^>]+)>$', addr_str.strip())
    if match:
        return {"name": match.group(1).strip(' "\''), "address": match.group(2)}
    
    # Just an email address
    return {"name": "", "address": addr_str.strip()}


def connect_imap() -> Tuple[Optional[imaplib.IMAP4_SSL], str]:
    """
    Connect to IMAP server.
    Returns (connection, error_message).
    """
    username = get_credential("email_user")
    password = get_credential("email_password")
    server = get_credential("email_imap_server") or "imap.fastmail.com"
    port = int(get_credential("email_imap_port") or "993")
    
    if not username or not password:
        return None, "Email not configured. Run: python utils/vault.py"
    
    try:
        imap = imaplib.IMAP4_SSL(server, port)
        imap.login(username, password)
        return imap, ""
    except imaplib.IMAP4.error as e:
        return None, f"IMAP authentication failed: {e}"
    except Exception as e:
        return None, f"IMAP connection failed: {e}"


def fetch_emails(
    folder: str = "INBOX",
    limit: int = 10,
    unread_only: bool = True,
    since_hours: int = 24,
    mark_read: bool = False
) -> Tuple[List[Dict], str]:
    """
    Fetch emails from IMAP server.
    Returns (emails_list, error_message).
    """
    imap, error = connect_imap()
    if error:
        return [], error
    
    emails = []
    
    try:
        # Select folder
        status, data = imap.select(folder, readonly=not mark_read)
        if status != "OK":
            return [], f"Cannot select folder: {folder}"
        
        # Build search criteria
        criteria = []
        
        if unread_only:
            criteria.append("UNSEEN")
        
        if since_hours > 0:
            since_date = datetime.now() - timedelta(hours=since_hours)
            # IMAP date format: DD-Mon-YYYY
            date_str = since_date.strftime("%d-%b-%Y")
            criteria.append(f'SINCE {date_str}')
        
        search_criteria = " ".join(criteria) if criteria else "ALL"
        
        # Search for messages
        status, data = imap.search(None, search_criteria)
        if status != "OK":
            return [], "Search failed"
        
        msg_ids = data[0].split()
        
        # Get the most recent N messages
        msg_ids = msg_ids[-limit:] if len(msg_ids) > limit else msg_ids
        
        # Fetch each message
        for msg_id in reversed(msg_ids):  # Newest first
            try:
                # Fetch message
                status, msg_data = imap.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data[0]:
                    continue
                
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Parse headers
                subject = decode_mime_header(msg.get("Subject", "(no subject)"))
                from_addr = parse_email_address(msg.get("From", ""))
                to_addr = parse_email_address(msg.get("To", ""))
                date_str = msg.get("Date", "")
                
                # Parse date
                try:
                    date = parsedate_to_datetime(date_str) if date_str else None
                except:
                    date = None
                
                # Extract body
                body, is_html = extract_email_body(msg)
                
                # Count attachments
                attachments = []
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_disposition() == "attachment":
                            filename = part.get_filename()
                            if filename:
                                attachments.append(decode_mime_header(filename))
                
                email_data = {
                    "id": msg_id.decode(),
                    "subject": subject,
                    "from": from_addr,
                    "to": to_addr,
                    "date": date.isoformat() if date else None,
                    "body_preview": body[:500] + "..." if len(body) > 500 else body,
                    "body_length": len(body),
                    "is_html": is_html,
                    "attachments": attachments,
                    "has_attachments": len(attachments) > 0,
                }
                
                emails.append(email_data)
                
                # Mark as read if requested
                if mark_read:
                    imap.store(msg_id, '+FLAGS', '\\Seen')
                    
            except Exception as e:
                # Skip problematic emails
                continue
        
        return emails, ""
        
    except Exception as e:
        return [], f"Fetch failed: {e}"
    finally:
        try:
            imap.logout()
        except:
            pass


def test_imap_connection() -> Tuple[bool, str]:
    """Test IMAP connection without fetching emails."""
    imap, error = connect_imap()
    if error:
        return False, error
    
    try:
        # Try to select inbox
        status, data = imap.select("INBOX", readonly=True)
        if status == "OK":
            count = int(data[0])
            imap.logout()
            return True, f"IMAP connection OK. INBOX has {count} messages."
        return False, "Cannot access INBOX"
    except Exception as e:
        return False, f"IMAP test failed: {e}"


@register_skill
class EmailFetchSkill(Skill):
    """Fetch emails from IMAP server."""
    
    name = "email_fetch"
    description = "Fetch emails from IMAP inbox"
    parameters = {
        "folder": "Mail folder (optional, default: INBOX)",
        "limit": "Max emails to fetch (optional, default: 10)",
        "unread_only": "Only fetch unread (optional, default: true)",
        "since_hours": "Only fetch from last N hours (optional, default: 24)",
        "mark_read": "Mark fetched emails as read (optional, default: false)",
    }
    
    def run(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        folder = params.get("folder", "INBOX")
        limit = params.get("limit", 10)
        unread_only = params.get("unread_only", True)
        since_hours = params.get("since_hours", 24)
        mark_read = params.get("mark_read", False)
        
        emails, error = fetch_emails(
            folder=folder,
            limit=limit,
            unread_only=unread_only,
            since_hours=since_hours,
            mark_read=mark_read
        )
        
        if error:
            return SkillResult(
                success=False,
                output="",
                error=error
            )
        
        # Format output
        if not emails:
            output = "No emails found matching criteria"
        else:
            lines = [f"Found {len(emails)} email(s):\n"]
            for e in emails:
                lines.append(f"• {e['subject']}")
                lines.append(f"  From: {e['from']['address']}")
                lines.append(f"  Date: {e['date']}")
                if e['has_attachments']:
                    lines.append(f"  📎 {len(e['attachments'])} attachment(s)")
                lines.append("")
            output = "\n".join(lines)
        
        return SkillResult(
            success=True,
            output=output,
            data={"emails": emails, "count": len(emails)}
        )


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Noctem Email Fetch")
    parser.add_argument("--test", action="store_true", help="Test IMAP connection")
    parser.add_argument("--fetch", action="store_true", help="Fetch recent emails")
    parser.add_argument("--limit", type=int, default=5, help="Max emails (default: 5)")
    parser.add_argument("--all", action="store_true", help="Fetch all (not just unread)")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back (default: 24)")
    args = parser.parse_args()
    
    if args.test:
        print("Testing IMAP connection...")
        success, msg = test_imap_connection()
        print(f"{'✓' if success else '✗'} {msg}")
        sys.exit(0 if success else 1)
    
    if args.fetch:
        print(f"Fetching up to {args.limit} emails from last {args.hours} hours...")
        emails, error = fetch_emails(
            limit=args.limit,
            unread_only=not args.all,
            since_hours=args.hours
        )
        
        if error:
            print(f"✗ {error}")
            sys.exit(1)
        
        if not emails:
            print("No emails found")
        else:
            print(f"\nFound {len(emails)} email(s):\n")
            for e in emails:
                print(f"📧 {e['subject']}")
                print(f"   From: {e['from']['name'] or e['from']['address']}")
                print(f"   Date: {e['date']}")
                print(f"   Preview: {e['body_preview'][:100]}...")
                print()
        
        sys.exit(0)
    
    parser.print_help()
