# Moltbot Skill: Gmail Reader & Summarizer

## Purpose
This skill enables Moltbot to:
- Read emails from Gmail (READ-ONLY)
- Summarize inbox contents
- Find important/urgent emails
- Search for specific emails
- Generate daily email digests

**Security**: This is READ-ONLY access. The system cannot send, modify, or delete emails.

## Prerequisites

### 1. Install Required Packages
```bash
pip3 install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### 2. Enable Gmail API
Using the same Google Cloud Project from Calendar setup:
1. Go to https://console.cloud.google.com/
2. Go to "APIs & Services" → "Enable APIs and Services"
3. Search for "Gmail API"
4. Click "Enable"

### 3. Update OAuth Scopes
When first running the Gmail reader, you'll need to re-authenticate with the additional scope.

## Implementation

### gmail_reader.py - Main Module
Location: `~/moltbot-system/skills/gmail_reader.py`

```python
#!/usr/bin/env python3
"""
Moltbot Gmail Reader
READ-ONLY access to Gmail
"""

import os
import json
import base64
import email
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from html.parser import HTMLParser

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Configuration
CONFIG_DIR = Path.home() / ".config" / "moltbot"
CREDENTIALS_FILE = CONFIG_DIR / "google_credentials.json"
TOKEN_FILE = CONFIG_DIR / "gmail_token.json"

# READ-ONLY scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


class HTMLStripper(HTMLParser):
    """Simple HTML to text converter"""
    def __init__(self):
        super().__init__()
        self.text = []
    
    def handle_data(self, data):
        self.text.append(data)
    
    def get_text(self):
        return ' '.join(self.text)


def strip_html(html_content: str) -> str:
    """Convert HTML to plain text"""
    stripper = HTMLStripper()
    stripper.feed(html_content)
    return stripper.get_text()


class GmailReader:
    def __init__(self):
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Gmail API"""
        creds = None
        
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CREDENTIALS_FILE.exists():
                    raise FileNotFoundError(
                        f"Credentials file not found: {CREDENTIALS_FILE}\n"
                        "Please follow setup instructions."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
            os.chmod(TOKEN_FILE, 0o600)
        
        self.service = build('gmail', 'v1', credentials=creds)
    
    def get_recent_emails(self, 
                         max_results: int = 20,
                         query: str = None,
                         unread_only: bool = False) -> List[Dict]:
        """
        Get recent emails from inbox
        
        Args:
            max_results: Maximum emails to return
            query: Gmail search query (e.g., "from:boss@company.com")
            unread_only: Only return unread emails
        
        Returns:
            List of email dictionaries
        """
        q = query or ""
        if unread_only:
            q = f"{q} is:unread".strip()
        
        results = self.service.users().messages().list(
            userId='me',
            maxResults=max_results,
            q=q if q else None
        ).execute()
        
        messages = results.get('messages', [])
        
        emails = []
        for msg in messages:
            email_data = self._get_email_details(msg['id'])
            if email_data:
                emails.append(email_data)
        
        return emails
    
    def _get_email_details(self, message_id: str) -> Optional[Dict]:
        """Get full details of an email"""
        try:
            msg = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            headers = msg.get('payload', {}).get('headers', [])
            
            # Extract headers
            header_dict = {}
            for h in headers:
                header_dict[h['name'].lower()] = h['value']
            
            # Parse date
            date_str = header_dict.get('date', '')
            try:
                # Try common date formats
                for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%d %b %Y %H:%M:%S %z']:
                    try:
                        parsed_date = datetime.strptime(date_str.split(' (')[0].strip(), fmt)
                        break
                    except:
                        parsed_date = None
            except:
                parsed_date = None
            
            # Get body
            body = self._extract_body(msg.get('payload', {}))
            
            # Truncate body for summary
            body_preview = body[:500] + '...' if len(body) > 500 else body
            
            return {
                'id': message_id,
                'thread_id': msg.get('threadId'),
                'subject': header_dict.get('subject', '(No subject)'),
                'from': header_dict.get('from', ''),
                'to': header_dict.get('to', ''),
                'date': parsed_date,
                'date_str': date_str,
                'snippet': msg.get('snippet', ''),
                'body_preview': body_preview,
                'labels': msg.get('labelIds', []),
                'is_unread': 'UNREAD' in msg.get('labelIds', [])
            }
            
        except Exception as e:
            print(f"Error getting email {message_id}: {e}")
            return None
    
    def _extract_body(self, payload: dict) -> str:
        """Extract email body from payload"""
        body = ""
        
        if 'body' in payload and payload['body'].get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
        
        elif 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                
                if mime_type == 'text/plain':
                    if part.get('body', {}).get('data'):
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        break
                
                elif mime_type == 'text/html':
                    if part.get('body', {}).get('data'):
                        html = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        body = strip_html(html)
                
                elif 'parts' in part:
                    body = self._extract_body(part)
                    if body:
                        break
        
        return body.strip()
    
    def get_unread_count(self) -> int:
        """Get count of unread emails"""
        results = self.service.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=1
        ).execute()
        
        return results.get('resultSizeEstimate', 0)
    
    def search_emails(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Search emails using Gmail query syntax
        
        Examples:
            - "from:boss@company.com"
            - "subject:urgent"
            - "after:2024/01/01 before:2024/02/01"
            - "has:attachment"
        """
        return self.get_recent_emails(max_results=max_results, query=query)
    
    def get_important_emails(self, max_results: int = 10) -> List[Dict]:
        """Get emails marked as important"""
        return self.get_recent_emails(
            max_results=max_results,
            query='is:important'
        )
    
    def get_today_emails(self) -> List[Dict]:
        """Get emails received today"""
        today = datetime.now().strftime('%Y/%m/%d')
        return self.get_recent_emails(query=f'after:{today}')
    
    def summarize_inbox(self) -> Dict:
        """Generate inbox summary"""
        unread = self.get_recent_emails(max_results=50, unread_only=True)
        important = self.get_important_emails(max_results=20)
        today = self.get_today_emails()
        
        # Count by sender
        senders = {}
        for email in unread:
            sender = email['from'].split('<')[0].strip()
            senders[sender] = senders.get(sender, 0) + 1
        
        # Sort by count
        top_senders = sorted(senders.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'unread_count': len(unread),
            'important_count': len(important),
            'today_count': len(today),
            'top_senders': top_senders,
            'recent_subjects': [e['subject'] for e in unread[:5]],
            'important_subjects': [e['subject'] for e in important[:5]]
        }
    
    def generate_digest(self) -> str:
        """Generate a text digest of recent emails"""
        summary = self.summarize_inbox()
        
        lines = [
            "=== Email Digest ===",
            f"Unread: {summary['unread_count']}",
            f"Important: {summary['important_count']}",
            f"Today: {summary['today_count']}",
            "",
            "Recent unread subjects:"
        ]
        
        for subj in summary['recent_subjects']:
            lines.append(f"  - {subj[:60]}...")
        
        lines.append("")
        lines.append("Top senders:")
        for sender, count in summary['top_senders']:
            lines.append(f"  - {sender}: {count} emails")
        
        return "\n".join(lines)


