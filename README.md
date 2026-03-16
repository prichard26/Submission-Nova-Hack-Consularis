# Consularis

Process intelligence with Aurelius (Amazon Nova) and Company Process Intelligence Report for mid-sized businesses.

---

## Prerequisites

- **Node.js** (LTS) — frontend
- **Python 3.10+** — backend
- **AWS credentials** — for Aurelius chat and reports (Amazon Nova via Bedrock)

---

## Quick start

1. Copy the env template and set AWS credentials:

   ```bash
   cp .env.example backend/.env
   # Edit backend/.env: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
   ```

2. From the repository root, run:

   ```bash
   ./run.sh
   ```

3. Open **http://localhost:5173** in your browser. Backend runs at **http://localhost:8000**.

**Stop:** Press **Ctrl+C** in the terminal where `./run.sh` is running, or run `./stop.sh` to stop processes on ports 5173–5175 and 8000.

---

## Manual setup (optional)

**Backend only** (other terminal):

```bash
cp .env.example backend/.env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend only:** `cd frontend && npm install && npm run dev` (backend must be running).

---

## Project structure

```
├── .env.example
├── .gitignore
├── README.md
├── SUBMISSION.md
├── requirements.txt
├── requirements-dev.txt
├── run.sh
├── stop.sh
│
├── backend/
│   ├── main.py, config.py, db.py, stats.py
│   ├── routers/       # health, chat, graph, analyze, session, validation (helpers)
│   ├── agent/         # Nova runtime, tools, prompt, context, bedrock_client, analyzer, report_generator
│   ├── graph/         # model, workspace, store, layout, bpmn_export, summary, validation
│   ├── data/          # pharmacy/, logistics/, manufacturing/, retail/, restaurant/, etc.
│   └── tests/         # conftest + test_*.py
│
├── frontend/
│   ├── index.html
│   ├── package.json, vite.config.js, eslint.config.js
│   ├── public/        # logo.png
│   └── src/
│       ├── main.jsx, App.jsx, index.css
│       ├── components/  # + nodes/, CSS next to components
│       ├── pages/       # Landing, Dashboard, AnalyzePage
│       ├── hooks/
│       ├── services/
│       └── contexts/
│
└── docs/
    └── README.md      # Points to this README and backend README
```

---

## Run tests

From repo root:

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
cd backend && pytest -v
```

---

## Main API (frontend → backend)

- **GET /health** — Health check
- **POST /api/session/init** — Initialize session (template or blank)
- **GET /api/graph/json** — Session graph as JSON
- **GET /api/graph/workspace** — Workspace manifest
- **POST /api/chat** — Send message to Aurelius; returns reply and optional graph update
- **POST /api/chat/confirm** — Apply pending plan
- **POST /api/analyze** — Automation analyzer (markdown + metrics)
- **POST /api/report** — Company Process Intelligence Report (metrics + narratives)
- **GET /api/graph/export** — Session graph as BPMN 2.0 XML (download)

---

## Documentation

- [SUBMISSION.md](SUBMISSION.md) — Hackathon submission and inspiration
