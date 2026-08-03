# Iris agent guide

This is the durable operating manual for agents working in this repository. Read it before making changes.

## Keep this document alive

- Update this file in the same change whenever you discover durable tribal knowledge: architecture boundaries, deployment behavior, authentication requirements, non-obvious commands, production incidents, or recurring pitfalls.
- Prefer correcting or reorganizing existing guidance over appending a chronological log.
- Keep transient task notes out of this file. Put cross-project scratch notes in `~/Documents/obsidian/brain`.
- Never add secrets, tokens, private database URLs, service-account JSON, or user data. Document secret *names* and where they are configured instead.
- If code behavior and this guide disagree, verify the behavior, fix the guide, and call out the discrepancy in the change.

## How to work here

- Think before coding. Confirm the request, the affected surfaces, and the smallest coherent change.
- Prefer simplicity, surgical edits, and goal-driven execution.
- Preserve unrelated and in-progress work. Inspect the worktree before editing.
- Use `rg` for discovery and `apply_patch` for hand edits.
- Public API identifiers are stable UUIDs. Integer database IDs are internal implementation details unless an existing endpoint explicitly says otherwise.
- Run checks proportional to the change. A cross-surface change should validate every affected app before it is published.

## Repository blueprint

```text
iris/
├── backend/          FastAPI API, SQLAlchemy models/DAOs, services, Alembic, pytest
├── frontend/         Main React 19 + Vite + Tailwind v4/shadcn-style web app
├── admin/            Separate local-only read-only React admin console
├── extension/        Manifest V3 browser extension and its React UI build
├── config/           Shared non-secret environment/origin registry
├── docs/             Product and architecture documentation
├── evals/            Search/agent evaluation fixtures and tooling
└── AGENTS.md         This living guide
```

### Backend

- The FastAPI application is exposed from `backend/iris/routes` and all HTTP routes live under `/api` except health checks.
- SQLAlchemy models are in `backend/iris/models`; database access belongs in `backend/iris/dao`; response/request models belong in `backend/iris/schemas`.
- Schema changes require an Alembic migration in `backend/alembic/versions` and tests that exercise both upgraded data and the public API contract.
- `DATABASE_URL` wins over `DEV_DATABASE_URL`; the fallback is the repository-local SQLite database. Production uses Railway Postgres with pgvector.
- Document and highlight UUIDs are public. Do not reintroduce integer-ID fallbacks at public document, graph, bookshelf, or highlight endpoints.
- Search conversations persist the user prompts, search steps, inspected documents, responses, and results. Admin inspection uses separate `/api/admin/...` endpoints; never weaken normal user scoping to support admin views.

### Main frontend

- `frontend/` is a Vite SPA using React 19, TypeScript, Tailwind v4, Radix primitives, and shadcn-style components.
- Design tokens live in `frontend/src/index.css`. Keep component-specific styling in Tailwind classes and shared primitives rather than adding standalone custom stylesheets.
- The product accent is purple. The interface uses slightly sharp radii and compact, quiet surfaces inspired by the Codex app.
- Canonical local frontend origin is `http://localhost:5175`; the canonical local API is `http://127.0.0.1:8000`.
- `npm run dev:remote` keeps the frontend local while pointing API calls at Railway via the committed non-secret remote-mode environment file.
- Document routes and drawers key their detail components by document UUID so switching documents resets scroll and local state.

### Admin console

- `admin/` is intentionally a separate Vite application, normally run locally on `http://localhost:5176`.
- It shares the main app's visual language and Firebase project but is not a separately deployed Railway service.
- It is read-only: top-level metrics, recent query traces, and user reports including collections and saved-state details. Impersonation is deliberately out of scope.
- Backend access is enforced by `IRIS_ADMIN_EMAILS`; hiding UI is not authorization.
- Use `npm run dev:remote` for the ergonomic local-admin/production-backend workflow.

### Browser extension

