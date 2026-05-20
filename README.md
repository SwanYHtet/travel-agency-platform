# CMPE 131 — Multi-Tenant Travel Agency SaaS Platform (Phase 3)

## Prerequisites

- Python 3.10+
- Node.js 18+
- `uv` (or plain `pip`)

---

## 1. One-time hosts setup (Mac/Linux)

```bash
sudo sh -c 'printf "\n127.0.0.1 agenta.local\n127.0.0.1 agentb.local\n" >> /etc/hosts'
```

---

## 2. Clone the repo

```bash
git clone https://github.com/SwanYHtet/travel-agency-platform.git
cd travel-agency-platform
```

---

## 3. Start the Phase 3 backend (port 8000)

```bash
cd travel-agency-api
uv run uvicorn app.main:app --reload --port 8000
```

> If you don't have `uv`: `pip install uv` first, or replace `uv run` with plain `uvicorn`.

---

## 4. Start the Phase 2 backend — multi-city packages (port 8001)

```bash
cd travel-agency-phase2-api
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

---

## 5. Start the frontend (port 5173)

```bash
cd travel-agency-app
npm install
npm run dev
```

---

## 6. Open in browser

| Tenant | URL |
|---|---|
| Agency A | http://agenta.local:5173 |
| Agency B | http://agentb.local:5173 |

**Test login:** `john.doe@example.com` / `CMPE-131@2026`

---

## Features

- Flight, hotel, and activity search (RapidAPI with mock fallback)
- Multi-city package builder with budget filtering — includes attraction costs
- Dynamic departure/return dates per leg
- Booking with per-city hotel check-in/out dates
- My Trips with flight, hotel, and activity details
- Multi-tenant routing (Agency A / Agency B)
