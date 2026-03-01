# Consularis Frontend

React + Vite frontend for process mapping and BPMN editing.

## Stack

- React 19
- Vite 7
- React Router
- bpmn-js
- React Flow (`@xyflow/react`)
- ESLint

## Quick Start

From `frontend/`:

```bash
npm install
npm run dev
```

App runs on the Vite dev URL (typically `http://localhost:5173`).

### Backend URL

Frontend API calls use:

- `VITE_API_BASE` when set
- fallback: `http://localhost:8000`

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

1. User starts on `/` and submits a company name.
2. Session is stored and user is routed to `/dashboard`.
3. Dashboard toggles between:
   - process graph (`ProcessGraphViewer`) using graph JSON
   - BPMN editor (`BpmnViewer`) using BPMN XML
4. Chat requests can trigger graph/BPMN refresh.

## Notes

- This frontend assumes the backend API is available.
- Build currently emits a large chunk warning due to graph/modeling libraries; this is expected for now.
