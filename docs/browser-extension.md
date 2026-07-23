# Iris browser extension

The unpacked Manifest V3 extension in `extension/` implements an explicit-save social-reading foundation without collecting general browsing history.

## User loop

1. Opening the extension popup captures the active page immediately.
2. The popup edits favorite, Read next/Read, note, and topic state.
3. A saved URL is recorded locally in extension storage.
4. On saved pages, selecting text opens an Iris toolbar.
5. One click saves a highlight; clicking the saved highlight opens note and delete actions.
6. Revisiting a locally known saved URL resolves its Iris state and restores highlights.

## Anchoring

Each highlight stores the exact quote, up to 64 characters of prefix and suffix context, and start/end offsets in the page's concatenated eligible text nodes. Restoration tries exact offsets first, then quote plus context. Scripts, styles, form controls, contenteditable regions, and Iris-owned UI are excluded.

Highlights spanning inline elements use range extraction as a fallback when `surroundContents` cannot wrap the selection. Pages rendered through canvas, PDFs, cross-origin frames, and heavily mutating applications are outside v1 scope. An unresolved anchor is left detached rather than placed heuristically.

## Privacy boundary

The content script is present on HTTP(S) pages so highlighting can work immediately after capture, but it contacts Iris only when the exact URL (or its tracking-normalized form) is already in the extension's local `savedUrls` list. Toolbar capture is explicit; browsing history is never requested.

## Backend

- `POST /api/browser/pages/capture`
- `GET /api/browser/pages/resolve?url=...`
- `GET/POST /api/documents/{id}/highlights`
- `PATCH/DELETE /api/highlights/{id}`

Highlights are user-owned and soft-deleted. Repeated page capture preserves existing notes and tags unless new values are supplied.

## Local validation

```bash
python3 -m json.tool extension/manifest.json >/dev/null
for file in extension/*.js; do node --check "$file"; done
FIREBASE_PROJECT_ID= FIREBASE_SERVICE_ACCOUNT_FILE= FIREBASE_SERVICE_ACCOUNT_JSON= \
  GOOGLE_CLOUD_PROJECT= GOOGLE_APPLICATION_CREDENTIALS= \
  backend/.venv/bin/python -m pytest backend -q
npm --prefix frontend run build
git diff --check
```

After code changes, reload the extension from `arc://extensions` or `chrome://extensions`. Old `options.html` URLs belong to version 0.1.0; settings now live at `settings.html`, while first-run education lives at `onboarding.html`. See `docs/browser-extension-architecture.md` for the current v0.5.0 design.
