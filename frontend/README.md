# Consularis Frontend

React + Vite frontend for process mapping with React Flow.

## Stack

- React 19
- Vite 7
- React Router
- @xyflow/react (React Flow)
- dagre (graph layout)
- html-to-image (PNG export)
- ESLint

## Quick Start

From `frontend/`:

```bash
npm install
npm run dev
```

App runs on the Vite dev URL (typically `http://localhost:5173`).

### Backend URL and APIs

Frontend API base: `VITE_API_BASE` when set, otherwise `http://localhost:8000`.

The app calls: `GET /api/graph/json`, `GET /api/graph/workspace`, `POST /api/graph/step`, `POST /api/graph/position`, and `POST /api/chat` (see [src/services/api.js](src/services/api.js)).

Example `.env` (frontend):

```bash
VITE_API_BASE=http://localhost:8000
```

## Scripts

- `npm run dev` - start development server
- `npm run build` - build production bundle
- `npm run preview` - preview production build locally
- `npm run lint` - run ESLint

## Routes

- `/` - Landing page (company input + sector tiles)
- `/dashboard` - Graph workspace (React Flow canvas, chat)

Session is persisted in `sessionStorage` under `consularis_session`.

## Project Structure

```text
frontend/
  src/
    components/
      AppErrorBoundary.jsx     # Global runtime fallback UI
      AureliusChat.jsx         # Chat assistant panel
      ProcessCanvas.jsx        # React Flow process graph canvas
      ProcessCanvas.css
      DetailPanel.jsx          # Step metadata editor (slides in from right)
      DetailPanel.css
      ProcessBreadcrumb.jsx    # Subprocess navigation breadcrumb
      LandscapeView.jsx        # Workspace tree overview (Dagre layout)
      LandscapeView.css
      DataViewState.jsx        # Shared loading/error state UI
      Robot.jsx                # Landing mascot component
      nodes/
        StepNode.jsx           # Rich step card (actor, metrics, automation bar)
        DecisionNode.jsx       # Diamond gateway node
        SubprocessNode.jsx     # Double-bordered drill-down node
        EventNode.jsx          # Start/end circle node
        nodeTypes.js           # React Flow nodeTypes registry
    hooks/
      useProcessGraph.js       # Fetch JSON graph with fallback + cancellation
      useWorkspace.js          # Fetch workspace manifest
    pages/
      Landing.jsx
      Dashboard.jsx
    services/
      api.js                   # Shared API request helpers
      graphTransform.js        # JSON graph -> React Flow nodes/edges
    App.jsx
    main.jsx
    index.css
```

## Data Flow

1. User starts on `/` and submits a company name (and sector; only Pharmacy is active). Session is stored in `sessionStorage` and user is routed to `/dashboard`.
2. Dashboard shows the **Process Canvas** (`ProcessCanvas`): fetches session graph via `GET /api/graph/json?session_id=...`; renders with React Flow using custom nodes (StepNode, DecisionNode, SubprocessNode, EventNode).
3. **Detail Panel** slides in when a step is clicked, showing all 19 metadata fields as an editable form.
4. **Landscape View** shows the workspace process tree using Dagre layout; clicking a process drills into its detail canvas.
5. **Aurelius chat** (`POST /api/chat`): sends message, receives assistant reply and updated `graph_json`; the canvas refreshes after a chat turn.

## UI theme and UX

- **Theme**: Light background with warm off-whites and orange accent. All colors are defined as CSS variables in `src/index.css` (`:root`). Main surfaces use `--bg-primary` (white), `--bg-secondary`, and `--bg-card`; graph canvases use a dot-pattern background (React Flow `Background` with `variant="dots"`).
- **Panels**: The step Detail Panel and the Aurelius chat overlay both have a semi-transparent backdrop. Clicking the backdrop or pressing **Escape** closes the open panel (Detail Panel takes precedence if both could close).

## Notes

- This frontend assumes the backend API is available.
- Build currently emits a large chunk warning due to React Flow; this is expected for now.
