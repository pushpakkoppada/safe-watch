"""SafeWatch - parental screen-time, app-usage and unsafe-content alert API."""
import os, random, sqlite3
from datetime import datetime, timedelta, timezone
from flask import Flask, g, jsonify, request, send_from_directory
from classifier import classify

DB = os.environ.get("SAFEWATCH_DB", "safewatch.db")
app = Flask(__name__, static_folder="static")

SCHEMA = """
CREATE TABLE IF NOT EXISTS children(id INTEGER PRIMARY KEY, name TEXT NOT NULL, daily_limit_min INTEGER DEFAULT 180);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, child_id INTEGER NOT NULL, ts TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('app','web')), name TEXT NOT NULL, url TEXT, duration_sec INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, child_id INTEGER NOT NULL, ts TEXT NOT NULL,
  url TEXT, category TEXT, severity TEXT, seen INTEGER DEFAULT 0);
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

# ---------- API ----------
@app.post("/api/children")
def add_child():
    b = request.get_json(force=True)
    cur = db().execute("INSERT INTO children(name,daily_limit_min) VALUES(?,?)",
                       (b["name"], b.get("daily_limit_min", 180)))
    db().commit()
    return jsonify(id=cur.lastrowid), 201

@app.get("/api/children")
def children():
    return jsonify(rows("SELECT * FROM children"))

@app.post("/api/events")
def ingest():
    """Called by the child's device agent / browser extension."""
    b = request.get_json(force=True)
    if b.get("kind") not in ("app", "web") or "child_id" not in b or "name" not in b:
        return jsonify(error="child_id, kind (app|web) and name required"), 400
    hit = record_event(b["child_id"], b["kind"], b["name"], b.get("url"), int(b.get("duration_sec", 0)))
    return jsonify(ok=True, flagged=bool(hit), category=hit[0] if hit else None), 201

@app.get("/api/children/<int:cid>/summary")
def summary(cid):
    days = int(request.args.get("days", 7))
    since = (now() - timedelta(days=days)).isoformat()
    daily = rows("SELECT date(ts) day, SUM(duration_sec) sec FROM events WHERE child_id=? AND ts>=? "
                 "GROUP BY day ORDER BY day", cid, since)
    top = rows("SELECT name, kind, SUM(duration_sec) sec FROM events WHERE child_id=? AND ts>=? "
               "GROUP BY name, kind ORDER BY sec DESC LIMIT 8", cid, since)
    child = rows("SELECT * FROM children WHERE id=?", cid)
    if not child: return jsonify(error="not found"), 404
    today = now().date().isoformat()
    used = next((d["sec"] for d in daily if d["day"] == today), 0)
    return jsonify(child=child[0], daily=daily, top=top, today_sec=used,
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
    cid = db().execute("INSERT INTO children(name,daily_limit_min) VALUES('Aarav',150)").lastrowid
    db().commit()
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
    app.run(debug=True, port=5000)
