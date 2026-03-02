# Consularis Frontend

React + Vite frontend for process mapping and BPMN editing.

## Stack

- React 19
- Vite 7
- React Router
- bpmn-js
- React Flow (`@xyflow/react`) for Process view
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

The app calls: `GET /api/graph/baseline`, `GET /api/graph/export`, `GET /api/graph/json`, and `POST /api/chat` (see [src/services/api.js](src/services/api.js)).

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
- `/dashboard` - Graph workspace (process view, BPMN view, chat)

Session is persisted in `sessionStorage` under `consularis_session`.

## Project Structure

```text
frontend/
  src/
    components/
      AppErrorBoundary.jsx     # Global runtime fallback UI
      AureliusChat.jsx         # Chat assistant panel
      BpmnViewer.jsx           # bpmn-js modeler wrapper
      DataViewState.jsx        # Shared loading/error state UI
      GraphCanvas.jsx          # Switches between process and BPMN viewers
      ProcessGraphViewer.jsx   # React Flow renderer
      Robot.jsx                # Landing mascot component
    hooks/
      useBpmnXml.js            # Fetch BPMN XML with fallback + cancellation
      useGraphJson.js          # Fetch graph JSON + cancellation
    pages/
      Landing.jsx
      Dashboard.jsx
    services/
      api.js                   # Shared API request helpers
    App.jsx
    main.jsx
    index.css
```

## Data Flow

1. User starts on `/` and submits a company name (and sector; only Pharmacy is active). Session is stored in `sessionStorage` and user is routed to `/dashboard`.
2. Dashboard shows a view toggle: **Process** (React Flow) or **BPMN** (bpmn-js).
3. **Process view** (`ProcessGraphViewer`): fetches graph via `GET /api/graph/json?session_id=...`; displays lanes, nodes, and edges with React Flow.
4. **BPMN view** (`BpmnViewer`): fetches session graph via `GET /api/graph/export?session_id=...` (or baseline via `GET /api/graph/baseline`); renders with bpmn-js. Chat panel can be shown in the footer; chat returns `bpmn_xml` and triggers a diagram refresh.
5. **Aurelius chat** (`POST /api/chat`): sends message, receives assistant reply and updated `bpmn_xml`; both Process and BPMN views can refresh after a chat turn.

## Notes

- This frontend assumes the backend API is available.
- Build currently emits a large chunk warning due to graph/modeling libraries; this is expected for now.