# CLI Interface
if __name__ == "__main__":
    import sys
    
    gmail = GmailReader()
    
    if len(sys.argv) < 2:
        print("Usage: gmail_reader.py <command> [args]")
        print("Commands: recent, unread, search, important, today, summary, digest")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "recent":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        emails = gmail.get_recent_emails(max_results=count)
        for e in emails:
            unread = "●" if e['is_unread'] else "○"
            print(f"{unread} [{e['date_str'][:16]}] {e['from'][:30]}")
            print(f"    {e['subject'][:60]}")
    
    elif cmd == "unread":
        emails = gmail.get_recent_emails(unread_only=True)
        print(f"Unread emails: {len(emails)}")
        for e in emails:
            print(f"  [{e['from'][:25]}] {e['subject'][:50]}")
    
    elif cmd == "search" and len(sys.argv) > 2:
        query = ' '.join(sys.argv[2:])
        emails = gmail.search_emails(query)
        print(f"Found {len(emails)} emails matching: {query}")
        for e in emails:
            print(f"  [{e['date_str'][:10]}] {e['subject'][:50]}")
    
    elif cmd == "important":
        emails = gmail.get_important_emails()
        print(f"Important emails:")
        for e in emails:
            print(f"  [{e['from'][:25]}] {e['subject'][:50]}")
    
    elif cmd == "today":
        emails = gmail.get_today_emails()
        print(f"Today's emails: {len(emails)}")
        for e in emails:
            print(f"  [{e['from'][:25]}] {e['subject'][:50]}")
    
    elif cmd == "summary":
        summary = gmail.summarize_inbox()
        print(json.dumps(summary, indent=2, default=str))
    
    elif cmd == "digest":
        digest = gmail.generate_digest()
        print(digest)
    
    else:
        print(f"Unknown command: {cmd}")
```

### Background Check Task
Location: `~/moltbot-system/tasks/check-email.sh`

```bash
#!/bin/bash
# Check email and generate digest

cd ~/moltbot-system/skills

