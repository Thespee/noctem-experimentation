# Phase 4: Email Skills Implementation Guide

**Objective**: Implement email fetch, summarization, and management skills.

**Prerequisites**: 
- Phases 1-3 complete
- IMAP-enabled email account (Gmail, ProtonMail, Fastmail, etc.)
- App password or OAuth token for email access

---

## Overview

Email skills enable Noctem to:
1. Fetch and read emails via IMAP
2. Summarize newsletters and long emails
3. Queue actions for approval (reply, archive, etc.)
4. Send emails via SMTP (with approval)
5. Manage recurring summaries (daily digest)

---

## Security Model

**Critical**: Email access requires careful credential handling.

```
┌─────────────────────────────────────────────────────────────┐
│                    CREDENTIAL FLOW                          │
├─────────────────────────────────────────────────────────────┤
│  1. Credentials stored in encrypted vault (not plaintext)   │
│  2. Loaded into memory only when needed                     │
│  3. Never logged or included in error messages              │
│  4. App passwords preferred over main password              │
│  5. OAuth preferred where available                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 1: Create Credential Vault

### 1.1 Create `utils/vault.py`

```python
"""
Encrypted credential vault using system keyring or encrypted file.
"""
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
import base64

# Try to use system keyring first, fall back to encrypted file
try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

SERVICE_NAME = "noctem"
VAULT_FILE = Path(__file__).parent.parent / ".vault.enc"
SALT_FILE = Path(__file__).parent.parent / ".vault.salt"

