"""SafeWatch - parental screen-time, app-usage and unsafe-content alert API."""
import hmac, os, random, secrets, sqlite3
from datetime import datetime, timedelta, timezone
from flask import Flask, g, jsonify, request, send_from_directory, session
from classifier import classify

DB = os.environ.get("SAFEWATCH_DB", "safewatch.db")
PASSWORD = os.environ.get("PARENT_PASSWORD", "parent123")  # set a real one in production
app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

SCHEMA = """
CREATE TABLE IF NOT EXISTS children(id INTEGER PRIMARY KEY, name TEXT NOT NULL, daily_limit_min INTEGER DEFAULT 180, device_key TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, child_id INTEGER NOT NULL, ts TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('app','web')), name TEXT NOT NULL, url TEXT, duration_sec INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, child_id INTEGER NOT NULL, ts TEXT NOT NULL,
  url TEXT, category TEXT, severity TEXT, seen INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS app_limits(child_id INTEGER, name TEXT, limit_min INTEGER, PRIMARY KEY(child_id, name));
CREATE INDEX IF NOT EXISTS ix_events ON events(child_id, ts);
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
        g.db.executescript(SCHEMA)
    return g.db

@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d: d.close()

now = lambda: datetime.now(timezone.utc)
rows = lambda q, *a: [dict(r) for r in db().execute(q, a).fetchall()]

# ---------- auth ----------
OPEN = {"login", "me", "ingest"}  # ingest is protected by a per-device key instead

@app.before_request
def guard():
    if request.path.startswith("/api/") and request.endpoint not in OPEN and not session.get("parent"):
        return jsonify(error="login required"), 401

@app.post("/api/login")
def login():
    pw = str((request.get_json(silent=True) or {}).get("password", ""))
    if hmac.compare_digest(pw.encode(), PASSWORD.encode()):
        session["parent"] = True
        return jsonify(ok=True)
    return jsonify(error="wrong password"), 401

@app.post("/api/logout")
def logout():
    session.clear(); return jsonify(ok=True)

@app.get("/api/me")
def me():
    return jsonify(logged_in=bool(session.get("parent")))

# ---------- core ----------
def record_event(child_id, kind, name, url, duration, ts=None):
    ts = ts or now().isoformat()
    db().execute("INSERT INTO events(child_id,ts,kind,name,url,duration_sec) VALUES(?,?,?,?,?,?)",
                 (child_id, ts, kind, name, url, duration))
    hit = classify(url) if kind == "web" else None
    if hit:
        db().execute("INSERT INTO alerts(child_id,ts,url,category,severity) VALUES(?,?,?,?,?)",
                     (child_id, ts, url, *hit))
    db().commit()
    return hit

def new_child(name, limit):
    cur = db().execute("INSERT INTO children(name,daily_limit_min,device_key) VALUES(?,?,?)",
                       (name, limit, secrets.token_hex(8)))
    db().commit()
    return cur.lastrowid

@app.post("/api/children")
def add_child():
    b = request.get_json(silent=True) or {}
    name = str(b.get("name", "")).strip()[:50]
    if not name: return jsonify(error="name required"), 400
    cid = new_child(name, int(b.get("daily_limit_min", 180)))
    return jsonify(id=cid, device_key=rows("SELECT device_key FROM children WHERE id=?", cid)[0]["device_key"]), 201

@app.get("/api/children")
def children():
    return jsonify(rows("SELECT * FROM children"))

@app.post("/api/events")
def ingest():
    """Called by the child's device agent. Auth: X-Device-Key header."""
    child = rows("SELECT id FROM children WHERE device_key=?", request.headers.get("X-Device-Key", "-"))
    if not child: return jsonify(error="invalid device key"), 401
    b = request.get_json(silent=True) or {}
    if b.get("kind") not in ("app", "web") or not b.get("name"):
        return jsonify(error="kind (app|web) and name required"), 400
    dur = max(0, min(int(b.get("duration_sec", 0)), 86400))
    hit = record_event(child[0]["id"], b["kind"], str(b["name"])[:100], str(b.get("url") or "")[:500] or None, dur)
    return jsonify(ok=True, flagged=bool(hit), category=hit[0] if hit else None), 201

