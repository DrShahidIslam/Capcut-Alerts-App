# CapCut Content Alerts

This app is a CapCut-focused content pipeline modeled on the same operational pattern as your FIFA alerts app:

1. Discover content opportunities from seeds, trends, competitor coverage, and your own site inventory.
2. Rank opportunities and send the best ones to Telegram.
3. Generate a full draft after approval.
4. Approve as draft or publish live to WordPress.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py --discover-only
python main.py --once
```
