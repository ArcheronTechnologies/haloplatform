# Allabolag.se Scraper

Zero-cost, slow-and-steady bulk scraper for Swedish company data. Uses your home internet connection directly - no proxies, no paid services.

## Timeline Expectations

| Rate | Daily | Duration | Risk |
|------|-------|----------|------|
| **Conservative** | 100/day | 15 months | Very Low |
| **Recommended** | 150/day | 10 months | Low |
| **Moderate** | 200/day | 8 months | Medium |

**This is a marathon, not a sprint.** The scraper is designed to run unattended for months.

## Setup

### 1. Install dependencies

```bash
cd archeron_scraper
pip install -r requirements.txt
```

### 2. Configure for your browser

Edit `scraper/config.py` to match your actual browser:

```python
# Use YOUR actual browser's User-Agent
# Chrome: Visit chrome://version and copy the User Agent
user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."
```

**Important:** Don't rotate user agents. Use one consistent fingerprint that matches your actual browser.

## Usage

### Step 1: Generate company list

You need orgnrs to scrape. Options:

**From Bolagsverket HVD (if you have access):**
```bash
# Export orgnrs from HVD company listing
python -m scraper.utils.hvd_export > orgnrs.txt
```

**Scrape allabolag's index (slower but free):**
```bash
# This also uses your home IP, be patient
python -m scraper.utils.index_scraper --output orgnrs.txt
```

### Step 2: Load jobs

```bash
python -m scraper.orchestrator load --file orgnrs.txt
```

For priority companies (e.g., healthcare):
```bash
python -m scraper.orchestrator load --file healthcare.txt --priority 10
```

### Step 3: Run

```bash
# Run indefinitely (Ctrl+C to stop, resume anytime)
python -m scraper.orchestrator run
```

The scraper will:
- Only run during Swedish business hours (08:00-22:00)
- Skip weekends
- Take 15-minute breaks every 20 requests
- Wait 15-45 seconds between requests
- Stop automatically if blocked (1 week cooldown)

### Step 4: Monitor

```bash
python -m scraper.orchestrator stats
```

Output:
```
Job Queue Stats:
  completed: 1,234
  pending: 548,766
  
Requests today: 87 / 150
Error rate (last hour): 0.0%

Estimated completion: ~10 months
```

## What Happens If You Get Blocked

1. Scraper detects block (403, captcha, etc.)
2. Automatically enters 1-week cooldown
3. After cooldown, resumes automatically
4. If blocked repeatedly, wait longer (2-4 weeks)

**You will NOT get legal trouble.** allabolag.se will just rate-limit you. They see millions of Swedish IPs daily - one slow researcher isn't worth pursuing.

## Running Unattended

### Using screen/tmux

```bash
# Start in background
screen -S scraper
python -m scraper.orchestrator run

# Detach: Ctrl+A, D
# Reattach later:
screen -r scraper
```

### Using systemd (Linux)

```ini
# /etc/systemd/system/allabolag-scraper.service
[Unit]
Description=Allabolag Scraper
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/archeron_scraper
ExecStart=/usr/bin/python -m scraper.orchestrator run
Restart=on-failure
RestartSec=3600

[Install]
WantedBy=multi-user-target
```

```bash
sudo systemctl enable allabolag-scraper
sudo systemctl start allabolag-scraper
```

## Data Output

Data stored in SQLite (`allabolag_scrape.db`):

```bash
# Count scraped companies
sqlite3 allabolag_scrape.db "SELECT COUNT(*) FROM companies"

# Find directors with many companies
sqlite3 allabolag_scrape.db "
  SELECT name, COUNT(*) as n 
  FROM directors 
  GROUP BY name 
  HAVING n > 5 
  ORDER BY n DESC 
  LIMIT 20
"

# Healthcare companies
sqlite3 allabolag_scrape.db "
  SELECT orgnr, name, city 
  FROM companies 
  WHERE sni_code LIKE '86%'
"
```

## Configuration Reference

`scraper/config.py`:

```python
# Timing
min_delay: float = 15.0        # Minimum seconds between requests
max_delay: float = 45.0        # Maximum seconds
requests_per_hour_max: int = 15
requests_per_day_max: int = 150

# Behavior
active_hours_start: int = 8    # Start at 08:00 Swedish
active_hours_end: int = 22     # Stop at 22:00 Swedish  
skip_weekends: bool = True     # No scraping Sat/Sun

# On block
block_cooldown_hours: int = 168  # 1 week cooldown
```

## FAQ

**Q: Why so slow?**
A: Because you're using one residential IP. Fast scraping = instant block.

**Q: Can I run multiple instances?**
A: Not from the same IP. You could run from different locations (home, mobile, friend's house) with separate databases.

**Q: What if allabolag changes their HTML?**
A: Update `parser.py`. Raw HTML is saved, so you can reparse later.

**Q: Is this legal?**
A: Scraping public data for research is generally legal in Sweden/EU. Don't redistribute the data commercially. When in doubt, consult a lawyer.

**Q: Why not use Selenium/Playwright?**
A: Overkill. allabolag.se doesn't require JavaScript. Plain HTTP is simpler and less detectable.

## Architecture

```
┌─────────────────────────────┐
│     Your Home Internet      │
│     (No proxy!)             │
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│      Session Manager        │
│  - Timing controls          │
│  - Block detection          │
│  - Rate limiting            │
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│         Parser              │
│  - HTML extraction          │
│  - Company data             │
│  - Directors                │
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│      SQLite Database        │
│  - Job queue (resumable)    │
│  - Scraped companies        │
│  - Director relationships   │
└─────────────────────────────┘
```