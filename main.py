from __future__ import annotations

import random
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

DEMO_LOCATIONS = [
    {"lat": 40.7128, "lng": -74.0060, "label": "New York, NY"},
    {"lat": 34.0522, "lng": -118.2437, "label": "Los Angeles, CA"},
    {"lat": 41.8781, "lng": -87.6298, "label": "Chicago, IL"},
    {"lat": 29.7604, "lng": -95.3698, "label": "Houston, TX"},
]

APP_STATE: Dict[str, Any] = {
    "network": "Connected",
    "gps": "Reliable",
    "battery": 72,
    "session": "Inactive",
    "journey": None,
    "lastReliableLocation": {"lat": 40.7128, "lng": -74.0060, "label": "Demo Location"},
    "queuedEvents": [],
    "timeline": [
        {"time": "09:00", "event": "System booted and health checks passed."},
        {"time": "09:03", "event": "GPS and network are stable."},
    ],
    "safetyHistory": [
        {"time": "09:00", "type": "Startup", "message": "SafeWalk AI ready."},
        {"time": "09:03", "type": "Status", "message": "Full protection active."},
    ],
    "emergency": False,
    "trustedContacts": [],
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
    APP_STATE["safetyHistory"].append({"time": now_clock(), "type": type_, "message": message})


def add_timeline_event(event: str) -> None:
    APP_STATE["timeline"].append({"time": now_clock(), "event": event})


def get_overall_state() -> str:
    if APP_STATE["emergency"]:
        return "EMERGENCY MODE"
    if APP_STATE["network"] == "Offline" or APP_STATE["gps"] == "Unavailable":
        if APP_STATE["battery"] <= 5:
            return "EMERGENCY MODE"
        return "LIMITED PROTECTION"
    if APP_STATE["battery"] <= 30 or APP_STATE["session"] in {"Offline Safety Mode", "Battery Awareness", "Critical Safety Mode"}:
        return "DEGRADED PROTECTION"
    return "FULL PROTECTION"


def get_status_payload() -> Dict[str, Any]:
    overall = get_overall_state()
    mode_explanations = {
        "FULL PROTECTION": "All services are healthy and active.",
        "DEGRADED PROTECTION": "One or more safety systems are reduced but still stable.",
        "LIMITED PROTECTION": "A key system is unavailable, so recovery and fallback mode are active.",
        "EMERGENCY MODE": "A critical safety issue has been detected or simulated.",
    }
    return {
        "overallState": overall,
        "network": APP_STATE["network"],
        "gps": APP_STATE["gps"],
        "battery": APP_STATE["battery"],
        "batteryMode": "Critical" if APP_STATE["battery"] <= 5 else "Battery Awareness" if APP_STATE["battery"] <= 30 else "Normal",
        "session": APP_STATE["session"],
        "journey": APP_STATE["journey"],
        "lastReliableLocation": APP_STATE["lastReliableLocation"],
        "queuedEvents": APP_STATE["queuedEvents"],
        "timeline": APP_STATE["timeline"],
        "safetyHistory": APP_STATE["safetyHistory"][-10:],
        "emergency": APP_STATE["emergency"],
        "modeExplanation": mode_explanations.get(overall, "System status unknown."),
    }


def queue_local_event(message: str) -> None:
    APP_STATE["queuedEvents"].append({"time": now_clock(), "message": message})


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
  <meta name="viewport" content="width=device-width,initial-scale=1.0" />
  <title>SafeWalk AI</title>
  <style>
    :root {
      --bg: #071a2d;
      --panel: #0e233c;
      --card: rgba(18,45,79,0.92);
      --border: rgba(125,178,255,0.25);
      --text: #edf6ff;
      --muted: #a9bedf;
      --primary: #4cc9f0;
      --success: #39d98a;
      --warning: #ffb703;
      --danger: #ff5d73;
      --shadow: 0 18px 40px rgba(0,0,0,0.25);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, Segoe UI, sans-serif;
      background: linear-gradient(180deg, #071a2d 0%, #0d2140 100%);
      color: var(--text);
    }
    .container { max-width: 1100px; margin: 0 auto; padding: 20px 16px 60px; }
    .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
    .brand { display: flex; align-items: center; gap: 12px; font-weight: 700; }
    .brand-badge {
      width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center;
      background: linear-gradient(135deg, var(--primary), #55d6d7); color: #062135; font-weight: 800;
      box-shadow: var(--shadow);
    }
    .prototype-pill {
      background: rgba(255,183,3,0.12); border: 1px solid rgba(255,183,3,0.45); color: #ffd77b;
      border-radius: 999px; padding: 7px 10px; font-size: 11px; letter-spacing: 0.06em; font-weight: 700; text-transform: uppercase;
    }
    .hero {
      background: linear-gradient(135deg, rgba(76,201,240,0.15), rgba(19,58,92,0.92)); border: 1px solid var(--border);
      border-radius: 26px; box-shadow: var(--shadow); padding: 24px 18px; margin-bottom: 18px;
    }
    .hero h1 { margin: 0 0 8px; font-size: clamp(2rem, 7vw, 3.2rem); line-height: 1.08; }
    .tagline { margin: 0; color: var(--muted); font-size: 1rem; line-height: 1.5; }
    .hero-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 16px; }
    .btn {
      border: 0; border-radius: 14px; padding: 12px 18px; font-weight: 700; cursor: pointer;
      transition: 0.2s ease; box-shadow: 0 8px 18px rgba(0,0,0,0.16);
    }
    .btn:hover { transform: translateY(-1px); }
    .btn.primary { background: linear-gradient(135deg, var(--primary), #6bdcff); color: #062035; }
    .btn.warning { background: linear-gradient(135deg, #ff9f43, #ff7b54); color: white; }
    .btn.danger { background: linear-gradient(135deg, var(--danger), #ff3b4d); color: white; }
    .btn.secondary { background: rgba(255,255,255,0.08); color: var(--text); border: 1px solid rgba(255,255,255,0.12); }
    .btn.ghost { background: transparent; color: var(--text); border: 1px solid var(--border); }
    .grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
    .card {
      background: rgba(18,45,79,0.88); border: 1px solid var(--border); border-radius: 20px;
      padding: 18px; box-shadow: var(--shadow);
    }
    .card-header {
      display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 16px;
    }
    .card h2 { margin: 0; }
    .status-badge {
      display: inline-flex; align-items: center; justify-content: center; border-radius: 999px; padding: 7px 12px;
      font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; border: 1px solid transparent;
    }
    .status-full { background: rgba(57,217,138,0.12); color: #80edb2; border-color: rgba(57,217,138,0.4); }
    .status-degraded { background: rgba(255,183,3,0.12); color: #ffd76a; border-color: rgba(255,183,3,0.4); }
    .status-limited { background: rgba(255,120,78,0.12); color: #ffc08a; border-color: rgba(255,120,78,0.4); }
    .status-emergency { background: rgba(255,93,115,0.12); color: #ffb7c0; border-color: rgba(255,93,115,0.5); }
    .stat-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .metric { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 14px 12px; }
    .metric-label { display: block; color: var(--muted); font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 7px; }
    .metric-value { font-size: clamp(1.15rem, 5vw, 1.65rem); font-weight: 800; }
    .info-list { display: grid; gap: 10px; margin-top: 12px; }
    .info-row { display: flex; justify-content: space-between; gap: 12px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 8px; }
    .info-row:last-child { border-bottom: 0; }
    .muted { color: var(--muted); }
    .demo-controls { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
    .timeline { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
    .timeline li { border-left: 2px solid rgba(76,201,240,0.5); padding-left: 12px; color: var(--muted); }
    .timeline .time { color: var(--text); font-weight: 700; margin-right: 8px; }
    .list-card { display: grid; gap: 10px; margin-top: 12px; }
    .item { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; padding: 12px 14px; }
    .form-grid { display: grid; gap: 10px; margin-top: 12px; }
    .form-grid input {
      width: 100%; background: rgba(255,255,255,0.04); color: var(--text); border: 1px solid rgba(255,255,255,0.08);
      border-radius: 10px; padding: 12px 14px; font: inherit;
    }
    .form-grid input::placeholder { color: #98afd0; }
    .feedback {
      margin-top: 12px; background: rgba(57,217,138,0.12); border: 1px solid rgba(57,217,138,0.4); color: #80edb2;
      border-radius: 12px; padding: 12px 14px; font-size: 14px; display: none;
    }
    .feedback.show { display: block; }
    .modal { position: fixed; inset: 0; background: rgba(4,14,28,0.8); display: none; align-items: center; justify-content: center; padding: 16px; z-index: 50; }
    .modal.open { display: flex; }
    .modal-card { width: min(100%, 420px); background: #0d2140; border: 1px solid var(--border); border-radius: 22px; padding: 22px 18px; box-shadow: var(--shadow); }
    .modal h3 { margin: 0 0 12px; font-size: 1.5rem; }
    .modal p { margin: 0 0 12px; }
    .modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 18px; }
    @media (min-width: 768px) { .grid { grid-template-columns: 1.3fr 1fr; } .demo-controls { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
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
      <p class="tagline">SafeWalk AI checks whether the safety system itself is healthy and automatically falls back when GPS, network, or battery conditions degrade.</p>
      <div class="hero-actions">
        <button class="btn primary" id="startJourneyBtn">Start SafeWalk</button>
        <button class="btn danger" id="sosBtn">Emergency SOS</button>
        <button class="btn secondary" id="useLocationBtn">Use My Location</button>
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
              <span class="metric-label">Journey</span>
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
              <span class="muted">Session</span>
              <strong id="sessionText">Inactive</strong>
            </div>
            <div class="info-row">
              <span class="muted">System Explanation</span>
              <strong id="explainText">All services are healthy and active.</strong>
            </div>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>SafeWalk Journey</h2>
          </div>
          <div class="info-list">
            <div class="info-row">
              <span class="muted">Destination</span>
              <strong id="destinationText">Not started</strong>
            </div>
            <div class="info-row">
              <span class="muted">Timer</span>
              <strong id="timerText">00:00</strong>
            </div>
            <div class="info-row">
              <span class="muted">Journey State</span>
              <strong id="journeyStateText">Standby</strong>
            </div>
            <div class="info-row">
              <span class="muted">ETA</span>
              <strong id="etaText">—</strong>
            </div>
          </div>
          <div class="hero-actions" style="margin-top: 12px;">
            <button class="btn secondary" id="checkinBtn">I’m Safe</button>
            <button class="btn danger" id="sessionSosBtn">Emergency</button>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>Explainable Safety Timeline</h2>
          </div>
          <ul id="timelineList" class="timeline"></ul>
        </section>
      </main>

      <aside>
        <section class="card">
          <div class="card-header">
            <h2>Demo Controls</h2>
          </div>
          <div class="demo-controls">
            <button class="btn warning" id="gpsFailBtn">GPS Failure</button>
            <button class="btn warning" id="networkFailBtn">Network Down</button>
            <button class="btn primary" id="networkRecoveryBtn">Recover Network</button>
            <button class="btn secondary" id="batteryLowBtn">Low Battery</button>
            <button class="btn secondary" id="batteryCriticalBtn">Critical Battery</button>
            <button class="btn ghost" id="resetDemoBtn">Reset</button>
          </div>
          <div id="feedback" class="feedback"></div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>System Health</h2>
          </div>
          <div class="info-list">
            <div class="info-row"><span class="muted">Network</span><strong id="networkDetail">Connected</strong></div>
            <div class="info-row"><span class="muted">GPS</span><strong id="gpsDetail">Reliable</strong></div>
            <div class="info-row"><span class="muted">Battery</span><strong id="batteryDetail">Normal (72%)</strong></div>
            <div class="info-row"><span class="muted">Queued Events</span><strong id="queueDetail">0 events</strong></div>
          </div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>Trusted Contacts</h2>
          </div>
          <form id="contactForm" class="form-grid">
            <input id="nameInput" type="text" placeholder="Name" required />
            <input id="relationshipInput" type="text" placeholder="Relationship" required />
            <input id="phoneInput" type="tel" placeholder="Phone" required />
            <button type="submit" class="btn primary">Add Contact</button>
          </form>
          <div id="contactList" class="list-card"></div>
        </section>

        <section class="card" style="margin-top: 16px;">
          <div class="card-header">
            <h2>Safety History</h2>
          </div>
          <div id="historyList" class="list-card"></div>
        </section>
      </aside>
    </div>
  </div>

  <div id="sosModal" class="modal" aria-hidden="true">
    <div class="modal-card">
      <h3>Emergency Demo</h3>
      <p class="muted">Demo mode only — no real emergency was sent.</p>
      <div class="info-list">
        <div class="info-row"><span class="muted">Location</span><strong id="modalLocation">—</strong></div>
        <div class="info-row"><span class="muted">Time</span><strong id="modalTime">—</strong></div>
      </div>
      <div class="modal-actions">
        <button class="btn ghost" id="cancelSosBtn">Cancel</button>
        <button class="btn danger" id="confirmSosBtn">Confirm Alert</button>
      </div>
    </div>
  </div>

  <script>
    const state = { timerSeconds: 0, timerInterval: null };

    function showFeedback(message) {
      const el = document.getElementById('feedback');
      el.textContent = message;
      el.classList.add('show');
      setTimeout(() => el.classList.remove('show'), 3000);
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
      const node = document.getElementById(id);
      if (node) node.textContent = value;
    }

    function startTimer() {
      if (state.timerInterval) clearInterval(state.timerInterval);
      state.timerInterval = setInterval(() => {
        state.timerSeconds += 1;
        const m = String(Math.floor(state.timerSeconds / 60)).padStart(2, '0');
        const s = String(state.timerSeconds % 60).padStart(2, '0');
        setText('timerText', `${m}:${s}`);
      }, 1000);
    }

    function stopTimer() {
      if (state.timerInterval) clearInterval(state.timerInterval);
      state.timerInterval = null;
      state.timerSeconds = 0;
      setText('timerText', '00:00');
    }

    function renderTimeline(items) {
      const list = document.getElementById('timelineList');
      list.innerHTML = '';
      if (!items || items.length === 0) {
        list.innerHTML = '<li>No events yet.</li>';
        return;
      }
      [...items].reverse().slice(0, 8).forEach((item) => {
        const li = document.createElement('li');
        li.innerHTML = `<span class="time">${item.time}</span> ${item.event}`;
        list.appendChild(li);
      });
    }

    function renderHistory(items) {
      const list = document.getElementById('historyList');
      list.innerHTML = '';
      if (!items || items.length === 0) {
        list.innerHTML = '<div class="item">No history yet.</div>';
        return;
      }
      [...items].reverse().slice(0, 8).forEach((item) => {
        const div = document.createElement('div');
        div.className = 'item';
        div.innerHTML = `<strong>${item.type}</strong> (${item.time})<br /><span class="muted">${item.message}</span>`;
        list.appendChild(div);
      });
    }

    function renderContacts(items) {
      const list = document.getElementById('contactList');
      list.innerHTML = '';
      if (!items || items.length === 0) {
        list.innerHTML = '<div class="item">No contacts added yet.</div>';
        return;
      }
      items.forEach((contact) => {
        const div = document.createElement('div');
        div.className = 'item';
        div.innerHTML = `<strong>${contact.name}</strong><br /><span class="muted">${contact.relationship} • ${contact.phone}</span>`;
        list.appendChild(div);
      });
    }

    async function fetchJson(url, method = 'GET', body = null) {
      const options = { method, headers: { 'Content-Type': 'application/json' } };
      if (body) options.body = JSON.stringify(body);
      const response = await fetch(url, options);
      if (!response.ok) throw new Error(`Request failed: ${response.status}`);
      return response.json();
    }

    async function loadStatus() {
      try {
        const data = await fetchJson('/api/status');
        const overall = data.overallState || 'FULL PROTECTION';
        setBadge(document.getElementById('overallBadge'), overall);
        setText('journeyStatusText', data.journey ? data.journey.status : 'Inactive');
        setText('gpsStatusText', data.gps || 'Reliable');
        setText('networkStatusText', data.network || 'Connected');
        setText('batteryStatusText', `${data.battery || 72}%`);
        setText('currentLocationText', data.lastReliableLocation ? `${data.lastReliableLocation.lat}, ${data.lastReliableLocation.lng}` : 'Unknown');
        setText('sessionText', data.session || 'Inactive');
        setText('explainText', data.modeExplanation || 'All services are healthy and active.');
        setText('networkDetail', data.network || 'Connected');
        setText('gpsDetail', data.gps || 'Reliable');
        setText('batteryDetail', `${data.batteryMode || 'Normal'} (${data.battery || 72}%)`);
        setText('queueDetail', `${(data.queuedEvents || []).length} events`);

        if (data.journey) {
          setText('destinationText', data.journey.destination || 'Not started');
          setText('journeyStateText', data.journey.status || 'Standby');
          setText('etaText', data.journey.estimatedArrival || '—');
          if (data.journey.status === 'Active') {
            startTimer();
          } else {
            stopTimer();
          }
        } else {
          setText('destinationText', 'Not started');
          setText('journeyStateText', 'Standby');
          setText('etaText', '—');
          stopTimer();
        }

        renderTimeline(data.timeline || []);
        renderHistory(data.safetyHistory || []);
      } catch (error) {
        console.error(error);
      }
    }

    async function loadContacts() {
      try {
        const data = await fetchJson('/api/contacts');
        renderContacts(data.contacts || []);
      } catch (error) {
        console.error(error);
      }
    }

    async function startJourney() {
      try {
        const data = await fetchJson('/api/journey/start', 'POST', {
          destination: 'Downtown Station',
          estimatedArrival: '19:15',
        });
        if (data.success) {
          showFeedback('SafeWalk started successfully.');
          await loadStatus();
        }
      } catch (error) {
        console.error(error);
        showFeedback('Unable to start SafeWalk.');
      }
    }

    async function triggerDemo(endpoint, message) {
      try {
        const data = await fetchJson(endpoint, 'POST');
        if (data.success) {
          showFeedback(message);
          await loadStatus();
        }
      } catch (error) {
        console.error(error);
        showFeedback('Demo action failed.');
      }
    }

    async function addContact(event) {
      event.preventDefault();
      const name = document.getElementById('nameInput').value.trim();
      const relationship = document.getElementById('relationshipInput').value.trim();
      const phone = document.getElementById('phoneInput').value.trim();
      if (!name || !relationship || !phone) return;

      try {
        const data = await fetchJson('/api/contacts', 'POST', { name, relationship, phone });
        if (data.success) {
          document.getElementById('contactForm').reset();
          showFeedback(`Added contact: ${name}`);
          await loadContacts();
        }
      } catch (error) {
        console.error(error);
        showFeedback('Unable to add contact.');
      }
    }

    function openSosModal() {
      const modal = document.getElementById('sosModal');
      modal.classList.add('open');
      setText('modalLocation', `${state.lastLocationLat || 40.7128}, ${state.lastLocationLng || -74.0060}`);
      setText('modalTime', new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    }

    async function confirmSos() {
      try {
        const data = await fetchJson('/api/emergency', 'POST');
        document.getElementById('sosModal').classList.remove('open');
        if (data.success) {
          showFeedback('Emergency demo alert triggered.');
          await loadStatus();
        }
      } catch (error) {
        console.error(error);
        showFeedback('Emergency alert failed.');
      }
    }

    async function checkIn() {
      try {
        const data = await fetchJson('/api/journey/checkin', 'POST');
        if (data.success) {
          showFeedback('Check-in recorded.');
          await loadStatus();
        }
      } catch (error) {
        console.error(error);
        showFeedback('Check-in failed.');
      }
    }

    async function useMyLocation() {
      if (!navigator.geolocation) {
        showFeedback('Geolocation is not supported in this browser.');
        return;
      }

      navigator.geolocation.getCurrentPosition(async (position) => {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        state.lastLocationLat = lat;
        state.lastLocationLng = lng;
        try {
          const data = await fetchJson('/api/location', 'POST', { lat, lng, label: 'Current Device Location' });
          if (data.success) {
            showFeedback('Current location updated.');
            await loadStatus();
          }
        } catch (error) {
          console.error(error);
          showFeedback('Location update failed.');
        }
      }, () => {
        showFeedback('Location permission denied. Using demo location instead.');
      });
    }

    document.getElementById('startJourneyBtn').addEventListener('click', startJourney);
    document.getElementById('sosBtn').addEventListener('click', openSosModal);
    document.getElementById('sessionSosBtn').addEventListener('click', openSosModal);
    document.getElementById('confirmSosBtn').addEventListener('click', confirmSos);
    document.getElementById('cancelSosBtn').addEventListener('click', () => document.getElementById('sosModal').classList.remove('open'));
    document.getElementById('checkinBtn').addEventListener('click', checkIn);
    document.getElementById('useLocationBtn').addEventListener('click', useMyLocation);
    document.getElementById('gpsFailBtn').addEventListener('click', () => triggerDemo('/api/demo/gps/failure', 'GPS failure simulated.'));
    document.getElementById('networkFailBtn').addEventListener('click', () => triggerDemo('/api/demo/network/offline', 'Network failure simulated.'));
    document.getElementById('networkRecoveryBtn').addEventListener('click', () => triggerDemo('/api/demo/network/recovery', 'Network recovered.'));
    document.getElementById('batteryLowBtn').addEventListener('click', () => triggerDemo('/api/demo/battery/low', 'Low battery mode simulated.'));
    document.getElementById('batteryCriticalBtn').addEventListener('click', () => triggerDemo('/api/demo/battery/critical', 'Critical battery mode simulated.'));
    document.getElementById('resetDemoBtn').addEventListener('click', () => triggerDemo('/api/demo/reset', 'Demo reset.'));
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
    add_timeline_event("SafeWalk AI started.")


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(HTML_PAGE)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "SafeWalk AI", "timestamp": now_iso()}


@app.get("/api/status")
def api_status() -> Dict[str, Any]:
    return get_status_payload()


@app.post("/api/location")
def update_location(payload: Dict[str, Any]) -> Dict[str, Any]:
    lat = payload.get("lat")
    lng = payload.get("lng")
    label = payload.get("label") or "Current Location"
    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="lat and lng are required")
    APP_STATE["lastReliableLocation"] = {"lat": float(lat), "lng": float(lng), "label": label}
    APP_STATE["gps"] = "Reliable"
    add_timeline_event(f"Location updated: {label}")
    add_event("Location", f"Updated device location to {lat}, {lng}")
    return {"success": True, "location": APP_STATE["lastReliableLocation"]}


@app.post("/api/journey/start")
def journey_start(payload: Dict[str, Any]) -> Dict[str, Any]:
    destination = payload.get("destination", "Downtown Station")
    estimated_arrival = payload.get("estimatedArrival", "19:15")
    APP_STATE["session"] = "Active"
    APP_STATE["journey"] = {
        "destination": destination,
        "status": "Active",
        "estimatedArrival": estimated_arrival,
        "startedAt": now_iso(),
    }
    APP_STATE["emergency"] = False
    add_timeline_event(f"Journey started to {destination}.")
    add_event("Journey", f"SafeWalk started toward {destination}")
    return {"success": True}


@app.post("/api/journey/checkin")
def journey_checkin() -> Dict[str, Any]:
    if not APP_STATE["journey"]:
        return {"success": False, "message": "No active journey."}
    APP_STATE["session"] = "Active"
    add_event("Check-in", "User confirmed they are safe.")
    add_timeline_event("User checked in and confirmed safety.")
    return {"success": True}


@app.post("/api/emergency")
def emergency_simulation() -> Dict[str, Any]:
    APP_STATE["emergency"] = True
    APP_STATE["session"] = "Emergency"
    APP_STATE["journey"] = APP_STATE["journey"] or {"destination": "Demo Route", "status": "Emergency", "estimatedArrival": "—"}
    add_event("Emergency", "Demo emergency alert triggered.")
    add_timeline_event("Emergency alert triggered.")
    return {"success": True}


@app.get("/api/contacts")
def get_contacts() -> Dict[str, Any]:
    contacts = load_contacts()
    APP_STATE["trustedContacts"] = contacts
    return {"contacts": contacts}


@app.post("/api/contacts")
def create_contact(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    relationship = (payload.get("relationship") or "").strip()
    phone = (payload.get("phone") or "").strip()
    if not name or not relationship or not phone:
        raise HTTPException(status_code=400, detail="All fields are required.")
    persist_contact({"name": name, "relationship": relationship, "phone": phone})
    add_event("Contact", f"Added trusted contact: {name}")
    return {"success": True}


@app.post("/api/demo/gps/failure")
def gps_failure() -> Dict[str, Any]:
    APP_STATE["gps"] = "Unavailable"
    APP_STATE["session"] = "Fallback Mode"
    add_event("GPS", "GPS unavailable — using last reliable location.")
    add_timeline_event("GPS failed — app switched to last reliable location.")
    return {"success": True}


@app.post("/api/demo/network/offline")
def network_offline() -> Dict[str, Any]:
    APP_STATE["network"] = "Offline"
    APP_STATE["session"] = "Offline Safety Mode"
    queue_local_event("Network unavailable — queued locally.")
    add_event("Network", "Offline mode enabled; actions queued locally.")
    add_timeline_event("Network failed — offline safety mode enabled.")
    return {"success": True}


@app.post("/api/demo/network/recovery")
def network_recovery() -> Dict[str, Any]:
    APP_STATE["network"] = "Connected"
    APP_STATE["session"] = "Recovered"
    queued = len(APP_STATE["queuedEvents"])
    clear_local_queue()
    add_event("Recovery", f"Network restored and {queued} queued events synchronized.")
    add_timeline_event("Network restored — session recovered.")
    return {"success": True}


@app.post("/api/demo/battery/low")
def battery_low() -> Dict[str, Any]:
    APP_STATE["battery"] = 22
    APP_STATE["session"] = "Battery Awareness"
    add_event("Battery", "Battery reduced to 22% — battery awareness enabled.")
    add_timeline_event("Battery dropped below 30% — battery awareness mode enabled.")
    return {"success": True}


@app.post("/api/demo/battery/critical")
def battery_critical() -> Dict[str, Any]:
    APP_STATE["battery"] = 4
    APP_STATE["session"] = "Critical Safety Mode"
    add_event("Battery", "Battery critical at 4% — preserve essential functions.")
    add_timeline_event("Battery critical — emergency-safe behavior enabled.")
    return {"success": True}


@app.post("/api/demo/reset")
def reset_demo() -> Dict[str, Any]:
    APP_STATE["network"] = "Connected"
    APP_STATE["gps"] = "Reliable"
    APP_STATE["battery"] = 72
    APP_STATE["session"] = "Inactive"
    APP_STATE["journey"] = None
    APP_STATE["queuedEvents"] = []
    APP_STATE["emergency"] = False
    APP_STATE["lastReliableLocation"] = random.choice(DEMO_LOCATIONS)
    APP_STATE["timeline"] = [
        {"time": "09:00", "event": "System booted and health checks passed."},
        {"time": "09:03", "event": "GPS and network are stable."},
    ]
    APP_STATE["safetyHistory"] = [
        {"time": "09:00", "type": "Startup", "message": "SafeWalk AI ready."},
        {"time": "09:03", "type": "Status", "message": "Full protection active."},
    ]
    add_event("Reset", "Demo state reset to initial conditions.")
    add_timeline_event("Demo reset to a clean baseline.")
    return {"success": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