def _get_key_from_password(password: str, salt: bytes) -> bytes:
    """Derive encryption key from password."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

class CredentialVault:
    """Secure credential storage."""
    
    def __init__(self, master_password: Optional[str] = None):
        self.master_password = master_password
        self._cache: Dict[str, str] = {}
        
        if HAS_KEYRING:
            self.backend = "keyring"
        elif HAS_CRYPTO and master_password:
            self.backend = "encrypted_file"
            self._load_encrypted_file()
        else:
            raise RuntimeError(
                "No secure storage available. Install 'keyring' or "
                "'cryptography' package and provide master password."
            )
    
    def _load_encrypted_file(self):
        """Load credentials from encrypted file."""
        if not VAULT_FILE.exists():
            return
        
        if not SALT_FILE.exists():
            return
        
        salt = SALT_FILE.read_bytes()
        key = _get_key_from_password(self.master_password, salt)
        fernet = Fernet(key)
        
        try:
            encrypted = VAULT_FILE.read_bytes()
            decrypted = fernet.decrypt(encrypted)
            self._cache = json.loads(decrypted.decode())
        except Exception:
            raise RuntimeError("Failed to decrypt vault. Wrong password?")
    
    def _save_encrypted_file(self):
        """Save credentials to encrypted file."""
        if self.backend != "encrypted_file":
            return
        
        # Generate salt if needed
        if not SALT_FILE.exists():
            salt = os.urandom(16)
            SALT_FILE.write_bytes(salt)
        else:
            salt = SALT_FILE.read_bytes()
        
        key = _get_key_from_password(self.master_password, salt)
        fernet = Fernet(key)
        
        data = json.dumps(self._cache).encode()
        encrypted = fernet.encrypt(data)
        VAULT_FILE.write_bytes(encrypted)
    
    def get(self, key: str) -> Optional[str]:
        """Get a credential."""
        if self.backend == "keyring":
            return keyring.get_password(SERVICE_NAME, key)
        else:
            return self._cache.get(key)
    
    def set(self, key: str, value: str):
        """Set a credential."""
        if self.backend == "keyring":
            keyring.set_password(SERVICE_NAME, key, value)
        else:
            self._cache[key] = value
            self._save_encrypted_file()
    
    def delete(self, key: str):
        """Delete a credential."""
        if self.backend == "keyring":
            try:
                keyring.delete_password(SERVICE_NAME, key)
            except keyring.errors.PasswordDeleteError:
                pass
        else:
            self._cache.pop(key, None)
            self._save_encrypted_file()
    
    def list_keys(self) -> list:
        """List all stored credential keys (not values!)."""
        if self.backend == "keyring":
            # Keyring doesn't support listing, return known keys
            return ["email_user", "email_password", "email_server", "smtp_server"]
        else:
            return list(self._cache.keys())


# Singleton vault instance
_vault: Optional[CredentialVault] = None

def init_vault(master_password: Optional[str] = None) -> CredentialVault:
    """Initialize the credential vault."""
    global _vault
    _vault = CredentialVault(master_password)
    return _vault

def get_vault() -> Optional[CredentialVault]:
    """Get the vault instance."""
    return _vault

def get_credential(key: str) -> Optional[str]:
    """Convenience function to get a credential."""
    if _vault is None:
        raise RuntimeError("Vault not initialized. Call init_vault() first.")
    return _vault.get(key)

def set_credential(key: str, value: str):
    """Convenience function to set a credential."""
    if _vault is None:
        raise RuntimeError("Vault not initialized. Call init_vault() first.")
    _vault.set(key, value)
```

---

## Step 2: Create Email Connection Manager

### 2.1 Create `skills/email_connection.py`

```python
"""
Email connection manager for IMAP and SMTP.
"""
import imaplib
import smtplib
import ssl
from email import message_from_bytes
from email.message import EmailMessage
from typing import Optional, List, Tuple
from dataclasses import dataclass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.vault import get_credential

@dataclass
class EmailConfig:
    """Email server configuration."""
    imap_server: str
    imap_port: int = 993
    smtp_server: str = None
    smtp_port: int = 587
    use_ssl: bool = True
    
    @classmethod
    def gmail(cls) -> 'EmailConfig':
        return cls(
            imap_server="imap.gmail.com",
            smtp_server="smtp.gmail.com",
            smtp_port=587
        )
    
    @classmethod
    def protonmail(cls) -> 'EmailConfig':
        # Requires ProtonMail Bridge
        return cls(
            imap_server="127.0.0.1",
            imap_port=1143,
            smtp_server="127.0.0.1",
            smtp_port=1025,
            use_ssl=False
        )
    
    @classmethod
    def fastmail(cls) -> 'EmailConfig':
        return cls(
            imap_server="imap.fastmail.com",
            smtp_server="smtp.fastmail.com"
        )

class EmailConnection:
    """Manages IMAP connection."""
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self.imap: Optional[imaplib.IMAP4_SSL] = None
        self._connected = False
    
    def connect(self) -> Tuple[bool, str]:
        """Connect to IMAP server."""
        username = get_credential("email_user")
        password = get_credential("email_password")
        
        if not username or not password:
            return False, "Email credentials not configured"
        
        try:
            if self.config.use_ssl:
                self.imap = imaplib.IMAP4_SSL(
                    self.config.imap_server,
                    self.config.imap_port
                )
            else:
                self.imap = imaplib.IMAP4(
                    self.config.imap_server,
                    self.config.imap_port
                )
            
            self.imap.login(username, password)
            self._connected = True
            return True, "Connected"
            
        except imaplib.IMAP4.error as e:
            return False, f"IMAP error: {e}"
        except Exception as e:
            return False, f"Connection error: {e}"
    
    def disconnect(self):
        """Disconnect from IMAP server."""
        if self.imap and self._connected:
            try:
                self.imap.logout()
            except:
                pass
            self._connected = False
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, *args):
        self.disconnect()
    
    def select_folder(self, folder: str = "INBOX") -> Tuple[bool, int]:
        """Select a mail folder. Returns (success, message_count)."""
        if not self._connected:
            return False, 0
        
        try:
            status, data = self.imap.select(folder)
            if status == "OK":
                count = int(data[0])
                return True, count
            return False, 0
        except Exception as e:
            return False, 0
    
    def search(self, criteria: str = "ALL") -> List[bytes]:
        """Search for messages. Returns list of message IDs."""
        if not self._connected:
            return []
        
        try:
            status, data = self.imap.search(None, criteria)
            if status == "OK":
                return data[0].split()
            return []
        except:
            return []
    
    def fetch_message(self, msg_id: bytes) -> Optional[EmailMessage]:
        """Fetch a single message by ID."""
        if not self._connected:
            return None
        
        try:
            status, data = self.imap.fetch(msg_id, "(RFC822)")
            if status == "OK" and data[0]:
                raw_email = data[0][1]
                return message_from_bytes(raw_email)
            return None
        except:
            return None
    
    def fetch_headers(self, msg_id: bytes) -> Optional[dict]:
        """Fetch just headers for a message."""
        if not self._connected:
            return None
        
        try:
            status, data = self.imap.fetch(msg_id, "(BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
            if status == "OK" and data[0]:
                headers = data[0][1].decode('utf-8', errors='replace')
                result = {}
                for line in headers.strip().split('\r\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        result[key.strip().lower()] = value.strip()
                return result
            return None
        except:
            return None


def send_email(
    to: str,
    subject: str,
    body: str,
    config: EmailConfig,
    html: bool = False
) -> Tuple[bool, str]:
    """Send an email via SMTP."""
    username = get_credential("email_user")
    password = get_credential("email_password")
    
    if not username or not password:
        return False, "Email credentials not configured"
    
    if not config.smtp_server:
        return False, "SMTP server not configured"
    
    msg = EmailMessage()
    msg['From'] = username
    msg['To'] = to
    msg['Subject'] = subject
    
    if html:
        msg.set_content(body, subtype='html')
    else:
        msg.set_content(body)
    
    try:
        context = ssl.create_default_context()
        
        with smtplib.SMTP(config.smtp_server, config.smtp_port) as server:
            server.starttls(context=context)
            server.login(username, password)
            server.send_message(msg)
        
        return True, "Email sent"
        
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed"
    except Exception as e:
        return False, f"SMTP error: {e}"
```

---

## Step 3: Implement Email Fetch Skill

### 3.1 Create `skills/email_fetch.py`

```python
"""
Skill: email_fetch
Fetches emails from IMAP server.

