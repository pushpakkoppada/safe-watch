# SafeWatch — Parental Screen-Time & Safe-Browsing Monitor

Parents see their child's **screen time**, **app/site usage**, and get **alerts for unsafe content**.

## Core features (milestone 1)
- **Event ingestion API** — a child-device agent/browser extension POSTs app and web activity.
- **Unsafe-content classifier** (`classifier.py`) — domain + keyword rules (adult, gambling, violence, self-harm, drugs) with severity; flagged web events auto-create alerts.
- **Parent dashboard** (`static/index.html`) — today's usage vs. daily limit, 7-day trend, top apps/sites, alert list with dismiss.
- **SQLite storage** — `children`, `events`, `alerts`.

## Run
```bash
pip install -r requirements.txt
python app.py            # http://localhost:5000
```
Click **Load demo data** in the dashboard to see sample activity.

## API
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/children` | add child `{name, daily_limit_min}` |
| GET | `/api/children` | list children |
| POST | `/api/events` | ingest `{child_id, kind: app\|web, name, url?, duration_sec}` |
| GET | `/api/children/<id>/summary?days=7` | daily totals, top usage, limit status |
| GET | `/api/children/<id>/alerts` | recent alerts |
| POST | `/api/alerts/<id>/seen` | dismiss an alert |
| POST | `/api/seed` | demo data |

Example: `curl -X POST localhost:5000/api/events -H 'Content-Type: application/json' -d '{"child_id":1,"kind":"web","name":"bet365.com","url":"https://bet365.com/casino","duration_sec":90}'`

## Not yet built (next milestones)
Parent login/auth + device pairing, real device/extension agent, push/email alerts, per-app time limits, ML-based content classification, privacy controls & data retention.
