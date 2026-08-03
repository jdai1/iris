# Iris browser extension

The unpacked Manifest V3 extension built into `extension/dist/` implements a low-friction social-reading foundation without collecting general browsing history.

## User loop

1. Selecting text on any normal HTTP(S) page opens the Iris toolbar; the popup is not required.
2. Clicking **Highlight** captures the page if necessary and saves the highlight in one flow.
3. The adjacent note action saves the highlight and immediately opens its note editor.
4. Clicking a saved highlight opens note and delete actions.
5. Opening the extension popup remains an optional way to save the page and edit favorite, Read next/Read, note, and topic state.
6. Revisiting a locally known saved URL resolves its Iris state and restores highlights.

## Anchoring

Each highlight stores the exact quote, up to 64 characters of prefix and suffix context, and start/end offsets in the page's concatenated eligible text nodes. Restoration tries exact offsets first, then quote plus context. Scripts, styles, form controls, contenteditable regions, and Iris-owned UI are excluded.

Highlights spanning inline elements use range extraction as a fallback when `surroundContents` cannot wrap the selection. Pages rendered through canvas, PDFs, cross-origin frames, and heavily mutating applications are outside v1 scope. An unresolved anchor is left detached rather than placed heuristically.

## Privacy boundary

The content script is present on HTTP(S) pages so the selection toolbar can appear immediately. Selection alone is local and sends nothing. Clicking a toolbar action explicitly sends the current URL, title, and selected-text anchors to Iris; capture is idempotent when the page is already saved. Automatic restoration contacts Iris only when the exact URL (or its tracking-normalized form) is already in the extension's local `savedUrls` list. Browsing history is never requested.

## Backend

- `POST /api/browser/pages/capture`
- `GET /api/browser/pages/resolve?url=...`
- `GET/POST /api/documents/{document_uuid}/highlights`
- `PATCH/DELETE /api/highlights/{highlight_uuid}`

Highlights are user-owned and soft-deleted. Repeated page capture preserves existing notes and tags unless new values are supplied.

## Local validation

```bash
npm --prefix extension run build:local
python3 -m json.tool extension/dist/manifest.json >/dev/null
for file in extension/*.js; do node --check "$file"; done
node extension/anchoring.test.js
FIREBASE_PROJECT_ID= FIREBASE_SERVICE_ACCOUNT_FILE= FIREBASE_SERVICE_ACCOUNT_JSON= \
  GOOGLE_CLOUD_PROJECT= GOOGLE_APPLICATION_CREDENTIALS= \
  backend/.venv/bin/python -m pytest backend -q
npm --prefix frontend run build
git diff --check
```

After code changes, rebuild and reload `extension/dist` from `arc://extensions` or `chrome://extensions`. Settings live at `settings.html`, while first-run education lives at `onboarding.html`. See `docs/browser-extension-architecture.md` for the current v1 design.