Parameters:
  - folder (str, optional): Mail folder (default: INBOX)
  - limit (int, optional): Max emails to fetch (default: 10)
  - unread_only (bool, optional): Only fetch unread (default: true)
  - since_days (int, optional): Only fetch from last N days (default: 7)

Returns:
  - success: {"emails": [...], "count": N}
  - error: {"error": "..."}
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Dict, Any
import re

sys.path.insert(0, str(Path(__file__).parent.parent))
from skills.email_connection import EmailConnection, EmailConfig
from utils.vault import get_credential

def extract_text_from_email(msg) -> str:
    """Extract plain text content from email message."""
    text = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    text += payload.decode('utf-8', errors='replace')
                except:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                text = payload.decode('utf-8', errors='replace')
        except:
            pass
    
    # Clean up text
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

def parse_email_address(addr: str) -> dict:
    """Parse email address into name and address."""
    import email.utils
    name, address = email.utils.parseaddr(addr)
    return {"name": name, "address": address}

def run(
    folder: str = "INBOX",
    limit: int = 10,
    unread_only: bool = True,
    since_days: int = 7
) -> dict:
    """Fetch emails from IMAP server."""
    
    # Get config from vault
    imap_server = get_credential("email_imap_server")
    if not imap_server:
        imap_server = "imap.gmail.com"  # Default to Gmail
    
    config = EmailConfig(imap_server=imap_server)
    
    emails = []
    
    try:
        with EmailConnection(config) as conn:
            success, msg = conn.connect()
            if not success:
                return {"error": msg}
            
            # Select folder
            success, count = conn.select_folder(folder)
            if not success:
                return {"error": f"Cannot select folder: {folder}"}
            
            # Build search criteria
            criteria_parts = []
            
            if unread_only:
                criteria_parts.append("UNSEEN")
            
            if since_days > 0:
                since_date = datetime.now() - timedelta(days=since_days)
                date_str = since_date.strftime("%d-%b-%Y")
                criteria_parts.append(f'SINCE "{date_str}"')
            
            criteria = " ".join(criteria_parts) if criteria_parts else "ALL"
            
            # Search for messages
            msg_ids = conn.search(criteria)
            
            # Limit results
            msg_ids = msg_ids[-limit:] if len(msg_ids) > limit else msg_ids
            
            # Fetch each message
            for msg_id in reversed(msg_ids):  # Newest first
                msg = conn.fetch_message(msg_id)
                if msg is None:
                    continue
                
                # Extract data
                try:
                    date_str = msg.get('Date', '')
                    date = parsedate_to_datetime(date_str) if date_str else None
                    
                    email_data = {
                        "id": msg_id.decode(),
                        "subject": msg.get('Subject', '(no subject)'),
                        "from": parse_email_address(msg.get('From', '')),
                        "to": parse_email_address(msg.get('To', '')),
                        "date": date.isoformat() if date else None,
                        "body_preview": extract_text_from_email(msg)[:500],
                        "body_length": len(extract_text_from_email(msg)),
                        "has_attachments": any(
                            part.get_content_disposition() == 'attachment'
                            for part in msg.walk()
                        ) if msg.is_multipart() else False
                    }
                    
                    emails.append(email_data)
                    
                except Exception as e:
                    # Skip problematic emails
                    continue
        
        return {
            "emails": emails,
            "count": len(emails),
            "folder": folder,
            "unread_only": unread_only
        }
        
    except Exception as e:
        return {"error": f"Email fetch failed: {e}"}
