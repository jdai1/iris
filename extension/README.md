# Save to Iris browser extension

Manifest V3 extension for Chrome, Arc, Edge, and other Chromium browsers.

## Local development

Run Iris normally on the canonical local origins:

```bash
backend/.venv/bin/python -m uvicorn iris.routes:app --reload --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
```

Build the unpacked extension:

```bash
npm --prefix extension/ui install
npm --prefix extension run build:local
```

Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select `extension/dist`.

After extension changes, rerun the build and reload the extension card. The local profile is read from `config/environments.json`.

## Production package

```bash
npm --prefix extension run package
```

This builds against the Railway production API and `www.iriis.net`, validates a clean runtime directory, and creates `extension/release/save-to-iris-1.0.0.zip`. Production and local builds share the origins declared in `config/environments.json`.

## Architecture

- React 19 + Tailwind v4 popup, onboarding, and settings surfaces.
- Manifest V3 module service worker for Firebase session refresh and authenticated API transport.
- Framework-free content script for selection, anchoring, and highlight controls.
- UUID-only public document and highlight API calls.
- No direct database access; all durable state goes through FastAPI.

The content script is available on HTTP(S) pages so selection controls can appear without opening the popup. Merely loading or selecting on a new page does not contact Iris. Clicking **Highlight** idempotently captures the page when necessary and then creates the highlight; automatic restoration requests remain limited to URLs in the extension's bounded `savedUrls` list.
