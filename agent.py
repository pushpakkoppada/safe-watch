"""Demo device agent. Usage: python3 agent.py http://localhost:5000 <DEVICE_KEY>
Sends a few sample events as if from the child's device."""
import json, sys, urllib.request

base, key = sys.argv[1].rstrip("/"), sys.argv[2]
samples = [
    {"kind": "app", "name": "YouTube", "duration_sec": 1800},
    {"kind": "web", "name": "khanacademy.org", "url": "https://khanacademy.org", "duration_sec": 600},
    {"kind": "web", "name": "bet365.com", "url": "https://bet365.com/casino", "duration_sec": 90},
]
for ev in samples:
    req = urllib.request.Request(base + "/api/events", json.dumps(ev).encode(),
                                 {"Content-Type": "application/json", "X-Device-Key": key})
    print(ev["name"], "->", urllib.request.urlopen(req).read().decode().strip())
