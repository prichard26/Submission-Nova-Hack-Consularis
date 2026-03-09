# Licenses Used (Project Dependencies)

**Recap — Free to sell?** Yes. You are free to use this application commercially and to sell it. All dependencies used (frontend and backend) allow commercial use and distribution. The only condition: when you distribute the app, you must include the EPL-2.0 license and make the source of **elkjs** (and any changes to it) available; your own application code does not need to be open-sourced.

---

This document lists the license types of dependencies used by the **frontend** and **backend** applications. It is intended for compliance and distribution. **Commercial use and sale of the application are permitted** under the terms of these licenses, subject to each license’s requirements (e.g. retaining notices, providing source for EPL-2.0 code).

---

## Frontend

*Source: `frontend/package.json`*

### Direct Dependencies

| Package | Version | License | Notes |
|---------|---------|---------|--------|
| @xyflow/react | ^12.10.1 | MIT | React Flow – diagram UI |
| dagre | ^0.8.5 | MIT | Graph layout (optional) |
| elkjs | ^0.11.1 | **EPL-2.0** | Eclipse Layout Kernel – auto-arrange layout |
| html-to-image | ^1.11.13 | MIT | Export canvas to image |
| react | ^19.2.0 | MIT | UI library |
| react-dom | ^19.2.0 | MIT | React DOM renderer |
| react-router-dom | ^7.13.1 | MIT | Routing |

### Frontend Direct DevDependencies

| Package | Version | License | Notes |
|---------|---------|---------|--------|
| @eslint/js | ^9.39.1 | MIT | ESLint JS parser |
| @types/react | ^19.2.7 | MIT | React type definitions |
| @types/react-dom | ^19.2.3 | MIT | React DOM type definitions |
| @vitejs/plugin-react | ^5.1.1 | MIT | Vite React plugin |
| eslint | ^9.39.1 | MIT | Linting |
| eslint-plugin-react-hooks | ^7.0.1 | MIT | React Hooks rules |
| eslint-plugin-react-refresh | ^0.4.24 | MIT | Fast refresh rules |
| globals | ^16.5.0 | MIT | Global variable definitions |
| vite | ^7.3.1 | MIT | Build tooling |

### Frontend Transitive Dependencies (Summary)

As of the last `license-checker` run, the full frontend dependency tree breaks down by license as follows:

| License | Count | Commercial use |
|---------|--------|----------------|
| MIT | 144 | Yes, permissive |
| ISC | 18 | Yes, permissive |
| Apache-2.0 | 12 | Yes, permissive |
| BSD-2-Clause | 6 | Yes, permissive |
| BSD-3-Clause | 3 | Yes, permissive |
| EPL-2.0 | 1 | Yes (elkjs; disclose source of library when distributing) |
| Python-2.0 | 1 | Yes (permissive) |
| CC-BY-4.0 | 1 | Yes (attribution) |
| UNLICENSED | 1 | This project (frontend); not a third-party dep |

---

## Backend

*Source: `backend/requirements.txt`, `backend/requirements-dev.txt`*

### Direct Dependencies (Runtime)

| Package | Version | License | Notes |
|---------|---------|---------|--------|
| fastapi | 0.134.0 | MIT | Web API framework |
| uvicorn[standard] | 0.41.0 | BSD-3-Clause | ASGI server |
| pydantic | 2.12.5 | MIT | Data validation |
| python-dotenv | 1.2.1 | BSD-3-Clause | Environment variables |
| boto3 | ≥1.35.0 | Apache-2.0 | AWS SDK (Bedrock / Nova) |

### Backend Direct DevDependencies

| Package | Version | License | Notes |
|---------|---------|---------|--------|
| pytest | 9.0.2 | MIT | Testing |
| httpx | 0.28.1 | BSD-3-Clause | HTTP client (tests) |

### Backend Transitive Dependencies (Common)

Backend runtime pulls in additional packages (e.g. starlette, anyio, h11, httpcore, pydantic_core). These are typically MIT or BSD-3-Clause. To generate a full backend license report, use a virtualenv with only backend deps installed and run:

```bash
cd backend
pip install pip-licenses
pip-licenses --format=markdown
```

---

## Special Notes

- **EPL-2.0 (elkjs, frontend):** You may use and sell the application. When you distribute the application, you must include the EPL-2.0 license and make the source code of elkjs (and any modifications to it) available. Your own application code that merely uses elkjs does not need to be open-sourced.
- **MIT / ISC / BSD / Apache-2.0:** Use and sale are allowed. Keep the license notices (e.g. in NOTICE or license files) when you distribute.

---

## Regenerating Reports

**Frontend (full tree):**

```bash
cd frontend
npx license-checker --summary
```

For a detailed JSON report: `npx license-checker --json`

**Backend (full tree, from backend venv):**

```bash
cd backend
pip install pip-licenses
pip-licenses --format=markdown
```

---

*Last updated from `frontend/package.json`, `backend/requirements.txt`, `backend/requirements-dev.txt`, and license-checker / pip metadata.*
