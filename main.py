from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "safewalk.db"

app = FastAPI(title="SafeWalk AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

APP_STATE: Dict[str, Any] = {
    "network": "Connected",
    "gps": "Reliable",
    "battery": 72,
    "session": "Inactive",
    "lastReliableLocation": {
        "lat": 40.7128,
        "lng": -74.0060,
        "timestamp": "2026-10-06T14:30:00Z",
    },
    "journey": None,
    "queuedEvents": [],
    "timeline": [
        {"time": "14:30", "event": "Full Protection"},
        {"time": "14:34", "event": "GPS signal weakened"},
        {"time": "14:34", "event": "Switched to Degraded Protection"},
        {"time": "14:37", "event": "Network unavailable"},
        {"time": "14:37", "event": "Entered Offline Safety Mode"},
        {"time": "14:40", "event": "Network restored"},
        {"time": "14:40", "event": "Safety session recovered"},
    ],
    "emergency": False,
    "trustedContacts": [],
    "journeyHistory": [],
    "safetyHistory": [
        {"time": "14:30", "type": "Status", "message": "Full Protection"},
        {"time": "14:34", "type": "GPS", "message": "GPS signal weakened"},
        {"time": "14:37", "type": "Network", "message": "Network unavailable"},
        {"time": "14:40", "type": "Recovery", "message": "Safety session recovered"},
    ],
}


def now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def now_clock() -> str:
    return datetime.now().strftime("%H:%M")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            relationship TEXT NOT NULL,
            phone TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS journeys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destination TEXT NOT NULL,
            started_at TEXT NOT NULL,
            status TEXT NOT NULL,
            estimated_arrival TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def add_event(type_: str, message: str) -> None:
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO events (type, message, created_at) VALUES (?, ?, ?)",
        (type_, message, now_iso()),
    )
    conn.commit()
    conn.close()
    APP_STATE["safetyHistory"].append({"time": now_clock(), "type": type_, "message": message})


def add_timeline_event(event: str) -> None:
    APP_STATE["timeline"].append({"time": now_clock(), "event": event})


def current_battery_mode() -> str:
    battery = APP_STATE["battery"]
    if battery <= 5:
        return "Critical"
    if battery <= 15:
        return "Battery Saver"
    if battery <= 30:
        return "Battery Awareness"
    return "Normal"


def get_overall_state() -> str:
    if APP_STATE["emergency"]:
        return "EMERGENCY MODE"

    critical_count = 0
    if APP_STATE["network"] == "Offline":
        critical_count += 1
    if APP_STATE["gps"] == "Unavailable":
        critical_count += 1
    if APP_STATE["battery"] <= 5:
        critical_count += 1

    degraded_count = 0
    if APP_STATE["network"] in {"Weak", "Offline"}:
        degraded_count += 1
    if APP_STATE["gps"] in {"Weak", "Unavailable"}:
        degraded_count += 1
    if APP_STATE["battery"] <= 30:
        degraded_count += 1
    if APP_STATE["session"] in {"Paused", "Recovered", "Offline Safety Mode", "Battery Awareness", "Critical Safety Mode"}:
        degraded_count += 1

    if critical_count > 0:
        return "EMERGENCY MODE"
    if degraded_count >= 2:
        return "LIMITED PROTECTION"
    if degraded_count == 1:
        return "DEGRADED PROTECTION"
    return "FULL PROTECTION"


def get_safety_status_payload() -> Dict[str, Any]:
    overall = get_overall_state()
    mode_explanation = {
        "FULL PROTECTION": "All important services available.",
        "DEGRADED PROTECTION": "One service has reduced reliability, but the system continues safely in fallback mode.",
        "LIMITED PROTECTION": "Multiple services are degraded or unavailable; essential safety functions are prioritized.",
        "EMERGENCY MODE": "A critical safety capability is unavailable or a simulated emergency event has been triggered.",
    }

    payload = {
        "overallState": overall,
        "status": overall,
        "network": APP_STATE["network"],
        "gps": APP_STATE["gps"],
        "battery": APP_STATE["battery"],
        "batteryMode": current_battery_mode(),
        "session": APP_STATE["session"],
        "journey": APP_STATE["journey"],
        "lastReliableLocation": APP_STATE["lastReliableLocation"],
        "gpsLabel": "GPS unavailable — using last reliable location" if APP_STATE["gps"] == "Unavailable" else "Location signal weak" if APP_STATE["gps"] == "Weak" else "Location reliable",
        "queuedEvents": APP_STATE["queuedEvents"],
        "timeline": APP_STATE["timeline"],
        "safetyHistory": APP_STATE["safetyHistory"][-8:],
        "emergency": APP_STATE["emergency"],
        "modeExplanation": mode_explanation.get(overall, "System status unknown."),
    }
    return payload


