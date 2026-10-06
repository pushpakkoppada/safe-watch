import os, sys, tempfile
os.environ["SAFEWATCH_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["PARENT_PASSWORD"] = "pw"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from app import app
from classifier import classify

@pytest.fixture
def parent():
    c = app.test_client()
    assert c.post("/api/login", json={"password": "pw"}).status_code == 200
    return c

def test_classifier():
    assert classify("https://www.bet365.com/x")[0] == "gambling"
    assert classify("http://xvideos.com/a")[1] == "high"
    assert classify("https://khanacademy.org") is None
    assert classify(None) is None

def test_login_required_and_wrong_password():
    c = app.test_client()
    assert c.get("/api/children").status_code == 401
    assert c.post("/api/login", json={"password": "bad"}).status_code == 401

def test_device_key_required():
    assert app.test_client().post("/api/events", json={"kind": "app", "name": "x"}).status_code == 401

def test_full_flow(parent):
    kid = parent.post("/api/children", json={"name": "Sam", "daily_limit_min": 1}).get_json()
    h = {"X-Device-Key": kid["device_key"]}
    c = app.test_client()
    ok = c.post("/api/events", headers=h, json={"kind": "web", "name": "b", "url": "https://bet365.com/casino", "duration_sec": 120})
    assert ok.get_json()["flagged"] is True
    c.post("/api/events", headers=h, json={"kind": "app", "name": "YouTube", "duration_sec": 300})
    assert c.post("/api/events", headers=h, json={"kind": "bad"}).status_code == 400
    parent.post(f"/api/children/{kid['id']}/limits", json={"name": "YouTube", "limit_min": 2})
    s = parent.get(f"/api/children/{kid['id']}/summary").get_json()
    assert s["over_limit"] and s["unseen_alerts"] == 1 and s["limits"][0]["over"]
    a = parent.get(f"/api/children/{kid['id']}/alerts").get_json()
    parent.post(f"/api/alerts/{a[0]['id']}/seen")
    assert parent.get(f"/api/children/{kid['id']}/summary").get_json()["unseen_alerts"] == 0

def test_validation(parent):
    assert parent.post("/api/children", json={"name": " "}).status_code == 400
    assert parent.get("/api/children/999/summary").status_code == 404