@app.post("/api/children/<int:cid>/limits")
def set_limit(cid):
    b = request.get_json(silent=True) or {}
    name, lim = str(b.get("name", "")).strip()[:50], int(b.get("limit_min", 0))
    if not name or lim <= 0: return jsonify(error="name and positive limit_min required"), 400
    db().execute("INSERT OR REPLACE INTO app_limits VALUES(?,?,?)", (cid, name, lim)); db().commit()
    return jsonify(ok=True)

@app.get("/api/children/<int:cid>/summary")
def summary(cid):
    days = min(int(request.args.get("days", 7)), 90)
    since = (now() - timedelta(days=days)).isoformat()
    child = rows("SELECT * FROM children WHERE id=?", cid)
    if not child: return jsonify(error="not found"), 404
    daily = rows("SELECT date(ts) day, SUM(duration_sec) sec FROM events WHERE child_id=? AND ts>=? "
                 "GROUP BY day ORDER BY day", cid, since)
    top = rows("SELECT name, kind, SUM(duration_sec) sec FROM events WHERE child_id=? AND ts>=? "
               "GROUP BY name, kind ORDER BY sec DESC LIMIT 8", cid, since)
    today = now().date().isoformat()
    used = next((d["sec"] for d in daily if d["day"] == today), 0)
    per_app = {r["name"]: r["sec"] for r in rows(
        "SELECT name, SUM(duration_sec) sec FROM events WHERE child_id=? AND date(ts)=? GROUP BY name", cid, today)}
    limits = [dict(l, used_sec=per_app.get(l["name"], 0), over=per_app.get(l["name"], 0) > l["limit_min"] * 60)
              for l in rows("SELECT name, limit_min FROM app_limits WHERE child_id=?", cid)]
    return jsonify(child=child[0], daily=daily, top=top, today_sec=used, limits=limits,
                   over_limit=used > child[0]["daily_limit_min"] * 60,
                   unseen_alerts=rows("SELECT COUNT(*) n FROM alerts WHERE child_id=? AND seen=0", cid)[0]["n"])

@app.get("/api/children/<int:cid>/alerts")
def alerts(cid):
    return jsonify(rows("SELECT * FROM alerts WHERE child_id=? ORDER BY ts DESC LIMIT 50", cid))

@app.post("/api/alerts/<int:aid>/seen")
def seen(aid):
    db().execute("UPDATE alerts SET seen=1 WHERE id=?", (aid,)); db().commit()
    return jsonify(ok=True)

@app.post("/api/seed")
def seed():
    """Create demo child + a week of fake activity."""
    cid = new_child("Aarav", 150)
    db().execute("INSERT INTO app_limits VALUES(?,?,?)", (cid, "YouTube", 60)); db().commit()
    apps = ["YouTube", "Minecraft", "Instagram", "WhatsApp", "Duolingo", "Chrome"]
    sites = ["wikipedia.org/wiki/Volcano", "khanacademy.org", "youtube.com/watch?v=1", "reddit.com/r/memes"]
    bad = ["http://www.bet365.com/casino", "http://xvideos.com/x", "http://example.com/free-poker-night"]
    for d in range(7):
        base = now() - timedelta(days=d)
        for _ in range(random.randint(6, 10)):
            ts = (base - timedelta(minutes=random.randint(0, 600))).isoformat()
            if random.random() < .6:
                record_event(cid, "app", random.choice(apps), None, random.randint(300, 2700), ts)
            else:
                u = random.choice(sites)
                record_event(cid, "web", u.split("/")[0], "https://" + u, random.randint(60, 900), ts)
        if random.random() < .5:
            u = random.choice(bad)
            record_event(cid, "web", u.split("//")[1].split("/")[0], u, 120, base.isoformat())
    return jsonify(child_id=cid), 201

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

if __name__ == "__main__":
    app.run(debug=os.environ.get("DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
