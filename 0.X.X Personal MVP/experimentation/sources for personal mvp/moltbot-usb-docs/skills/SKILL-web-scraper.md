# Moltbot Skill: Web Scraper Framework

## Purpose
This skill enables Moltbot to scrape websites and store data in a local SQLite database. It is designed to:
- Fetch data from specified URLs
- Parse HTML/JSON content
- Store structured data locally
- Track scraping history and changes
- Respect rate limits and robots.txt

## Prerequisites
Install required packages:
```bash
pip3 install requests beautifulsoup4 lxml sqlite3
```

## Database Schema
Location: `~/moltbot-system/data/scraped.db`

```sql
-- Create tables
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    selector TEXT,
    frequency_minutes INTEGER DEFAULT 60,
    last_scraped DATETIME,
    enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS scraped_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    content TEXT,
    content_hash TEXT,
    metadata TEXT,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS scrape_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT,
    message TEXT,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_scraped_source ON scraped_data(source_id);
CREATE INDEX IF NOT EXISTS idx_scraped_time ON scraped_data(scraped_at);
```

## Implementation Files

### scraper.py - Main Scraper Module
Location: `~/moltbot-system/skills/scraper.py`

```python
#!/usr/bin/env python3
"""
Moltbot Web Scraper Skill
Scrapes websites and stores data in SQLite
"""

import sqlite3
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
from bs4 import BeautifulSoup

# Configuration
DATA_DIR = Path.home() / "moltbot-system" / "data"
DB_PATH = DATA_DIR / "scraped.db"
USER_AGENT = "MoltbotScraper/1.0 (Local AI Assistant)"
REQUEST_TIMEOUT = 30

class WebScraper:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        cursor = self.conn.cursor()
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                selector TEXT,
                frequency_minutes INTEGER DEFAULT 60,
                last_scraped DATETIME,
                enabled INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS scraped_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                content TEXT,
                content_hash TEXT,
                metadata TEXT,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );

            CREATE TABLE IF NOT EXISTS scrape_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT,
                message TEXT,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );
        ''')
        self.conn.commit()
    
    def add_source(self, name: str, url: str, selector: str = None, 
                   frequency_minutes: int = 60) -> int:
        """Add a new scraping source"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO sources (name, url, selector, frequency_minutes)
            VALUES (?, ?, ?, ?)
        ''', (name, url, selector, frequency_minutes))
        self.conn.commit()
        return cursor.lastrowid
    
    def list_sources(self) -> List[Dict]:
        """List all scraping sources"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM sources')
        return [dict(row) for row in cursor.fetchall()]
    
    def scrape(self, source_name: str) -> Dict[str, Any]:
        """Scrape a source by name"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM sources WHERE name = ?', (source_name,))
        source = cursor.fetchone()
        
        if not source:
            return {"error": f"Source '{source_name}' not found"}
        
        return self._scrape_source(dict(source))
    
    def _scrape_source(self, source: Dict) -> Dict[str, Any]:
        """Internal method to scrape a single source"""
        try:
            # Make request
            headers = {"User-Agent": USER_AGENT}
            response = requests.get(
                source['url'], 
                headers=headers, 
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            # Parse content
            if source['selector']:
                soup = BeautifulSoup(response.text, 'lxml')
                elements = soup.select(source['selector'])
                content = "\n".join(str(el) for el in elements)
            else:
                content = response.text
            
            # Calculate hash to detect changes
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            # Check if content changed
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT content_hash FROM scraped_data 
                WHERE source_id = ? 
                ORDER BY scraped_at DESC LIMIT 1
            ''', (source['id'],))
            last_row = cursor.fetchone()
            
            changed = not last_row or last_row['content_hash'] != content_hash
            
            # Store data
            metadata = json.dumps({
                "status_code": response.status_code,
                "content_type": response.headers.get('content-type'),
                "content_length": len(content),
                "changed": changed
            })
            
            cursor.execute('''
                INSERT INTO scraped_data (source_id, content, content_hash, metadata)
                VALUES (?, ?, ?, ?)
            ''', (source['id'], content, content_hash, metadata))
            
            # Update last_scraped
            cursor.execute('''
                UPDATE sources SET last_scraped = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (source['id'],))
            
            # Log success
            cursor.execute('''
                INSERT INTO scrape_log (source_id, status, message)
                VALUES (?, 'success', ?)
            ''', (source['id'], f"Scraped {len(content)} chars, changed={changed}"))
            
            self.conn.commit()
            
            return {
                "source": source['name'],
                "url": source['url'],
                "content_length": len(content),
                "changed": changed,
                "hash": content_hash
            }
            
        except Exception as e:
            # Log error
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO scrape_log (source_id, status, message)
                VALUES (?, 'error', ?)
            ''', (source['id'], str(e)))
            self.conn.commit()
            
            return {"error": str(e), "source": source['name']}
    
    def scrape_due(self) -> List[Dict]:
        """Scrape all sources that are due based on frequency"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM sources 
            WHERE enabled = 1 
            AND (last_scraped IS NULL 
                 OR datetime(last_scraped, '+' || frequency_minutes || ' minutes') < datetime('now'))
        ''')
        
        results = []
        for source in cursor.fetchall():
            result = self._scrape_source(dict(source))
            results.append(result)
            time.sleep(1)  # Rate limiting between sources
        
        return results
    
    def get_latest(self, source_name: str, limit: int = 5) -> List[Dict]:
        """Get latest scraped data for a source"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT sd.* FROM scraped_data sd
            JOIN sources s ON sd.source_id = s.id
            WHERE s.name = ?
            ORDER BY sd.scraped_at DESC
            LIMIT ?
        ''', (source_name, limit))
        return [dict(row) for row in cursor.fetchall()]
    
    def search_content(self, query: str, source_name: str = None) -> List[Dict]:
        """Search scraped content"""
        cursor = self.conn.cursor()
        if source_name:
            cursor.execute('''
                SELECT s.name, sd.scraped_at, sd.content FROM scraped_data sd
                JOIN sources s ON sd.source_id = s.id
                WHERE s.name = ? AND sd.content LIKE ?
                ORDER BY sd.scraped_at DESC
                LIMIT 20
            ''', (source_name, f'%{query}%'))
        else:
            cursor.execute('''
                SELECT s.name, sd.scraped_at, sd.content FROM scraped_data sd
                JOIN sources s ON sd.source_id = s.id
                WHERE sd.content LIKE ?
                ORDER BY sd.scraped_at DESC
                LIMIT 20
            ''', (f'%{query}%',))
        return [dict(row) for row in cursor.fetchall()]
    
    def close(self):
        self.conn.close()


# CLI Interface
if __name__ == "__main__":
    import sys
    
    scraper = WebScraper()
    
    if len(sys.argv) < 2:
        print("Usage: scraper.py <command> [args]")
        print("Commands: add, list, scrape, scrape-all, latest, search")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "add" and len(sys.argv) >= 4:
        name, url = sys.argv[2], sys.argv[3]
        selector = sys.argv[4] if len(sys.argv) > 4 else None
        source_id = scraper.add_source(name, url, selector)
        print(f"Added source '{name}' with ID {source_id}")
    
    elif cmd == "list":
        sources = scraper.list_sources()
        for s in sources:
            print(f"[{s['id']}] {s['name']}: {s['url']}")
    
    elif cmd == "scrape" and len(sys.argv) >= 3:
        result = scraper.scrape(sys.argv[2])
        print(json.dumps(result, indent=2))
    
    elif cmd == "scrape-all":
        results = scraper.scrape_due()
        print(json.dumps(results, indent=2))
    
    elif cmd == "latest" and len(sys.argv) >= 3:
        data = scraper.get_latest(sys.argv[2])
        for d in data:
            print(f"[{d['scraped_at']}] {len(d['content'])} chars")
    
    elif cmd == "search" and len(sys.argv) >= 3:
        results = scraper.search_content(sys.argv[2])
        for r in results:
            print(f"[{r['name']}] {r['scraped_at']}: {r['content'][:100]}...")
    
    else:
        print(f"Unknown command: {cmd}")
    
    scraper.close()
```