```

---

## Step 4: Implement Email Summarize Skill

### 4.1 Create `skills/email_summarize.py`

```python
"""
Skill: email_summarize
Summarizes one or more emails using LLM.

Parameters:
  - email_ids (list, optional): Specific email IDs to summarize
  - folder (str, optional): Folder to summarize (default: INBOX)
  - limit (int, optional): Max emails if no IDs given (default: 5)
  - style (str, optional): Summary style - brief/detailed/digest (default: brief)

Returns:
  - success: {"summary": "...", "emails_summarized": N}
  - error: {"error": "..."}
"""
import sys
from pathlib import Path
from typing import List, Optional
import json

sys.path.insert(0, str(Path(__file__).parent.parent))
from skills.email_fetch import run as fetch_emails, extract_text_from_email
from skills.email_connection import EmailConnection, EmailConfig
from utils.vault import get_credential

# Import Ollama for summarization
try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

SUMMARY_PROMPTS = {
    "brief": """Summarize this email in 1-2 sentences. Focus on:
- Who it's from
- Main point/action required
- Any deadlines

Email:
{email_content}

Summary:""",
    
    "detailed": """Provide a detailed summary of this email including:
- Sender and context
- Main points (bullet list)
- Action items if any
- Key dates/deadlines
- Tone (urgent, informational, etc.)

Email:
{email_content}

Summary:""",
    
    "digest": """You are summarizing multiple emails for a daily digest.
For each email, provide:
- One-line summary
- Priority (high/medium/low)
- Action needed (yes/no)

Emails:
{email_content}

Digest:"""
}

def summarize_with_ollama(content: str, style: str, model: str = "qwen2.5:7b") -> str:
    """Summarize content using Ollama."""
    if not HAS_OLLAMA:
        return "[Ollama not available - install with: pip install ollama]"
    
    prompt = SUMMARY_PROMPTS.get(style, SUMMARY_PROMPTS["brief"]).format(
        email_content=content[:8000]  # Limit context
    )
    
    try:
        response = ollama.generate(
            model=model,
            prompt=prompt,
            options={"temperature": 0.3, "num_predict": 500}
        )
        return response['response'].strip()
    except Exception as e:
        return f"[Summarization failed: {e}]"

def run(
    email_ids: Optional[List[str]] = None,
    folder: str = "INBOX",
    limit: int = 5,
    style: str = "brief"
) -> dict:
    """Summarize emails."""
    
    if style not in SUMMARY_PROMPTS:
        return {"error": f"Invalid style: {style}. Use: brief, detailed, or digest"}
    
    # Fetch emails
    if email_ids:
        # Fetch specific emails by ID
        # For MVP, we just fetch all and filter
        result = fetch_emails(folder=folder, limit=50, unread_only=False)
        if "error" in result:
            return result
        
        emails = [e for e in result["emails"] if e["id"] in email_ids]
    else:
        result = fetch_emails(folder=folder, limit=limit, unread_only=True)
        if "error" in result:
            return result
        
        emails = result["emails"]
    
    if not emails:
        return {"summary": "No emails to summarize", "emails_summarized": 0}
    
    # Summarize based on style
    if style == "digest":
        # Combine all emails for digest
        combined = "\n\n---\n\n".join([
            f"From: {e['from']['address']}\n"
            f"Subject: {e['subject']}\n"
            f"Date: {e['date']}\n"
            f"Content: {e['body_preview']}"
            for e in emails
        ])
        
        summary = summarize_with_ollama(combined, style)
        
    else:
        # Summarize each email individually
        summaries = []
        for email in emails:
            content = (
                f"From: {email['from']['address']}\n"
                f"Subject: {email['subject']}\n"
                f"Content: {email['body_preview']}"
            )
            
            individual_summary = summarize_with_ollama(content, style)
            summaries.append({
                "subject": email["subject"],
                "from": email["from"]["address"],
                "summary": individual_summary
            })
        
        # Format output
        if style == "brief":
            summary = "\n\n".join([
                f"📧 {s['subject']}\n   From: {s['from']}\n   → {s['summary']}"
                for s in summaries
            ])
        else:
            summary = "\n\n---\n\n".join([
                f"📧 {s['subject']}\nFrom: {s['from']}\n\n{s['summary']}"
                for s in summaries
            ])
    
    return {
        "summary": summary,
        "emails_summarized": len(emails),
        "style": style
    }
