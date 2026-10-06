# SafeWalk AI

A production-style mobile-first personal safety prototype built with Python and FastAPI.

## What it includes
- Safety Continuity Engine demo logic
- GPS/network/battery fallback states
- Offline Safety Mode and queued local event handling
- Safety timeline and event history
- Trusted contact management using SQLite
- Demo emergency flow with explicit prototype labeling
- Mobile-first dashboard UI served from FastAPI

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open:

http://localhost:8000

## Prototype note
This app simulates emergency notifications and safety behavior for demonstration purposes only. It does not send real emergency messages.

## API endpoints
- GET /health
- GET /safety-status
- POST /journey/start
- GET /journey/status
- POST /journey/status
- GET /events
- GET /trusted-contacts
- POST /trusted-contacts
- POST /emergency/demo
