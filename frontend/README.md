# Consularis Frontend

React + Vite frontend for Consularis process mapping: React Flow canvas, Aurelius chat, and Company Process Intelligence Report.

---

## Stack

- React 19, Vite 7, React Router
- @xyflow/react (React Flow)
- dagre (graph layout)
- html-to-image (PNG export)
- ESLint

---

## Quick start

From `frontend/`:

```bash
npm install
npm run dev
```

App runs at **http://localhost:5173** (or the Vite dev URL). The backend must be running (default **http://localhost:8000**). To use a different API base, set `VITE_API_BASE` in a frontend `.env` (e.g. `VITE_API_BASE=http://localhost:8000`).

---

## Scripts

- `npm run dev` — development server
- `npm run build` — production bundle
- `npm run preview` — preview production build locally
- `npm run lint` — ESLint

---

## Routes

- **/** — Landing: company name and sector/template selection; session stored in `sessionStorage` under `consularis_session`, then redirect to dashboard.
- **/dashboard** — Graph workspace: React Flow canvas, Aurelius chat, landscape/minimap, detail panel.
- **/dashboard/analyze** — Company Process Intelligence Report (metrics, charts, narratives, PDF export, appointment CTA).

---

## Project structure

```text
frontend/
├── index.html
├── package.json, vite.config.js, eslint.config.js
├── public/
│   └── logo.png
└── src/
    ├── main.jsx, App.jsx, index.css
    ├── components/
    │   ├── AppErrorBoundary.jsx
    │   ├── AureliusChat.jsx, AureliusChat.css
    │   ├── ProcessCanvas.jsx, ProcessCanvas.css
    │   ├── DetailPanel.jsx, DetailPanel.css
    │   ├── LandscapeView.jsx, LandscapeView.css
    │   ├── LandscapeMinimap.jsx, LandscapeMinimap.css
    │   ├── DataViewState.jsx
    │   ├── Robot.jsx, Robot.css
    │   ├── BotFace.jsx, BotFace.css
    │   ├── DashboardTopBar.jsx
    │   ├── DashboardTutorial.jsx, DashboardTutorial.css
    │   ├── ModelPicker.jsx, ModelPicker.css
    │   ├── FloatingToolbar.jsx
    │   ├── EdgeEditorModal.jsx
    │   └── nodes/
    │       ├── nodeTypes.jsx      # React Flow node type registry
    │       ├── StepNode.jsx, StepNode.css
    │       ├── DecisionNode.jsx, DecisionNode.css
    │       ├── SubprocessNode.jsx, SubprocessNode.css
    │       ├── EventNode.jsx, EventNode.css
    │       ├── LaneNode.jsx, LaneNode.css
    │       └── nodes-common.css
    ├── pages/
    │   ├── Landing.jsx, Landing.css
    │   ├── Dashboard.jsx, Dashboard.css
    │   └── AnalyzePage.jsx, AnalyzePage.css
    ├── hooks/
    │   ├── useChat.js
    │   ├── useProcessGraph.js
    │   ├── useWorkspace.js
    │   ├── useFetchResource.js
    │   ├── useVoiceInput.js
    │   ├── useMicLevels.js
    │   ├── useGraphHistory.js
    │   └── useInlineRename.js
    ├── services/
    │   ├── api.js           # Backend API client
    │   ├── graphTransform.js # JSON graph → React Flow nodes/edges
    │   └── landscapeLayout.js # Dagre layout for process tree
    └── contexts/
        └── ProcessCanvasContext.jsx
```

---

## Data flow

- **Landing** → user enters company name and template → `initSession` → session in `sessionStorage` → redirect to `/dashboard`.
- **Dashboard** → Process Canvas fetches graph via `GET /api/graph/json`; workspace via `GET /api/graph/workspace`. Custom nodes (Step, Decision, Subprocess, Event, Lane) render the graph. Clicking a step opens the Detail Panel (metadata edit). Aurelius chat uses `POST /api/chat` and `POST /api/chat/confirm`; canvas refreshes when the response includes graph updates.
- **Analyze** → Report page fetches `POST /api/report` for metrics and narratives, renders charts and PDF export; appointment form uses `POST /api/appointment`.

---

## Theme and UX

Colors and surfaces use CSS variables in `src/index.css` (`:root`): `--bg-primary`, `--bg-secondary`, `--bg-card`, `--accent`. Graph canvas uses React Flow `Background` with dots. Detail Panel and Aurelius chat use a backdrop; Escape or backdrop click closes the panel.