```

---

## Step 5: Implement Email Send Skill (with Approval)

### 5.1 Create `skills/email_send.py`

```python
"""
Skill: email_send
Sends an email (with approval queue).

Parameters:
  - to (str, required): Recipient email address
  - subject (str, required): Email subject
  - body (str, required): Email body
  - html (bool, optional): Send as HTML (default: false)
  - approve (bool, optional): Auto-approve (default: false - requires confirmation)

Returns:
  - success: {"status": "sent"} or {"status": "queued", "approval_id": "..."}
  - error: {"error": "..."}
"""
import sys
import json
import secrets
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from skills.email_connection import send_email, EmailConfig
from utils.vault import get_credential

# Approval queue file
APPROVAL_QUEUE = Path(__file__).parent.parent / "data" / "email_queue.json"

def load_queue() -> list:
    """Load the approval queue."""
    APPROVAL_QUEUE.parent.mkdir(exist_ok=True)
    if APPROVAL_QUEUE.exists():
        return json.loads(APPROVAL_QUEUE.read_text())
    return []

def save_queue(queue: list):
    """Save the approval queue."""
    APPROVAL_QUEUE.write_text(json.dumps(queue, indent=2))

def add_to_queue(to: str, subject: str, body: str, html: bool) -> str:
    """Add email to approval queue. Returns approval ID."""
    queue = load_queue()
    
    approval_id = secrets.token_hex(4)
    
    queue.append({
        "id": approval_id,
        "to": to,
        "subject": subject,
        "body": body,
        "html": html,
        "created_at": datetime.now().isoformat(),
        "status": "pending"
    })
    
    save_queue(queue)
    return approval_id

def approve_email(approval_id: str) -> dict:
    """Approve and send a queued email."""
    queue = load_queue()
    
    # Find the email
    email = next((e for e in queue if e["id"] == approval_id), None)
    if email is None:
        return {"error": f"Email {approval_id} not found"}
    
    if email["status"] != "pending":
        return {"error": f"Email {approval_id} already {email['status']}"}
    
    # Get config
    smtp_server = get_credential("email_smtp_server")
    if not smtp_server:
        smtp_server = "smtp.gmail.com"
    
    config = EmailConfig(
        imap_server="",  # Not needed for sending
        smtp_server=smtp_server
    )
    
    # Send
    success, msg = send_email(
        to=email["to"],
        subject=email["subject"],
        body=email["body"],
        config=config,
        html=email["html"]
    )
    
    # Update queue
    email["status"] = "sent" if success else "failed"
    email["sent_at"] = datetime.now().isoformat() if success else None
    email["error"] = None if success else msg
    save_queue(queue)
    
    if success:
        return {"status": "sent", "to": email["to"], "subject": email["subject"]}
    else:
        return {"error": msg}

def reject_email(approval_id: str) -> dict:
    """Reject a queued email."""
    queue = load_queue()
    
    email = next((e for e in queue if e["id"] == approval_id), None)
    if email is None:
        return {"error": f"Email {approval_id} not found"}
    
    email["status"] = "rejected"
    save_queue(queue)
    
    return {"status": "rejected", "id": approval_id}

def get_pending() -> list:
    """Get all pending emails in queue."""
    queue = load_queue()
    return [e for e in queue if e["status"] == "pending"]