def queue_local_event(message: str) -> None:
    APP_STATE["queuedEvents"].append({"at": now_iso(), "message": message})


def clear_local_queue() -> None:
    APP_STATE["queuedEvents"] = []


def persist_contact(contact: Dict[str, str]) -> None:
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO contacts (name, relationship, phone) VALUES (?, ?, ?)",
        (contact["name"], contact["relationship"], contact["phone"]),
    )
    conn.commit()
    conn.close()


def load_contacts() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM contacts ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def load_events() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return [dict(row) for row in rows]


HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SafeWalk AI</title>
  <style>
    :root {
      --bg: #071a2d;
      --panel: #0e233c;
      --card: rgba(18, 45, 79, 0.92);
      --border: rgba(125, 178, 255, 0.25);
      --text: #edf6ff;
      --muted: #a9bedf;
      --primary: #4cc9f0;
      --success: #39d98a;
      --warning: #ffb703;
      --danger: #ff5d73;
      --shadow: 0 20px 45px rgba(0, 0, 0, 0.28);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #071a2d 0%, #0d2140 100%);
      color: var(--text);
      min-height: 100vh;
    }

    button, input {
      font: inherit;
    }

    .container {
      max-width: 1100px;
      margin: 0 auto;
      padding: 20px 16px 60px;
    }

    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 700;
      letter-spacing: 0.02em;
    }

    .brand-badge {
      width: 38px; height: 38px;
      display: grid; place-items: center;
      border-radius: 12px;
      color: #062135;
      background: linear-gradient(135deg, var(--primary), #55d6d7);
      font-weight: 800;
      box-shadow: var(--shadow);
    }

    .prototype-pill {
      padding: 7px 10px;
      border-radius: 999px;
      background: rgba(255, 183, 3, 0.12);
      color: #ffd77b;
      border: 1px solid rgba(255, 183, 3, 0.45);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 700;
    }

    .hero {
      background: linear-gradient(135deg, rgba(76, 201, 240, 0.15), rgba(19, 58, 92, 0.92));
      border: 1px solid var(--border);
      border-radius: 26px;
      box-shadow: var(--shadow);
      padding: 24px 18px;
      margin-bottom: 18px;
    }

    .hero h1 {
      margin: 0 0 8px;
      font-size: clamp(2rem, 7vw, 3.2rem);
      line-height: 1.08;
    }

    .tagline {
      margin: 0;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.5;
    }

    .hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 18px;
    }

    .btn {
      border: 0;
      border-radius: 14px;
      padding: 12px 18px;
      font-weight: 700;
      cursor: pointer;
      transition: 0.2s ease;
      background: #ebf7ff;
      color: #0d1d2c;
      box-shadow: 0 8px 18px rgba(0,0,0,0.16);
    }
    .btn:hover { transform: translateY(-1px); }
    .btn.primary {
      background: linear-gradient(135deg, var(--primary), #6bdcff);
      color: #062035;
    }
    .btn.warning {
      background: linear-gradient(135deg, #ff9f43, #ff7b54);
      color: white;
    }
    .btn.danger {
      background: linear-gradient(135deg, var(--danger), #ff3b4d);
      color: white;
    }
    .btn.secondary {
      background: rgba(255,255,255,0.08);
      color: var(--text);
      border: 1px solid rgba(255,255,255,0.12);
    }
    .btn.ghost {
      background: transparent;
      color: var(--text);
      border: 1px solid var(--border);
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
    }

    .card {
      background: rgba(18, 45, 79, 0.88);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 18px;
      box-shadow: var(--shadow);
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
    }

    .card h2, .card h3 { margin: 0; }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      border: 1px solid transparent;
    }

    .status-full { background: rgba(57, 217, 138, 0.12); color: #80edb2; border-color: rgba(57, 217, 138, 0.4); }
    .status-degraded { background: rgba(255, 183, 3, 0.12); color: #ffd76a; border-color: rgba(255, 183, 3, 0.4); }
    .status-limited { background: rgba(255, 120, 78, 0.12); color: #ffc08a; border-color: rgba(255, 120, 78, 0.4); }
    .status-emergency { background: rgba(255, 93, 115, 0.12); color: #ffb7c0; border-color: rgba(255, 93, 115, 0.5); }

    .stat-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 12px;
    }

    .metric {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 16px;
      padding: 14px 12px;
    }

    .metric-label {
      display: block;
      color: var(--muted);
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 7px;
    }

    .metric-value {
      font-size: clamp(1.15rem, 5vw, 1.65rem);
      font-weight: 800;
      display: block;
    }

    .chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }

    .chip {
      padding: 7px 10px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(255,255,255,0.03);
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
    }

    .demo-controls {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }

    .journey-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .timer {
      font-size: 2rem;
      font-weight: 800;
      letter-spacing: 0.06em;
    }

    .info-list {
      display: grid;
      gap: 10px;
      margin-top: 10px;
    }

    .info-row {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      padding-bottom: 8px;
    }
    .info-row:last-child { border-bottom: 0; padding-bottom: 0; }

    .muted { color: var(--muted); }

    .timeline {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 10px;
    }

    .timeline li {
      border-left: 2px solid rgba(76, 201, 240, 0.5);
      padding-left: 12px;
      color: var(--muted);
      line-height: 1.5;
    }

    .timeline .time {
      color: var(--text);
      font-weight: 700;
      margin-right: 8px;
    }

    .form-grid {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }

    .form-grid input {
      width: 100%;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 10px;
      padding: 12px 14px;
      color: var(--text);
    }
    .form-grid input::placeholder { color: #98afd0; }

    .history-list, .contact-list {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }

    .history-item, .contact-item {
      background: rgba(255,255,255,0.02);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 12px;
      padding: 12px 14px;
    }

    .privacy-grid {
      display: grid;
      gap: 12px;
      margin-top: 10px;
    }

    .privacy-point {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      background: rgba(255,255,255,0.02);
      border-radius: 12px;
      padding: 12px 14px;
      border: 1px solid rgba(255,255,255,0.06);
    }

    .privacy-dot {
      width: 10px; height: 10px; border-radius: 50%;
      background: linear-gradient(135deg, var(--success), var(--primary));
      margin-top: 6px;
      flex-shrink: 0;
    }

    details {
      margin-top: 18px;
      background: rgba(255,255,255,0.02);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      padding: 12px 14px;
    }
    details summary {
      cursor: pointer;
      font-weight: 700;
    }

    .modal {
      position: fixed;
      inset: 0;
      background: rgba(4, 14, 28, 0.7);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 16px;
      z-index: 50;
    }
    .modal.open { display: flex; }

    .modal-card {
      width: min(100%, 420px);
      background: #0d2140;
      border: 1px solid var(--border);
      border-radius: 22px;
      padding: 22px 18px 18px;
      box-shadow: var(--shadow);
    }

    .modal h3 {
      margin: 0 0 8px;
      font-size: 1.5rem;
    }

    .modal-actions {
      display: flex;
      gap: 10px;
      justify-content: flex-end;
      margin-top: 18px;
    }

    @media (min-width: 768px) {
      .grid {
        grid-template-columns: 1.3fr 1fr;
      }
      .hero {
        padding: 30px 28px;
      }
      .container { padding: 24px 20px 90px; }
      .demo-controls {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
    }
  </style>
</head>
<body>
  <div class="container">
    <header class="topbar">
      <div class="brand">
        <div class="brand-badge">S</div>
        <div>SafeWalk AI</div>
      </div>
      <div class="prototype-pill">Prototype / Demo</div>
    </header>

    <section class="hero">
      <h1>Safety that continues when technology doesn’t.</h1>
      <p class="tagline">
        SafeWalk AI continuously checks whether the safety system itself is functioning and automatically adapts when network, GPS, battery, or connectivity becomes unreliable.
      </p>

      <div class="hero-actions">
        <button class="btn primary" id="startJourneyBtn">Start SafeWalk</button>
        <button class="btn danger" id="sosBtn">Emergency SOS</button>
      </div>
    </section>

    <div class="grid">
      <main>
        <section class="card">
          <div class="card-header">
            <h2>Current Safety Status</h2>
            <span id="overallBadge" class="status-badge status-full">FULL PROTECTION</span>
          </div>

          <div class="stat-grid">
            <div class="metric">
              <span class="metric-label">Journey Status</span>
              <span class="metric-value" id="journeyStatusText">Inactive</span>
            </div>
            <div class="metric">
              <span class="metric-label">GPS</span>
              <span class="metric-value" id="gpsStatusText">Reliable</span>
            </div>
            <div class="metric">
              <span class="metric-label">Network</span>
              <span class="metric-value" id="networkStatusText">Connected</span>
            </div>
            <div class="metric">
              <span class="metric-label">Battery</span>
              <span class="metric-value" id="batteryStatusText">72%</span>
            </div>
          </div>

          <div class="chip-row">
            <span class="chip">Safety Session: <strong id="sessionText">Inactive</strong></span>
            <span class="chip">Last Reliable Location: <strong id="locationText">40.7128, -74.0060</strong></span>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>Safety System Health</h2>
          </div>

          <div class="info-list">
            <div class="info-row">
              <span class="muted">Network</span>
              <strong id="networkDetail">Connected</strong>
            </div>
            <div class="info-row">
              <span class="muted">GPS</span>
              <strong id="gpsDetail">Reliable</strong>
            </div>
            <div class="info-row">
              <span class="muted">Battery</span>
              <strong id="batteryDetail">Normal</strong>
            </div>
            <div class="info-row">
              <span class="muted">Safety Session</span>
              <strong id="sessionDetail">Inactive</strong>
            </div>
            <div class="info-row">
              <span class="muted">Last Reliable Location</span>
              <strong id="lastLocationDetail">40.7128, -74.0060</strong>
            </div>
          </div>

          <div class="card-header" style="margin-top: 18px;">
            <h3>Overall System State</h3>
          </div>
          <div class="status-badge status-full" id="overallBadgeLarge">FULL PROTECTION</div>
          <p class="muted" id="stateDescription" style="margin-top: 12px;">All important services available.</p>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>SafeWalk Session</h2>
          </div>

          <div class="journey-head">
            <div>
              <div class="muted" style="font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em;">Destination</div>
              <strong id="destinationText">Not started</strong>
            </div>
            <div class="timer" id="timerText">00:00</div>
          </div>

          <div class="info-list">
            <div class="info-row">
              <span class="muted">Current location</span>
              <strong id="currentLocationText">Waiting for GPS</strong>
            </div>
            <div class="info-row">
              <span class="muted">Safety status</span>
              <strong id="safetyStatusText">Standby</strong>
            </div>
            <div class="info-row">
              <span class="muted">Estimated arrival</span>
              <strong id="etaText">—</strong>
            </div>
          </div>

          <div class="hero-actions">
            <button class="btn secondary" id="checkinBtn">I’m Safe</button>
            <button class="btn danger" id="sessionSosBtn">Emergency</button>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>Responsible AI / Privacy</h2>
          </div>

          <div class="privacy-grid">
            <div class="privacy-point">
              <div class="privacy-dot"></div>
              <div>Sensitive data should be processed locally whenever possible, especially in offline or degraded protection modes.</div>
            </div>
            <div class="privacy-point">
              <div class="privacy-dot"></div>
              <div>Raw camera or audio data should not be stored unnecessarily; this prototype intentionally limits data retention.</div>
            </div>
            <div class="privacy-point">
              <div class="privacy-dot"></div>
              <div>Location should only be collected during an active safety session and is clearly labeled as a demo/prototype.</div>
            </div>
            <div class="privacy-point">
              <div class="privacy-dot"></div>
              <div>This app is a prototype and not a replacement for emergency services. It simulates alerts and notifications only.</div>
            </div>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>How our innovation works</h2>
          </div>
          <p class="muted">
            SafeWalk does not only detect danger. It continuously checks whether the safety system itself is functioning and automatically adapts when network, GPS, battery, or connectivity becomes unreliable.
          </p>
        </section>
      </main>

      <aside>
        <section class="card">
          <div class="card-header">
            <h2>Developer Demo Controls</h2>
          </div>

          <div class="demo-controls">
            <button class="btn warning" id="gpsFailBtn">Simulate GPS Failure</button>
            <button class="btn warning" id="networkFailBtn">Simulate Network Failure</button>
            <button class="btn primary" id="networkRecoveryBtn">Simulate Network Recovery</button>
            <button class="btn secondary" id="batteryLowBtn">Low Battery</button>
            <button class="btn secondary" id="batteryCriticalBtn">Critical Battery</button>
            <button class="btn ghost" id="resetDemoBtn">Reset Demo</button>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>Fallback Logic</h2>
          </div>
          <div class="info-list">
            <div class="info-row">
              <span class="muted">Network degraded</span>
              <strong>Offline Safety Mode</strong>
            </div>
            <div class="info-row">
              <span class="muted">GPS unreliable</span>
              <strong>Use last reliable location</strong>
            </div>
            <div class="info-row">
              <span class="muted">Battery low</span>
              <strong>Battery Saver mode</strong>
            </div>
            <div class="info-row">
              <span class="muted">Recovery</span>
              <strong>Sync and resume</strong>
            </div>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>Trusted Contacts</h2>
          </div>

          <form id="contactForm" class="form-grid">
            <input type="text" id="nameInput" placeholder="Name" required />
            <input type="text" id="relationshipInput" placeholder="Relationship" required />
            <input type="tel" id="phoneInput" placeholder="Phone Number" required />
            <button class="btn primary" type="submit">Add Contact</button>
          </form>

          <div id="contactList" class="contact-list"></div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>Safety History</h2>
          </div>
          <div id="historyList" class="history-list"></div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>Explainable Safety Timeline</h2>
          </div>
          <ul id="timelineList" class="timeline"></ul>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>System Health / Technical Details</h2>
          </div>

          <details open>
            <summary>View technical details</summary>
            <div class="info-list">
              <div class="info-row">
                <span class="muted">Connectivity</span>
                <strong id="techNetwork">Connected</strong>
              </div>
              <div class="info-row">
                <span class="muted">Location source</span>
                <strong id="techGps">Reliable</strong>
              </div>
              <div class="info-row">
                <span class="muted">Battery awareness</span>
                <strong id="techBattery">Normal</strong>
              </div>
              <div class="info-row">
                <span class="muted">Session continuity</span>
                <strong id="techSession">Active</strong>
              </div>
              <div class="info-row">
                <span class="muted">Queue sync</span>
                <strong id="techQueue">0 events queued</strong>
              </div>
            </div>
          </details>
        </section>
      </aside>
    </div>
  </div>

  <div id="sosModal" class="modal" aria-hidden="true">
    <div class="modal-card">
      <h3>Emergency Demo</h3>
      <p class="muted">DEMO — No real emergency message has been sent.</p>
      <p class="muted">This will trigger a simulated safety alert and notify a trusted contact using demo data.</p>

      <div class="info-list">
        <div class="info-row">
          <span class="muted">Location</span>
          <strong id="modalLocation">40.7128, -74.0060</strong>
        </div>
        <div class="info-row">
          <span class="muted">Time</span>
          <strong id="modalTime">—</strong>
        </div>
      </div>

      <div class="modal-actions">
        <button class="btn ghost" id="cancelSosBtn">Cancel</button>
        <button class="btn danger" id="confirmSosBtn">Confirm Demo Alert</button>
      </div>
    </div>
  </div>

  <script>
    const state = {
      timerSeconds: 0,
      timerInterval: null,
      lastStatus: null,
      activeJourney: null
    };

    function setBadge(el, status) {
      el.className = 'status-badge';
      if (status === 'FULL PROTECTION') el.classList.add('status-full');
      else if (status === 'DEGRADED PROTECTION') el.classList.add('status-degraded');
      else if (status === 'LIMITED PROTECTION') el.classList.add('status-limited');
      else if (status === 'EMERGENCY MODE') el.classList.add('status-emergency');
      el.textContent = status;
    }

    function updateBadges(status) {
      const ids = ['overallBadge', 'overallBadgeLarge'];
      ids.forEach((id) => {
        const el = document.getElementById(id);
        if (el) setBadge(el, status);
      });
    }

    function setText(id, value) {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    }

    function updateJourneyTimer() {
      const minutes = Math.floor(state.timerSeconds / 60).toString().padStart(2, '0');
      const seconds = (state.timerSeconds % 60).toString().padStart(2, '0');
      setText('timerText', `${minutes}:${seconds}`);
    }

    function stopTimer() {
      if (state.timerInterval) {
        clearInterval(state.timerInterval);
        state.timerInterval = null;
      }
    }

    function startTimer() {
      stopTimer();
      state.timerInterval = setInterval(() => {
        state.timerSeconds += 1;
        updateJourneyTimer();
      }, 1000);
    }

    function renderContacts(contacts) {
      const list = document.getElementById('contactList');
      list.innerHTML = '';
      if (!contacts || contacts.length === 0) {
        list.innerHTML = '<div class="contact-item">No trusted contacts added yet.</div>';
        return;
      }
      contacts.forEach((contact) => {
        const item = document.createElement('div');
        item.className = 'contact-item';
        item.innerHTML = `
          <strong>${contact.name}</strong><br />
          <span class="muted">${contact.relationship}</span><br />
          <span class="muted">${contact.phone}</span>
        `;
        list.appendChild(item);
      });
    }

    function renderHistory(events) {
      const list = document.getElementById('historyList');
      list.innerHTML = '';
      if (!events || events.length === 0) {
        list.innerHTML = '<div class="history-item">No safety history yet.</div>';
        return;
      }
      [...events].reverse().forEach((event) => {
        const item = document.createElement('div');
        item.className = 'history-item';
        item.innerHTML = `
          <div class="muted">${event.time}</div>
          <div><strong>${event.type}</strong></div>
          <div>${event.message}</div>
        `;
        list.appendChild(item);
      });
    }

    function renderTimeline(timeline) {
      const list = document.getElementById('timelineList');
      list.innerHTML = '';
      if (!timeline || timeline.length === 0) {
        list.innerHTML = '<li>No timeline yet.</li>';
        return;
      }
      [...timeline].reverse().forEach((entry) => {
        const item = document.createElement('li');
        item.innerHTML = `<span class="time">${entry.time}</span> — ${entry.event}`;
        list.appendChild(item);
      });
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
      });
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      return await response.json();
    }

    async function loadStatus() {
      try {
        const data = await fetchJson('/safety-status');
        state.lastStatus = data;
        const overall = data.overallState || 'FULL PROTECTION';
        updateBadges(overall);

        setText('journeyStatusText', data.journey ? data.journey.status : 'Inactive');
        setText('gpsStatusText', data.gps || 'Reliable');
        setText('networkStatusText', data.network || 'Connected');
        setText('batteryStatusText', `${data.battery || 72}%`);
        setText('sessionText', data.session || 'Inactive');
        setText('locationText', data.lastReliableLocation ? `${data.lastReliableLocation.lat}, ${data.lastReliableLocation.lng}` : 'Unknown');

        setText('networkDetail', data.network || 'Connected');
        setText('gpsDetail', data.gps || 'Reliable');
        setText('batteryDetail', data.batteryMode || 'Normal');
        setText('sessionDetail', data.session || 'Inactive');
        setText('lastLocationDetail', data.lastReliableLocation ? `${data.lastReliableLocation.lat}, ${data.lastReliableLocation.lng}` : 'Unknown');
        setText('stateDescription', data.modeExplanation || 'All important services available.');

        setText('techNetwork', data.network || 'Connected');
        setText('techGps', data.gps || 'Reliable');
        setText('techBattery', data.batteryMode || 'Normal');
        setText('techSession', data.session || 'Inactive');
        setText('techQueue', `${(data.queuedEvents || []).length} events queued`);

        if (data.journey) {
          const j = data.journey;
          setText('destinationText', j.destination || 'Not started');
          setText('safetyStatusText', j.safetyStatus || 'Standby');
          setText('etaText', j.estimatedArrival || '—');
          setText('currentLocationText', j.currentLocation || 'Waiting for GPS');
          state.activeJourney = { ...j, isRunning: j.status === 'Active' || j.status === 'Recovered' };
          if (state.activeJourney.isRunning) startTimer();
          else {
            stopTimer();
            setText('timerText', '00:00');
          }
        } else {
          setText('destinationText', 'Not started');
          setText('safetyStatusText', 'Standby');
          setText('etaText', '—');
          setText('currentLocationText', 'Waiting for GPS');
          state.activeJourney = null;
          stopTimer();
          setText('timerText', '00:00');
        }

        renderTimeline(data.timeline || []);
        renderHistory(data.safetyHistory || []);
      } catch (error) {
        console.error(error);
      }
    }

    async function loadContacts() {
      try {
        const data = await fetchJson('/trusted-contacts');
        renderContacts(data.contacts || []);
      } catch (error) {
        console.error(error);
      }
    }

    async function startJourney() {
      try {
        const data = await fetchJson('/journey/start', {
          method: 'POST',
          body: JSON.stringify({ destination: 'Downtown Station', estimatedArrival: '19:15' })
        });
        if (data.success) await loadStatus();
      } catch (error) {
        console.error(error);
      }
    }

    async function triggerDemo(url) {
      try {
        const data = await fetchJson(url, { method: 'POST' });
        if (data.success) await loadStatus();
      } catch (error) {
        console.error(error);
      }
    }

    function openEmergencyModal() {
      const modal = document.getElementById('sosModal');
      modal.classList.add('open');
      const loc = state.lastStatus?.lastReliableLocation || { lat: 40.7128, lng: -74.0060 };
      setText('modalLocation', `${loc.lat}, ${loc.lng}`);
      setText('modalTime', new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    }

    async function confirmEmergency() {
      try {
        const data = await fetchJson('/emergency/demo', { method: 'POST' });
        document.getElementById('sosModal').classList.remove('open');
        if (data.success) await loadStatus();
      } catch (error) {
        console.error(error);
      }
    }

    async function addContact(event) {
      event.preventDefault();
      const name = document.getElementById('nameInput').value.trim();
      const relationship = document.getElementById('relationshipInput').value.trim();
      const phone = document.getElementById('phoneInput').value.trim();

      if (!name || !relationship || !phone) return;

      try {
        const data = await fetchJson('/trusted-contacts', {
          method: 'POST',
          body: JSON.stringify({ name, relationship, phone })
        });
        if (data.success) {
          document.getElementById('contactForm').reset();
          await loadContacts();
        }
      } catch (error) {
        console.error(error);
      }
    }

    async function checkInSafe() {
      try {
        const data = await fetchJson('/journey/status', { method: 'POST' });
        if (data.success) await loadStatus();
      } catch (error) {
        console.error(error);
      }
    }

    document.getElementById('startJourneyBtn').addEventListener('click', startJourney);
    document.getElementById('sosBtn').addEventListener('click', openEmergencyModal);
    document.getElementById('sessionSosBtn').addEventListener('click', openEmergencyModal);
    document.getElementById('confirmSosBtn').addEventListener('click', confirmEmergency);
    document.getElementById('cancelSosBtn').addEventListener('click', () => {
      document.getElementById('sosModal').classList.remove('open');
    });

    document.getElementById('gpsFailBtn').addEventListener('click', () => triggerDemo('/demo/gps/failure'));
    document.getElementById('networkFailBtn').addEventListener('click', () => triggerDemo('/demo/network/offline'));
    document.getElementById('networkRecoveryBtn').addEventListener('click', () => triggerDemo('/demo/network/recovery'));
    document.getElementById('batteryLowBtn').addEventListener('click', () => triggerDemo('/demo/battery/low'));
    document.getElementById('batteryCriticalBtn').addEventListener('click', () => triggerDemo('/demo/battery/critical'));
    document.getElementById('resetDemoBtn').addEventListener('click', () => triggerDemo('/demo/reset'));
    document.getElementById('checkinBtn').addEventListener('click', checkInSafe);
    document.getElementById('contactForm').addEventListener('submit', addContact);

    loadStatus();
    loadContacts();
    setInterval(loadStatus, 5000);
  </script>
</body>
</html>
"""


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    APP_STATE["trustedContacts"] = load_contacts()


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return HTML_PAGE


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "SafeWalk AI",
        "timestamp": now_iso(),
        "prototype": True,
    }


@app.get("/safety-status")
def safety_status() -> Dict[str, Any]:
    return get_safety_status_payload()


@app.post("/journey/start")
def journey_start(payload: Dict[str, Any]) -> Dict[str, Any]:
    destination = payload.get("destination", "Downtown Station")
    estimated_arrival = payload.get("estimatedArrival", "19:15")
    APP_STATE["session"] = "Active"
    APP_STATE["journey"] = {
        "destination": destination,
        "status": "Active",
        "currentLocation": f"{APP_STATE['lastReliableLocation']['lat']}, {APP_STATE['lastReliableLocation']['lng']}",
        "safetyStatus": "Monitoring",
        "estimatedArrival": estimated_arrival,
        "startedAt": now_iso(),
    }
    APP_STATE["emergency"] = False
    add_timeline_event("SafeWalk started")
    add_event("Session", f"Journey started to {destination}")
    return {"success": True, "journey": APP_STATE["journey"], "status": get_safety_status_payload()}


@app.post("/journey/status")
@app.get("/journey/status")
def journey_status() -> Dict[str, Any]:
    if APP_STATE["journey"] is None:
        return {"success": False, "message": "No active journey"}
    APP_STATE["journey"]["status"] = "Active"
    APP_STATE["journey"]["safetyStatus"] = "Monitoring"
    APP_STATE["session"] = "Active"
    return {"success": True, "journey": APP_STATE["journey"]}


@app.get("/events")
def events() -> Dict[str, Any]:
    return {
        "events": load_events(),
        "timeline": APP_STATE["timeline"],
        "queuedEvents": APP_STATE["queuedEvents"],
    }


@app.get("/trusted-contacts")
def get_contacts() -> Dict[str, Any]:
    contacts = load_contacts()
    APP_STATE["trustedContacts"] = contacts
    return {"contacts": contacts}


@app.post("/trusted-contacts")
def create_contact(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    relationship = (payload.get("relationship") or "").strip()
    phone = (payload.get("phone") or "").strip()
    if not name or not relationship or not phone:
        raise HTTPException(status_code=400, detail="Name, relationship and phone are required.")
    contact = {"name": name, "relationship": relationship, "phone": phone}
    persist_contact(contact)
    APP_STATE["trustedContacts"] = load_contacts()
    add_event("Contact", f"Trusted contact added: {name}")
    return {"success": True, "contacts": APP_STATE["trustedContacts"]}


@app.post("/emergency/demo")
def emergency_demo() -> Dict[str, Any]:
    APP_STATE["emergency"] = True
    APP_STATE["session"] = "Emergency"
    APP_STATE["journey"] = APP_STATE["journey"] or {
        "destination": "Demo route",
        "status": "Emergency",
        "currentLocation": f"{APP_STATE['lastReliableLocation']['lat']}, {APP_STATE['lastReliableLocation']['lng']}",
        "safetyStatus": "Emergency",
        "estimatedArrival": "—",
        "startedAt": now_iso(),
    }
    add_timeline_event("Simulated emergency alert")
    add_event("Emergency", "DEMO — No real emergency message has been sent.")
    add_event("Contact", "Trusted contact notified with demo data.")
    return {"success": True, "message": "Demo emergency alert sent to trusted contacts (simulated only).", "status": get_safety_status_payload()}


@app.post("/demo/gps/failure")
def simulate_gps_failure() -> Dict[str, Any]:
    APP_STATE["gps"] = "Unavailable"
    APP_STATE["journey"] = APP_STATE["journey"] or {"destination": "Demo route", "status": "Active"}
    APP_STATE["journey"]["currentLocation"] = f"{APP_STATE['lastReliableLocation']['lat']}, {APP_STATE['lastReliableLocation']['lng']}"
    APP_STATE["journey"]["safetyStatus"] = "Fallback mode"
    add_timeline_event("GPS lost")
    add_timeline_event("Last reliable location stored")
    add_event("GPS", "GPS unavailable — using last reliable location")
    return {"success": True, "status": get_safety_status_payload()}


@app.post("/demo/network/offline")
def simulate_network_failure() -> Dict[str, Any]:
    APP_STATE["network"] = "Offline"
    APP_STATE["session"] = "Offline Safety Mode"
    APP_STATE["journey"] = APP_STATE["journey"] or {"destination": "Demo route", "status": "Active"}
    APP_STATE["journey"]["safetyStatus"] = "Offline Safety Mode"
    queue_local_event("Network lost — events queued locally")
    add_timeline_event("Network unavailable")
    add_timeline_event("Entered Offline Safety Mode")
    add_event("Network", "Offline Safety Mode — events queued locally")
    return {"success": True, "status": get_safety_status_payload()}


@app.post("/demo/network/recovery")
def simulate_network_recovery() -> Dict[str, Any]:
    APP_STATE["network"] = "Connected"
    APP_STATE["session"] = "Recovered"
    APP_STATE["journey"] = APP_STATE["journey"] or {"destination": "Demo route", "status": "Recovered"}
    APP_STATE["journey"]["status"] = "Recovered"
    APP_STATE["journey"]["safetyStatus"] = "Monitoring"
    clear_local_queue()
    add_timeline_event("Network restored")
    add_timeline_event("Safety session recovered")
    add_event("Recovery", "Network restored — queued events synchronized")
    return {"success": True, "status": get_safety_status_payload()}


@app.post("/demo/battery/low")
def simulate_low_battery() -> Dict[str, Any]:
    APP_STATE["battery"] = 22
    APP_STATE["session"] = "Battery Awareness"
    add_timeline_event("Battery below 30% — Battery Awareness")
    add_event("Battery", "Battery below 30% — Battery Awareness")
    return {"success": True, "status": get_safety_status_payload()}


@app.post("/demo/battery/critical")
def simulate_critical_battery() -> Dict[str, Any]:
    APP_STATE["battery"] = 4
    APP_STATE["session"] = "Critical Safety Mode"
    add_timeline_event("Battery below 5% — Critical Safety Mode")
    add_event("Battery", "Critical Safety Mode — prioritize emergency information")
    return {"success": True, "status": get_safety_status_payload()}


@app.post("/demo/reset")
def reset_demo() -> Dict[str, Any]:
    APP_STATE["network"] = "Connected"
    APP_STATE["gps"] = "Reliable"
    APP_STATE["battery"] = 72
    APP_STATE["session"] = "Inactive"
    APP_STATE["journey"] = None
    APP_STATE["queuedEvents"] = []
    APP_STATE["emergency"] = False
    APP_STATE["timeline"] = [
        {"time": "14:30", "event": "Full Protection"},
        {"time": "14:34", "event": "GPS signal weakened"},
        {"time": "14:34", "event": "Switched to Degraded Protection"},
        {"time": "14:37", "event": "Network unavailable"},
        {"time": "14:37", "event": "Entered Offline Safety Mode"},
        {"time": "14:40", "event": "Network restored"},
        {"time": "14:40", "event": "Safety session recovered"},
    ]
    add_event("Reset", "Demo reset to system start state")
    return {"success": True, "status": get_safety_status_payload()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

