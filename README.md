# CapCut Content Alerts

This app is a CapCut-focused content pipeline modeled on the same operational pattern as your FIFA alerts app:

1. Discover content opportunities from seeds, trends, competitor coverage, and your own site inventory.
2. Rank opportunities with bucket diversity so the queue is not dominated by comparison topics.
3. Send the best opportunities to Telegram.
4. Generate SEO, AEO, and GEO-ready article drafts with focus keywords, meta fields, internal links, and FAQ schema.
5. Approve as draft or publish live to WordPress.
6. Review opportunities and draft history through exportable admin views.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py --test
python main.py --discover-only
python main.py --once
```

## Admin and export commands

```powershell
python main.py --admin-view opportunities --format html
python main.py --admin-view drafts --format table
python main.py --export opportunities --format csv
python main.py --export history --format json
```

Generated HTML views default to `data/reports/` and exports default to `data/exports/`.

## Windows scheduler setup

```powershell
python main.py --write-scheduler-setup
python main.py --install-task-scheduler
```

This writes scheduler helpers into `data/scheduler/`, including a `.bat` runner and a PowerShell install script for Windows Task Scheduler.