def run(
    to: str,
    subject: str,
    body: str,
    html: bool = False,
    approve: bool = False
) -> dict:
    """Queue or send an email."""
    
    # Validate
    if not to or "@" not in to:
        return {"error": "Invalid recipient email"}
    
    if not subject:
        return {"error": "Subject required"}
    
    if not body:
        return {"error": "Body required"}
    
    if approve:
        # Auto-approve - send immediately
        smtp_server = get_credential("email_smtp_server")
        if not smtp_server:
            smtp_server = "smtp.gmail.com"
        
        config = EmailConfig(
            imap_server="",
            smtp_server=smtp_server
        )
        
        success, msg = send_email(to, subject, body, config, html)
        
        if success:
            return {"status": "sent", "to": to, "subject": subject}
        else:
            return {"error": msg}
    else:
        # Add to approval queue
        approval_id = add_to_queue(to, subject, body, html)
        
        return {
            "status": "queued",
            "approval_id": approval_id,
            "message": f"Email queued for approval. Reply '/email approve {approval_id}' to send."
        }
```

---

## Step 6: Create Email Configuration Skill

### 6.1 Create `skills/email_config.py`

```python
"""
Skill: email_config
Configure email credentials securely.

Parameters:
  - action (str, required): setup/test/clear
  - provider (str, optional): gmail/protonmail/fastmail/custom
  - imap_server (str, optional): Custom IMAP server
  - smtp_server (str, optional): Custom SMTP server

Returns:
  - success: {"status": "configured"} or {"status": "tested"}
  - error: {"error": "..."}
"""
import sys
from pathlib import Path
import getpass

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.vault import get_vault, set_credential, get_credential
from skills.email_connection import EmailConnection, EmailConfig

PROVIDERS = {
    "gmail": {
        "imap_server": "imap.gmail.com",
        "smtp_server": "smtp.gmail.com",
        "note": "Use an App Password from Google Account settings"
    },
    "protonmail": {
        "imap_server": "127.0.0.1",
        "imap_port": 1143,
        "smtp_server": "127.0.0.1",
        "smtp_port": 1025,
        "use_ssl": False,
        "note": "Requires ProtonMail Bridge running locally"
    },
    "fastmail": {
        "imap_server": "imap.fastmail.com",
        "smtp_server": "smtp.fastmail.com",
        "note": "Use an App Password from Fastmail settings"
    },
    "outlook": {
        "imap_server": "outlook.office365.com",
        "smtp_server": "smtp.office365.com",
        "note": "Use your Microsoft account password"
    }
}

def run(
    action: str,
    provider: str = None,
    imap_server: str = None,
    smtp_server: str = None,
    username: str = None,
    password: str = None
) -> dict:
    """Configure email settings."""
    
    vault = get_vault()
    if vault is None:
        return {"error": "Vault not initialized"}
    
    if action == "setup":
        # Determine servers
        if provider and provider in PROVIDERS:
            config = PROVIDERS[provider]
            imap = imap_server or config["imap_server"]
            smtp = smtp_server or config["smtp_server"]
            note = config.get("note", "")
        elif imap_server:
            imap = imap_server
            smtp = smtp_server or imap_server.replace("imap", "smtp")
            note = ""
        else:
            return {"error": "Specify provider or imap_server"}
        
        if not username:
            return {"error": "Username required"}
        if not password:
            return {"error": "Password required (use app password if available)"}
        
        # Store credentials
        set_credential("email_user", username)
        set_credential("email_password", password)
        set_credential("email_imap_server", imap)
        set_credential("email_smtp_server", smtp)
        
        return {
            "status": "configured",
            "provider": provider or "custom",
            "imap_server": imap,
            "smtp_server": smtp,
            "note": note
        }
    
    elif action == "test":
        # Test connection
        imap = get_credential("email_imap_server")
        if not imap:
            return {"error": "Email not configured. Run setup first."}
        
        config = EmailConfig(imap_server=imap)
        
        try:
            with EmailConnection(config) as conn:
                success, msg = conn.connect()
                if success:
                    # Try to select inbox
                    folder_ok, count = conn.select_folder("INBOX")
                    if folder_ok:
                        return {
                            "status": "tested",
                            "message": f"Connected successfully. INBOX has {count} messages."
                        }
                    return {"status": "tested", "message": "Connected but cannot access INBOX"}
                return {"error": msg}
        except Exception as e:
            return {"error": f"Test failed: {e}"}
    
    elif action == "clear":
        # Clear all email credentials
        for key in ["email_user", "email_password", "email_imap_server", "email_smtp_server"]:
            vault.delete(key)
        
        return {"status": "cleared", "message": "Email credentials removed"}
    
    elif action == "status":
        # Check current config (don't reveal password!)
        user = get_credential("email_user")
        imap = get_credential("email_imap_server")
        smtp = get_credential("email_smtp_server")
        
        if not user:
            return {"status": "not configured"}
        
        return {
            "status": "configured",
            "user": user,
            "imap_server": imap,
            "smtp_server": smtp,
            "password": "********"
        }
    
    else:
        return {"error": f"Unknown action: {action}. Use: setup, test, clear, status"}