- `extension/background.js` owns Firebase session refresh and proxies authenticated API requests. Extension pages and content scripts should not call Iris directly.
- `extension/content.js` is framework-free to avoid leaking host-page styles. React/Tailwind UI surfaces live under `extension/ui/`.
- `config/environments.json` is the source of truth for local and production app/API origins.
- Generated artifacts belong in `extension/dist/` and release ZIPs in `extension/release/`; do not hand-edit or commit generated UI bundles.
- Build local unpacked output with `npm --prefix extension run build:local`. Build the production Web Store ZIP with `npm --prefix extension run package`.
- Loading a page or selecting text must not transmit browsing activity. A network capture begins only after an explicit Iris action; saved-URL restoration is limited to locally known saved URLs.

## Firebase authentication

- The browser receives Firebase web configuration through `VITE_FIREBASE_*` variables. These identify the Firebase web app; they are not backend service-account credentials.
- The frontend sends Firebase ID tokens as `Authorization: Bearer ...`. The backend verifies them with the Firebase Admin SDK and resolves the Iris user.
- Railway must have explicit Admin SDK credentials through `FIREBASE_SERVICE_ACCOUNT_JSON` (preferred for a hosted service) or `FIREBASE_SERVICE_ACCOUNT_FILE`, plus `FIREBASE_PROJECT_ID`. Do not rely on ambient Google credentials on Railway.
- `FIREBASE_HTTP_TIMEOUT_SECONDS` bounds Firebase Admin network calls. Invalid tokens are `401`; missing credentials, certificate-fetch failures, and unexpected verifier outages are `503` so clients do not mistake infrastructure failures for logout.
- Authorized web origins must also be present in Firebase Authentication > Settings > Authorized domains. At minimum maintain the production domain and the localhost hostnames used for development.
- The extension receives an authenticated handoff only from the app origin compiled into its manifest, stores renewable credentials in extension-local storage, and refreshes through Google's secure-token endpoint.
- Never commit service-account JSON, Firebase refresh tokens, or production database credentials.

## Local development

Backend:

```bash
cd backend
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn iris.routes:app --reload --host 127.0.0.1 --port 8000
```

Main frontend:

```bash
npm --prefix frontend run dev
# or, against the Railway backend:
npm --prefix frontend run dev:remote
```

Admin console:

```bash
npm --prefix admin run dev:remote
```

Browser extension:

```bash
npm --prefix extension/ui install
npm --prefix extension run build:local
```

Load `extension/dist` as an unpacked extension in Chrome/Arc. Rebuild and reload the extension after worker, manifest, content-script, or UI changes.

## Validation baseline

Run the checks that cover the changed surfaces. Before consolidating a cross-stack branch, run all of these:

```bash
backend/.venv/bin/python -m pytest backend -q
npm --prefix frontend run build
npm --prefix admin run build
npm --prefix extension test
npm --prefix extension run build:local
npm --prefix extension run build:production
git diff --check
```

Use `backend/.venv/bin/alembic heads` to confirm a single migration head. Do not point automated tests at the production database.

## Deployment and CI/CD

- The backend and frontend are separate Railway services configured by `backend/railway.toml` and `frontend/railway.toml`.
- Railway builds each service from its subdirectory Dockerfile. The backend container runs `alembic upgrade head` before starting Uvicorn, so every migration must be safe to run during deploy and against existing production rows.
- Backend health is `/health`. The hosted API is `https://iris-production-73ec.up.railway.app`.
- The production frontend is `https://www.iriis.net`; its build receives `VITE_API_BASE` and `VITE_FIREBASE_*` as Railway build variables.
- GitHub `main` is the integration branch. Use a reviewed PR for normal changes and confirm required checks before merging.
- Railway deploys the branch configured on each service, which is independent of GitHub's default branch. After changing branch strategy, verify the Railway service source branch explicitly; a merge to `main` alone does not retarget Railway.
- A green GitHub merge and a green Railway deployment are separate facts. Verify the Railway deployment/health after changes to backend startup, migrations, environment variables, authentication, or frontend build configuration.
- Firebase Authorized domains, Railway CORS origins, the production frontend URL, and extension `externally_connectable` origin must stay aligned.

## Before handing off

- Confirm `git status` contains only intentional work.
- Note migrations and environment-variable additions explicitly.
- Report the exact checks run and whether production was actually deployed or only merged.
- Update this guide when the work introduced reusable knowledge that would otherwise have to be rediscovered.
