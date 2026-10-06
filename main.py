from __future__ import annotations

import sqlite3
import random
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

# Simulated GPS coordinates for demo
DEMO_LOCATIONS = [
    {"lat": 40.7128, "lng": -74.0060, "name": "New York, NY"},
    {"lat": 34.0522, "lng": -118.2437, "name": "Los Angeles, CA"},
    {"lat": 41.8781, "lng": -87.6298, "name": "Chicago, IL"},
    {"lat": 29.7604, "lng": -95.3698, "name": "Houston, TX"},
]

APP_STATE: Dict[str, Any] = {
    "network": "Connected",
    "gps": "Reliable",
    "battery": 72,
    "session": "Inactive",
    "lastReliableLocation": random.choice(DEMO_LOCATIONS),
    "journey": None,
    "queuedEvents": [],
    "timeline": [],
    "emergency": False,
    "trustedContacts": [],
    "safetyHistory": [],
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
    APP_STATE["safetyHistory"].append({
        "time": now_clock(),
        "type": type_,
        "message": message,
    })


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

    if critical_count > 0:
        return "EMERGENCY MODE"
    if degraded_count >= 2:
        return "LIMITED PROTECTION"
    if degraded_count == 1:
        return "DEGRADED PROTECTION"
    return "FULL PROTECTION"


def get_safety_status_payload() -> Dict[str, Any]:
    overall = get_overall_state()
    mode_explanations = {
        "FULL PROTECTION": "🟢 All important services available.",
        "DEGRADED PROTECTION": "🟡 One service has reduced reliability. System continues in fallback mode.",
        "LIMITED PROTECTION": "🟠 Multiple systems degraded. Prioritizing essential safety functions.",
        "EMERGENCY MODE": "🔴 Critical capability unavailable or emergency triggered.",
    }

    gps_label = {
        "Unavailable": "GPS unavailable — using last reliable location",
        "Weak": "Location signal weak",
        "Reliable": "Location reliable",
    }.get(APP_STATE["gps"], "Location status unknown")

    return {
        "overallState": overall,
        "network": APP_STATE["network"],
        "gps": APP_STATE["gps"],
        "battery": APP_STATE["battery"],
        "batteryMode": current_battery_mode(),
        "session": APP_STATE["session"],
        "journey": APP_STATE["journey"],
        "lastReliableLocation": APP_STATE["lastReliableLocation"],
        "gpsLabel": gps_label,
        "queuedEvents": APP_STATE["queuedEvents"],
        "timeline": APP_STATE["timeline"],
        "safetyHistory": APP_STATE["safetyHistory"][-10:],
        "emergency": APP_STATE["emergency"],
        "modeExplanation": mode_explanations.get(overall, "System status unknown."),
    }


def queue_local_event(message: str) -> None:
    APP_STATE["queuedEvents"].append({"at": now_clock(), "message": message})


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

    .container {
      max-width: 1100px;
      margin: 0 auto;
      padding: 20px 16px 60px;
    }

    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 700;
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
      background: rgba(255, 183, 3, 0.12);
      color: #ffd77b;
      border: 1px solid rgba(255, 183, 3, 0.45);
      border-radius: 999px;
      padding: 7px 10px;
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 700;
    }

    .hero {
      background: linear-gradient(135deg, rgba(76, 201, 240, 0.15), rgba(19, 58, 92, 0.92));
      border: 1px solid var(--border);
      border-radius: 26px;
      padding: 24px;
      margin-bottom: 20px;
      box-shadow: var(--shadow);
    }

    .hero h1 {
      margin: 0 0 8px;
      font-size: clamp(2rem, 7vw, 3.2rem);
      line-height: 1.08;
    }

    .tagline {
      margin: 0 0 16px;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.5;
    }

    .hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
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
    .btn:hover { transform: translateY(-2px); box-shadow: 0 12px 24px rgba(0,0,0,0.2); }
    .btn.primary { background: linear-gradient(135deg, var(--primary), #6bdcff); }
    .btn.warning { background: linear-gradient(135deg, #ff9f43, #ff7b54); color: white; }
    .btn.danger { background: linear-gradient(135deg, var(--danger), #ff3b4d); color: white; }
    .btn.secondary { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); }
    .btn.ghost { background: transparent; border: 1px solid var(--border); }

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
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }

    .card h2 { margin: 0; }

    .status-badge {
      display: inline-block;
      border-radius: 999px;
      padding: 8px 14px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
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
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 7px;
    }

    .metric-value {
      font-size: clamp(1.15rem, 5vw, 1.65rem);
      font-weight: 800;
    }

    .info-list {
      display: grid;
      gap: 12px;
      margin-top: 12px;
    }

    .info-row {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .info-row:last-child { border-bottom: 0; }

    .muted { color: var(--muted); }

    .demo-controls {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }

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
      font-size: 14px;
    }

    .timeline .time {
      color: var(--text);
      font-weight: 700;
      margin-right: 8px;
    }

    .contact-list, .history-list {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }

    .contact-item, .history-item {
      background: rgba(255,255,255,0.02);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 12px;
      padding: 12px 14px;
      font-size: 14px;
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

    .modal {
      position: fixed;
      inset: 0;
      background: rgba(4, 14, 28, 0.8);
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
      padding: 22px 18px;
      box-shadow: var(--shadow);
    }

    .modal h3 { margin: 0 0 12px; font-size: 1.5rem; }
    .modal p { margin: 0 0 12px; }

    .modal-actions {
      display: flex;
      gap: 10px;
      justify-content: flex-end;
      margin-top: 18px;
    }

    .success-msg {
      background: rgba(57, 217, 138, 0.12);
      border: 1px solid rgba(57, 217, 138, 0.4);
      color: #80edb2;
      border-radius: 10px;
      padding: 12px 14px;
      margin-top: 12px;
      font-size: 14px;
    }

    @media (min-width: 768px) {
      .grid { grid-template-columns: 1.3fr 1fr; }
      .demo-controls { grid-template-columns: repeat(3, minmax(0, 1fr)); }
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
      <h1>Safety that continues when technology doesn't.</h1>
      <p class="tagline">SafeWalk AI continuously checks whether the safety system itself is functioning and automatically adapts when network, GPS, battery, or connectivity becomes unreliable.</p>
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
          <div class="info-list">
            <div class="info-row">
              <span class="muted">Current Location</span>
              <strong id="currentLocationText">40.7128, -74.0060</strong>
            </div>
            <div class="info-row">
              <span class="muted">Safety Session</span>
              <strong id="sessionText">Inactive</strong>
            </div>
            <div class="info-row">
              <span class="muted">Status Explanation</span>
              <strong id="explainText">All important services available.</strong>
            </div>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>SafeWalk Active Session</h2>
          </div>
          <div class="info-list">
            <div class="info-row">
              <span class="muted">Destination</span>
              <strong id="destinationText">Not started</strong>
            </div>
            <div class="info-row">
              <span class="muted">Journey Time</span>
              <strong id="timerText">00:00</strong>
            </div>
            <div class="info-row">
              <span class="muted">Journey Status</span>
              <strong id="journeyStateText">Standby</strong>
            </div>
            <div class="info-row">
              <span class="muted">Estimated Arrival</span>
              <strong id="etaText">—</strong>
            </div>
          </div>
          <div class="hero-actions" style="margin-top: 12px;">
            <button class="btn secondary" id="checkinBtn">I'm Safe (Check-in)</button>
            <button class="btn danger" id="sessionSosBtn">Emergency</button>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <h2>Safety Timeline</h2>
          <ul id="timelineList" class="timeline"></ul>
        </section>
      </main>

      <aside>
        <section class="card">
          <h2>Developer Demo Controls</h2>
          <p class="muted">Click a button to simulate system state changes in real-time.</p>
          <div class="demo-controls">
            <button class="btn warning" id="gpsFailBtn">📡 GPS Failure</button>
            <button class="btn warning" id="networkFailBtn">🌐 Network Down</button>
            <button class="btn primary" id="networkRecoveryBtn">✅ Recover Network</button>
            <button class="btn secondary" id="batteryLowBtn">🔋 Low Battery</button>
            <button class="btn secondary" id="batteryCriticalBtn">⚠️ Critical Battery</button>
            <button class="btn ghost" id="resetDemoBtn">🔄 Reset All</button>
          </div>
          <div id="feedbackMsg"></div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <h2>System Health</h2>
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
              <strong id="batteryDetail">Normal (72%)</strong>
            </div>
            <div class="info-row">
              <span class="muted">Queued Events</span>
              <strong id="queueDetail">0 events</strong>
            </div>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <h2>Trusted Contacts</h2>
          <form id="contactForm" class="form-grid">
            <input type="text" id="nameInput" placeholder="Name" required />
            <input type="text" id="relationshipInput" placeholder="Relationship" required />
            <input type="tel" id="phoneInput" placeholder="Phone" required />
            <button class="btn primary" type="submit">Add Contact</button>
          </form>
          <div id="contactList" class="contact-list"></div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <h2>Safety History</h2>
          <div id="historyList" class="history-list"></div>
        </section>
      </aside>
    </div>
  </div>

  <div id="sosModal" class="modal">
    <div class="modal-card">
      <h3>🚨 Emergency Demo Alert</h3>
      <p class="muted"><strong>DEMO MODE</strong> — No real emergency has been sent.</p>
      <div class="info-list">
        <div class="info-row">
          <span class="muted">Location</span>
          <strong id="modalLocation">—</strong>
        </div>
        <div class="info-row">
          <span class="muted">Time</span>
          <strong id="modalTime">—</strong>
        </div>
      </div>
      <div class="modal-actions">
        <button class="btn ghost" id="cancelSosBtn">Cancel</button>
        <button class="btn danger" id="confirmSosBtn">Confirm Alert</button>
      </div>
    </div>
  </div>

  <script>
    const state = {
      timerSeconds: 0,
      timerInterval: null,
      lastStatus: null,
      isJourneyActive: false,
    };

    function showFeedback(message, type = 'success') {
      const el = document.getElementById('feedbackMsg');
      el.innerHTML = `<div class="success-msg">${message}</div>`;
      setTimeout(() => { el.innerHTML = ''; }, 3000);
    }

    function setBadge(el, status) {
      el.className = 'status-badge';
      if (status === 'FULL PROTECTION') el.classList.add('status-full');
      else if (status === 'DEGRADED PROTECTION') el.classList.add('status-degraded');
      else if (status === 'LIMITED PROTECTION') el.classList.add('status-limited');
      else if (status === 'EMERGENCY MODE') el.classList.add('status-emergency');
      el.textContent = status;
    }

    function setText(id, value) {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    }

    function startTimer() {
      if (state.timerInterval) clearInterval(state.timerInterval);
      state.timerInterval = setInterval(() => {
        state.timerSeconds += 1;
        const mins = Math.floor(state.timerSeconds / 60).toString().padStart(2, '0');
        const secs = (state.timerSeconds % 60).toString().padStart(2, '0');
        setText('timerText', `${mins}:${secs}`);
      }, 1000);
    }

    function stopTimer() {
      if (state.timerInterval) {
        clearInterval(state.timerInterval);
        state.timerInterval = null;
      }
      state.timerSeconds = 0;
    }

    function renderTimeline(items) {
      const list = document.getElementById('timelineList');
      list.innerHTML = '';
      if (!items || items.length === 0) {
        list.innerHTML = '<li style="color: var(--muted);">No events yet.</li>';
        return;
      }
      [...items].reverse().forEach((item) => {
        const li = document.createElement('li');
        li.innerHTML = `<span class="time">${item.time}</span> ${item.event}`;
        list.appendChild(li);
      });
    }

    function renderHistory(items) {
      const list = document.getElementById('historyList');
      list.innerHTML = '';
      if (!items || items.length === 0) {
        list.innerHTML = '<div class="history-item">No history yet.</div>';
        return;
      }
      [...items].reverse().slice(0, 8).forEach((item) => {
        const div = document.createElement('div');
        div.className = 'history-item';
        div.innerHTML = `<strong>${item.type}</strong> (${item.time})<br /><span class="muted">${item.message}</span>`;
        list.appendChild(div);
      });
    }

    function renderContacts(items) {
      const list = document.getElementById('contactList');
      list.innerHTML = '';
      if (!items || items.length === 0) {
        list.innerHTML = '<div class="contact-item">No contacts yet.</div>';
        return;
      }
      items.forEach((contact) => {
        const div = document.createElement('div');
        div.className = 'contact-item';
        div.innerHTML = `<strong>${contact.name}</strong><br /><span class="muted">${contact.relationship} • ${contact.phone}</span>`;
        list.appendChild(div);
      });
    }

    async function fetchApi(url, method = 'GET', body = null) {
      const options = { method, headers: { 'Content-Type': 'application/json' } };
      if (body) options.body = JSON.stringify(body);
      const response = await fetch(url, options);
      if (!response.ok) throw new Error(`${response.status}`);
      return await response.json();
    }

    async function loadStatus() {
      try {
        const data = await fetchApi('/safety-status');
        state.lastStatus = data;

        const overall = data.overallState || 'FULL PROTECTION';
        setBadge(document.getElementById('overallBadge'), overall);

        setText('journeyStatusText', data.journey ? data.journey.status : 'Inactive');
        setText('gpsStatusText', data.gps || 'Reliable');
        setText('networkStatusText', data.network || 'Connected');
        setText('batteryStatusText', `${data.battery}%`);
        setText('currentLocationText', data.lastReliableLocation ? `${data.lastReliableLocation.lat}, ${data.lastReliableLocation.lng}` : 'Unknown');
        setText('sessionText', data.session || 'Inactive');
        setText('explainText', data.modeExplanation || 'System status unknown.');

        setText('networkDetail', data.network);
        setText('gpsDetail', data.gps);
        setText('batteryDetail', `${data.batteryMode} (${data.battery}%)`);
        setText('queueDetail', `${data.queuedEvents.length} events queued`);

        if (data.journey) {
          setText('destinationText', data.journey.destination);
          setText('journeyStateText', data.journey.safetyStatus);
          setText('etaText', data.journey.estimatedArrival || '—');
          if (!state.isJourneyActive && data.journey.status === 'Active') {
            state.isJourneyActive = true;
            state.timerSeconds = 0;
            startTimer();
          }
        } else {
          setText('destinationText', 'Not started');
          setText('journeyStateText', 'Standby');
          setText('etaText', '—');
          setText('timerText', '00:00');
          state.isJourneyActive = false;
          stopTimer();
        }

        renderTimeline(data.timeline);
        renderHistory(data.safetyHistory);
      } catch (error) {
        console.error('Load status error:', error);
      }
    }

    async function loadContacts() {
      try {
        const data = await fetchApi('/trusted-contacts');
        renderContacts(data.contacts || []);
      } catch (error) {
        console.error('Load contacts error:', error);
      }
    }

    async function startJourney() {
      try {
        await fetchApi('/journey/start', 'POST', { destination: 'Downtown Station', estimatedArrival: '19:15' });
        showFeedback('✅ SafeWalk journey started! Now monitoring your safety.');
        await loadStatus();
      } catch (error) {
        showFeedback('❌ Failed to start journey', 'error');
      }
    }

    async function triggerDemo(endpoint, name) {
      try {
        await fetchApi(endpoint, 'POST');
        showFeedback(`✅ ${name}`);
        await loadStatus();
      } catch (error) {
        showFeedback(`❌ ${name} failed`, 'error');
      }
    }

    function openSosModal() {
      const modal = document.getElementById('sosModal');
      modal.classList.add('open');
      const loc = state.lastStatus?.lastReliableLocation || { lat: 0, lng: 0 };
      setText('modalLocation', `${loc.lat}, ${loc.lng}`);
      setText('modalTime', new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    }

    async function confirmSos() {
      try {
        await fetchApi('/emergency/demo', 'POST');
        document.getElementById('sosModal').classList.remove('open');
        showFeedback('🚨 Emergency demo alert sent!');
        await loadStatus();
      } catch (error) {
        showFeedback('❌ Failed to send alert', 'error');
      }
    }

    async function addContact(e) {
      e.preventDefault();
      const name = document.getElementById('nameInput').value.trim();
      const relationship = document.getElementById('relationshipInput').value.trim();
      const phone = document.getElementById('phoneInput').value.trim();
      if (!name || !relationship || !phone) return;
      try {
        await fetchApi('/trusted-contacts', 'POST', { name, relationship, phone });
        document.getElementById('contactForm').reset();
        showFeedback(`✅ Contact ${name} added`);
        await loadContacts();
      } catch (error) {
        showFeedback('❌ Failed to add contact', 'error');
      }
    }

    async function checkInSafe() {
      try {
        await fetchApi('/journey/status', 'POST');
        showFeedback('✅ Check-in received. Stay safe!');
        await loadStatus();
      } catch (error) {
        showFeedback('❌ Check-in failed', 'error');
      }
    }

    document.getElementById('startJourneyBtn').addEventListener('click', startJourney);
    document.getElementById('sosBtn').addEventListener('click', openSosModal);
    document.getElementById('sessionSosBtn').addEventListener('click', openSosModal);
    document.getElementById('confirmSosBtn').addEventListener('click', confirmSos);
    document.getElementById('cancelSosBtn').addEventListener('click', () => {
      document.getElementById('sosModal').classList.remove('open');
    });

    document.getElementById('gpsFailBtn').addEventListener('click', () => triggerDemo('/demo/gps/failure', '📡 GPS Failure Simulated'));
    document.getElementById('networkFailBtn').addEventListener('click', () => triggerDemo('/demo/network/offline', '🌐 Network Offline Simulated'));
    document.getElementById('networkRecoveryBtn').addEventListener('click', () => triggerDemo('/demo/network/recovery', '✅ Network Recovered'));
    document.getElementById('batteryLowBtn').addEventListener('click', () => triggerDemo('/demo/battery/low', '🔋 Low Battery Mode'));
    document.getElementById('batteryCriticalBtn').addEventListener('click', () => triggerDemo('/demo/battery/critical', '⚠️ Critical Battery Mode'));
    document.getElementById('resetDemoBtn').addEventListener('click', () => triggerDemo('/demo/reset', '🔄 Demo Reset'));
    document.getElementById('checkinBtn').addEventListener('click', checkInSafe);
    document.getElementById('contactForm').addEventListener('submit', addContact);

    loadStatus();
    loadContacts();
    setInterval(loadStatus, 2000);
  </script>
</body>
</html>
"""


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    APP_STATE["trustedContacts"] = load_contacts()
    add_timeline_event("SafeWalk AI Started")


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return HTML_PAGE


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "SafeWalk AI",
        "timestamp": now_iso(),
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
    }
    add_timeline_event(f"Journey started to {destination}")
    add_event("Journey", f"SafeWalk started: {destination}")
    return {"success": True}


@app.post("/journey/status")
@app.get("/journey/status")
def journey_status() -> Dict[str, Any]:
    if not APP_STATE["journey"]:
        return {"success": False}
    add_event("Check-in", "User confirmed safety at this location")
    return {"success": True}


@app.get("/trusted-contacts")
def get_contacts() -> Dict[str, Any]:
    return {"contacts": load_contacts()}


@app.post("/trusted-contacts")
def create_contact(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    relationship = (payload.get("relationship") or "").strip()
    phone = (payload.get("phone") or "").strip()
    if not name or not relationship or not phone:
        raise HTTPException(status_code=400, detail="All fields required")
    persist_contact({"name": name, "relationship": relationship, "phone": phone})
    add_event("Contact", f"Added trusted contact: {name}")
    return {"success": True}


@app.post("/emergency/demo")
def emergency_demo() -> Dict[str, Any]:
    APP_STATE["emergency"] = True
    APP_STATE["session"] = "Emergency"
    add_timeline_event("🚨 EMERGENCY ALERT (Demo)")
    add_event("Emergency", "DEMO: Emergency alert triggered and sent to contacts")
    return {"success": True}


@app.post("/demo/gps/failure")
def gps_failure() -> Dict[str, Any]:
    APP_STATE["gps"] = "Unavailable"
    APP_STATE["lastReliableLocation"] = APP_STATE["lastReliableLocation"]
    add_timeline_event("GPS signal lost — using last reliable location")
    add_event("GPS", "GPS unavailable — fallback to last known location")
    return {"success": True}


@app.post("/demo/network/offline")
def network_offline() -> Dict[str, Any]:
    APP_STATE["network"] = "Offline"
    APP_STATE["session"] = "Offline Safety Mode"
    queue_local_event("Network connection lost")
    add_timeline_event("Network went offline — Offline Safety Mode activated")
    add_event("Network", "Offline Safety Mode: queuing events locally")
    return {"success": True}


@app.post("/demo/network/recovery")
def network_recovery() -> Dict[str, Any]:
    APP_STATE["network"] = "Connected"
    queued = len(APP_STATE["queuedEvents"])
    clear_local_queue()
    add_timeline_event(f"Network restored — synced {queued} queued events")
    add_event("Recovery", f"Network recovered and synchronized {queued} events")
    return {"success": True}


@app.post("/demo/battery/low")
def battery_low() -> Dict[str, Any]:
    APP_STATE["battery"] = 22
    add_timeline_event("Battery below 30% — Battery Awareness Mode")
    add_event("Battery", "Battery Awareness Mode activated at 22%")
    return {"success": True}


@app.post("/demo/battery/critical")
def battery_critical() -> Dict[str, Any]:
    APP_STATE["battery"] = 4
    add_timeline_event("Battery critical (4%) — Critical Safety Mode")
    add_event("Battery", "Critical Battery Mode: preserving essential functions")
    return {"success": True}


@app.post("/demo/reset")
def reset_demo() -> Dict[str, Any]:
    APP_STATE["network"] = "Connected"
    APP_STATE["gps"] = "Reliable"
    APP_STATE["battery"] = 72
    APP_STATE["session"] = "Inactive"
    APP_STATE["journey"] = None
    APP_STATE["queuedEvents"] = []
    APP_STATE["emergency"] = False
    APP_STATE["lastReliableLocation"] = random.choice(DEMO_LOCATIONS)
    APP_STATE["timeline"] = []
    add_timeline_event("Demo reset — system back to normal")
    add_event("Reset", "Demo reset to initial state")
    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
