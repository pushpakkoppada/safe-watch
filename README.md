# SafeWatch — Parental Screen-Time & Safe-Browsing Monitor

Parents see their child's **screen time**, **app/site usage**, and get **alerts for unsafe content**.

## Features
- **Event ingestion API** — a child-device agent/browser extension POSTs app and web activity.
- **Unsafe-content classifier** (`classifier.py`) — domain + keyword rules (adult, gambling, violence, self-harm, drugs) with severity; flagged web events auto-create alerts.
- **Parent dashboard** (`static/index.html`) — today's usage vs. daily limit, 7-day trend, top apps/sites, alert list with dismiss.
- **SQLite storage** — `children`, `events`, `alerts`.

- **Parent login** (password from `PARENT_PASSWORD`), session cookie.
- **Device pairing** — each child gets a secret key; the device agent sends it as `X-Device-Key`.
- **Per-app time limits** plus a daily limit, with "over limit" warnings.
- **Responsive dashboard** (phone, tablet, desktop; light/dark) and HTML-escaped output.

## Run locally
```bash
python3 -m pip install -r requirements.txt
python3 app.py            # http://localhost:5000  (default password: parent123)
```
Click **Demo data**, or add a child and run the sample agent:
`python3 agent.py http://localhost:5000 <DEVICE_KEY>`

## Test
```bash
python3 -m pip install pytest
python3 -m pytest -q
```

## Deploy (Render)
Build: `pip install -r requirements.txt` — Start: `gunicorn app:app`
Env vars: `PARENT_PASSWORD`, `SECRET_KEY` (long random string).
Note: SQLite on free hosting resets on redeploy/sleep; use "Demo data" to repopulate. For real use, move to PostgreSQL.

## API (login required unless noted)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/login`, `/api/logout` | session auth (`/api/me` checks) |
| POST/GET | `/api/children` | add / list children |
| POST | `/api/events` | **device key auth** — `{kind: app\|web, name, url?, duration_sec}` |
| GET | `/api/children/<id>/summary` | usage, limits, unseen alert count |
| POST | `/api/children/<id>/limits` | `{name, limit_min}` |
| GET | `/api/children/<id>/alerts` | recent alerts |
| POST | `/api/alerts/<id>/seen` | dismiss alert |
| POST | `/api/seed` | demo data |

## Known limitations
Rule-based classifier (no ML), no email/push alerts, single parent account, SQLite storage.