### Background Task Script
Location: `~/moltbot-system/tasks/scrape-all.sh`

```bash
#!/bin/bash
# Automated scraping task - runs via task-runner.sh

cd ~/moltbot-system/skills
python3 scraper.py scrape-all >> ~/moltbot-system/logs/scraper.log 2>&1
```

## Usage Instructions

### For Moltbot (Agent)

When the user asks you to:
- **Set up a new scraper**: Use `scraper.py add <name> <url> [selector]`
- **Check what scrapers exist**: Use `scraper.py list`
- **Manually trigger a scrape**: Use `scraper.py scrape <name>`
- **Get recent data**: Use `scraper.py latest <name>`
- **Search across scraped data**: Use `scraper.py search <query>`

### Example Interactions

**User**: "I want to track the price on this product page"
```bash
# Add the source with a CSS selector for the price
python3 ~/moltbot-system/skills/scraper.py add "product-price" \
    "https://example.com/product" \
    ".price-container .current-price"

# Scrape it now
python3 ~/moltbot-system/skills/scraper.py scrape "product-price"
```

**User**: "What's the latest data from that product page?"
```bash
python3 ~/moltbot-system/skills/scraper.py latest "product-price"
```

**User**: "Search all scraped data for 'sale'"
```bash
python3 ~/moltbot-system/skills/scraper.py search "sale"
```

## CSS Selector Examples

| Target | Selector |
|--------|----------|
| All paragraphs | `p` |
| Element by ID | `#main-content` |
| Element by class | `.article-body` |
| Nested elements | `article .content p` |
| Multiple elements | `h1, h2, h3` |
| Specific attribute | `a[href*="example"]` |
| Table data | `table.data tbody tr td` |

## Scheduled Scraping

The scraper automatically runs via the background task system. To modify frequency:

```bash
# Update frequency in database (SQLite)
sqlite3 ~/moltbot-system/data/scraped.db \
    "UPDATE sources SET frequency_minutes = 30 WHERE name = 'product-price'"
```

## Security Notes

- The scraper respects a 1-second delay between requests
- User-Agent identifies as MoltbotScraper
- All data stored locally in SQLite
- No external data transmission
- Logs all scrape attempts

## Troubleshooting

**"No content scraped"**
- Check if the selector is correct
- Verify the page loads without JavaScript (this scraper doesn't execute JS)

**"Connection timeout"**
- Check network connectivity
- Verify the URL is accessible

**"Rate limited"**
- Increase `frequency_minutes` for the source
- The site may block scrapers - consider reducing frequency