```

---

## Step 7: Update Daemon for Email Commands

### 7.1 Update `signal_receiver.py`

Add email command shortcuts:

```python
# Add to message handler:

def handle_message(message: str, sender: str) -> str:
    msg = message.strip().lower()
    
    # Email shortcuts
    if msg.startswith("/email"):
        parts = message.split(maxsplit=2)
        if len(parts) < 2:
            return ("Email commands:\n"
                   "  /email check - Check for new emails\n"
                   "  /email summary - Summarize unread emails\n"
                   "  /email digest - Daily digest of all email\n"
                   "  /email approve <id> - Approve queued email\n"
                   "  /email pending - Show pending emails\n"
                   "  /email config - Configure email settings")
        
        cmd = parts[1].lower()
        
        if cmd == "check":
            from skills.email_fetch import run
            result = run(limit=5, unread_only=True)
            if "error" in result:
                return f"❌ {result['error']}"
            
            emails = result["emails"]
            if not emails:
                return "📭 No new emails"
            
            lines = [f"📬 {len(emails)} new email(s):"]
            for e in emails:
                lines.append(f"  • {e['from']['address']}: {e['subject'][:40]}")
            return "\n".join(lines)
        
        elif cmd == "summary":
            from skills.email_summarize import run
            result = run(style="brief", limit=5)
            if "error" in result:
                return f"❌ {result['error']}"
            return result["summary"]
        
        elif cmd == "digest":
            from skills.email_summarize import run
            result = run(style="digest", limit=20)
            if "error" in result:
                return f"❌ {result['error']}"
            return f"📋 Daily Digest:\n\n{result['summary']}"
        
        elif cmd == "approve" and len(parts) > 2:
            from skills.email_send import approve_email
            result = approve_email(parts[2])
            if "error" in result:
                return f"❌ {result['error']}"
            return f"✅ Email sent to {result['to']}"
        
        elif cmd == "reject" and len(parts) > 2:
            from skills.email_send import reject_email
            result = reject_email(parts[2])
            if "error" in result:
                return f"❌ {result['error']}"
            return f"🗑️ Email rejected"
        
        elif cmd == "pending":
            from skills.email_send import get_pending
            pending = get_pending()
            if not pending:
                return "No pending emails"
            
            lines = ["📤 Pending emails:"]
            for e in pending:
                lines.append(f"  [{e['id']}] To: {e['to']} - {e['subject'][:30]}")
            lines.append("\nReply '/email approve <id>' to send")
            return "\n".join(lines)
        
        elif cmd == "config":
            return ("To configure email:\n"
                   "1. Generate an app password for your email\n"
                   "2. Send: /email setup <provider> <email> <app_password>\n"
                   "   Providers: gmail, fastmail, protonmail, outlook\n"
                   "3. Test: /email test")
    
    # ... rest of message handling
```

---

## Step 8: Daily Digest Automation

### 8.1 Create `skills/email_digest_scheduler.py`

```python
#!/usr/bin/env python3
"""
Scheduled email digest generator.

Add to crontab:
  0 8 * * * /path/to/noctem/skills/email_digest_scheduler.py

Sends a daily email summary at 8 AM.
"""
import sys
from pathlib import Path
import subprocess

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.email_summarize import run as summarize
from skills.signal_send import run as send_signal

def main():
    # Generate digest
    result = summarize(style="digest", limit=30)
    
    if "error" in result:
        # Try to notify about the error
        send_signal(f"❌ Daily digest failed: {result['error']}")
        return 1
    
    # Send digest via Signal
    message = f"☀️ Good morning! Here's your email digest:\n\n{result['summary']}"
    
    send_signal(message)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

---

## Step 9: Testing

### 9.1 Create `tests/test_email_skills.py`