# Get unread count
UNREAD=$(python3 gmail_reader.py unread 2>/dev/null | head -1)
echo "[$(date -Iseconds)] $UNREAD" >> ~/moltbot-system/logs/email.log

# Generate daily digest at 8am
HOUR=$(date +%H)
if [[ "$HOUR" == "08" ]]; then
    DIGEST=$(python3 gmail_reader.py digest 2>/dev/null)
    # Optionally send via Signal
    # signal-cli -a "$SIGNAL_PHONE" send -m "$DIGEST" "$SIGNAL_PHONE"
fi
```

## First-Time Authentication

When first running the Gmail reader:
1. A browser will open for Google sign-in
2. Authorize read-only Gmail access
3. Token stored at `~/.config/moltbot/gmail_token.json`

```bash
python3 ~/moltbot-system/skills/gmail_reader.py recent
```

## Usage Instructions

### For Moltbot (Agent)

**"Check my email"**
```bash
python3 ~/moltbot-system/skills/gmail_reader.py unread
```

**"What emails did I get today?"**
```bash
python3 ~/moltbot-system/skills/gmail_reader.py today
```

**"Show me important emails"**
```bash
python3 ~/moltbot-system/skills/gmail_reader.py important
```

**"Search for emails from John"**
```bash
python3 ~/moltbot-system/skills/gmail_reader.py search "from:john@example.com"
```

**"Give me an email summary"**
```bash
python3 ~/moltbot-system/skills/gmail_reader.py digest
```

**"Find emails about the project"**
```bash
python3 ~/moltbot-system/skills/gmail_reader.py search "subject:project"
```

## Gmail Search Syntax

| Query | Description |
|-------|-------------|
| `from:email@example.com` | From specific sender |
| `to:email@example.com` | To specific recipient |
| `subject:keyword` | Subject contains keyword |
| `is:unread` | Unread emails |
| `is:important` | Important emails |
| `is:starred` | Starred emails |
| `has:attachment` | Has attachments |
| `after:2024/01/01` | After date |
| `before:2024/02/01` | Before date |
| `newer_than:7d` | Within last 7 days |
| `label:work` | Has specific label |

Combine queries: `from:boss@company.com subject:urgent newer_than:7d`

## AI-Powered Summarization

To have Moltbot summarize email content using the local LLM:

```bash
# Get email body and pipe to Ollama
EMAIL_BODY=$(python3 ~/moltbot-system/skills/gmail_reader.py recent 1 | python3 -c "import sys,json; print(json.loads(sys.stdin.read())[0]['body_preview'])")

# Summarize with Ollama
echo "$EMAIL_BODY" | ollama run qwen-agentic "Summarize this email in 2-3 sentences:"
```

### Create a summarize-emails.sh Script
Location: `~/moltbot-system/skills/summarize-emails.sh`

```bash
#!/bin/bash
# Summarize recent unread emails using local LLM

cd ~/moltbot-system/skills

echo "=== Email Summaries ==="
echo ""

python3 -c "
import json
from gmail_reader import GmailReader
from subprocess import run, PIPE

gmail = GmailReader()
emails = gmail.get_recent_emails(max_results=5, unread_only=True)

for email in emails:
    print(f'From: {email[\"from\"][:50]}')
    print(f'Subject: {email[\"subject\"]}')
    
    # Get body and summarize
    body = email['body_preview']
    if len(body) > 100:
        result = run(
            ['ollama', 'run', 'qwen-agentic', f'Summarize in 1-2 sentences: {body[:1000]}'],
            capture_output=True,
            text=True
        )
        print(f'Summary: {result.stdout.strip()}')
    else:
        print(f'Preview: {body}')
    print('---')
"
```

## Security Notes

1. **Read-Only Access**: OAuth scope is `gmail.readonly` - CANNOT send, modify, or delete emails

2. **Token Storage**: OAuth token stored with restricted permissions (600)

3. **No Data Transmission**: Email content processed locally only

4. **Body Truncation**: Email bodies are truncated to 500 chars in previews for efficiency

5. **Revoke Access**: https://myaccount.google.com/permissions

## Remote Commands via Signal

Add to Signal handler:
- `run:check-email` - Get unread count
- `email digest` - Get email digest

## Troubleshooting

**"Insufficient permission"**
- Gmail API needs to be enabled in Google Cloud Console
- Re-authenticate to grant Gmail access

**"Quota exceeded"**
- Gmail API has rate limits
- Reduce frequency of checks

**"Token expired"**
- Delete `~/.config/moltbot/gmail_token.json`
- Re-authenticate