```python
"""Tests for email skills."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Note: These tests require email to be configured
# Run: python -c "from skills.email_config import run; print(run('status'))"

def test_email_config_status():
    """Test config status (doesn't require credentials)."""
    from skills.email_config import run
    result = run(action="status")
    assert "status" in result
    print(f"✓ Config status: {result['status']}")

def test_email_fetch():
    """Test email fetch (requires config)."""
    from skills.email_fetch import run
    result = run(limit=3, unread_only=False)
    
    if "error" in result:
        print(f"⚠ Email fetch: {result['error']} (expected if not configured)")
        return
    
    assert "emails" in result
    assert "count" in result
    print(f"✓ Fetched {result['count']} emails")

def test_email_summarize():
    """Test email summarization (requires config + Ollama)."""
    from skills.email_summarize import run
    result = run(limit=2, style="brief")
    
    if "error" in result:
        print(f"⚠ Email summarize: {result['error']} (expected if not configured)")
        return
    
    assert "summary" in result
    print(f"✓ Summarized {result['emails_summarized']} emails")
    print(f"  Preview: {result['summary'][:100]}...")

def test_email_queue():
    """Test email approval queue."""
    from skills.email_send import run, get_pending
    
    # Queue a test email (don't actually send)
    result = run(
        to="test@example.com",
        subject="Test Subject",
        body="Test body",
        approve=False
    )
    
    assert result["status"] == "queued"
    approval_id = result["approval_id"]
    print(f"✓ Email queued with ID: {approval_id}")
    
    # Check pending
    pending = get_pending()
    assert any(e["id"] == approval_id for e in pending)
    print(f"✓ Email appears in pending queue")
    
    # Reject (don't actually send)
    from skills.email_send import reject_email
    reject_result = reject_email(approval_id)
    assert reject_result["status"] == "rejected"
    print(f"✓ Email rejected successfully")

if __name__ == "__main__":
    print("Running email skills tests...\n")
    
    test_email_config_status()
    test_email_fetch()
    test_email_summarize()
    test_email_queue()
    
    print("\n✓ All tests completed!")
```

---

## Completion Checklist

- [ ] `utils/vault.py` created
- [ ] `skills/email_connection.py` created
- [ ] `skills/email_fetch.py` created
- [ ] `skills/email_summarize.py` created
- [ ] `skills/email_send.py` created
- [ ] `skills/email_config.py` created
- [ ] `signal_receiver.py` handles /email commands
- [ ] `skills/email_digest_scheduler.py` created
- [ ] Vault initialized during startup
- [ ] Email configured via Signal
- [ ] `/email check` returns emails
- [ ] `/email summary` summarizes emails
- [ ] `/email approve` works for queued emails
- [ ] Daily digest cron job set up

---

## Usage Examples

```
# Configure email (one-time)
/email config
/email setup gmail myemail@gmail.com myapppassword123
/email test

# Daily use
/email check
/email summary
/email digest

# Sending with approval
User: "Send an email to boss@work.com saying I'll be late tomorrow"
Noctem: "📤 Email queued. Reply '/email approve abc123' to send:
         To: boss@work.com
         Subject: Running Late Tomorrow
         Body: Hi, I wanted to let you know..."
User: /email approve abc123
Noctem: "✅ Email sent to boss@work.com"
```

---

## Security Notes

1. **App Passwords**: Always use app-specific passwords, never main account passwords
2. **Credential Storage**: Uses system keyring when available, encrypted file as fallback
3. **Approval Queue**: Emails require explicit approval before sending
4. **No Password Logging**: Passwords are never logged or included in errors
5. **Minimal Permissions**: Only requests necessary IMAP/SMTP access

---

## Troubleshooting

### "IMAP authentication failed"
- Verify you're using an app password
- Check 2FA is enabled (required for app passwords)
- For Gmail: Enable "Less secure apps" is NOT recommended, use app passwords

### "Ollama not available for summarization"
- Install: `pip install ollama`
- Ensure Ollama service is running: `ollama serve`
- Pull model: `ollama pull qwen2.5:7b`

### "Vault not initialized"
- Call `init_vault()` during daemon startup
- If using encrypted file backend, provide master password

### Emails not appearing
- Check folder name (case-sensitive)
- Verify unread_only setting
- Try increasing since_days
