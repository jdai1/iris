# Iris browser extension architecture

Status: v1 production rewrite in progress
Targets: Chrome, Arc, and other Chromium browsers using Manifest V3

## Executive summary

The Iris extension is a browser client for the existing Iris frontend and backend. It does not contain a second backend and it does not directly share a runtime with the Iris React app.

The extension has four browser-side parts:

1. A React + Tailwind popup that saves the active page immediately and edits bookshelf metadata.
2. React + Tailwind onboarding and settings pages using the current Iris design tokens.
3. A Manifest V3 background service worker that owns authentication and proxies every Iris API request.
4. A lightweight content script that exposes selection actions on normal web pages, captures on first highlight, and restores persisted highlights.

The normal Iris frontend performs Firebase login. After login, it passes a renewable Firebase session to the installed extension. The background worker stores that session locally, refreshes it automatically, and attaches a valid Firebase ID token to API requests. The FastAPI backend remains the source of truth for users, documents, bookshelf state, tags, and highlights.

## System context

```mermaid
flowchart LR
    User["Reader"]
    Page["Any HTTP(S) page"]

    subgraph Browser["Chrome / Arc"]
        Popup["Extension popup<br/>React + Tailwind"]
        Pages["Onboarding + settings<br/>React + Tailwind"]
        Worker["MV3 background worker<br/>auth + API proxy"]
        Content["Content script<br/>selection + highlighting"]
        Storage["chrome.storage<br/>local + sync"]
        IrisFE["Iris web frontend<br/>React + Tailwind + Firebase SDK"]
    end

    Firebase["Firebase Authentication"]
    SecureToken["Firebase Secure Token API"]
    Core["Iris FastAPI backend"]
    DB[("PostgreSQL")]

    User --> Popup
    User --> Page
    User --> IrisFE
    Popup --> Worker
    Pages --> Worker
    Content --> Worker
    Content <--> Page
    Worker <--> Storage
    IrisFE <--> Firebase
    IrisFE -->|"external extension message"| Worker
    Worker -->|"refresh token grant"| SecureToken
    Worker -->|"Bearer Firebase ID token"| Core
    Core <--> DB
```

## Component boundaries

| Component | Location | Responsibility | Deliberately does not do |
| --- | --- | --- | --- |
| Manifest | `extension/dist/manifest.json` | Generated environment-specific permissions, entry points, icons, and content-script registration | Application logic |
| Popup | `extension/ui/src/popup.tsx` | Immediate capture, favorite/read/note/topic UI, sign-in and retry states | Store or refresh tokens; call FastAPI directly |
| Onboarding | `extension/ui/src/onboarding.tsx` | Explain save → highlight → return and initiate login | Authenticate directly |
| Settings | `extension/ui/src/settings.tsx` | Show account connection, open Iris, disconnect, open guide | Configure arbitrary API URLs or expose tokens |
| UI client | `extension/ui/src/chrome.ts` | Send typed request messages to the worker and open Iris tabs | Perform authenticated `fetch` itself |
| Background worker | `extension/background.js` | Own renewable auth, proxy requests, retry after 401, receive frontend auth handoff | Render UI or inspect page DOM |
| Content script | `extension/content.js` | Show highlight/note actions, capture on first highlight, and render/edit/delete highlights | Own authentication or run React inside host pages |
| Anchoring library | `extension/anchoring.js` | Locate saved quotations by offsets and contextual quote matching | Network or DOM mutation |
| FastAPI browser routes | `backend/iris/routes/api.py` | Capture/resolve pages and manage highlights/bookshelf state | Browser UI |

The popup/onboarding/settings use the same Tailwind v4 theme values, typography, radii, and purple accent as the core frontend. They are separate extension bundles because extension pages have a separate origin and CSP. The content script intentionally remains framework-free so Iris styles do not leak into host websites and host styles do not alter the extension UI.

## One-click page save

Opening the popup is the save action. There is no second confirmation button.

```mermaid
sequenceDiagram
    actor Reader
    participant Popup as React popup
    participant Chrome as chrome.tabs / storage
    participant Worker as Background worker
    participant API as Iris FastAPI
    participant DB as PostgreSQL
    participant Content as Content script

    Reader->>Popup: Click extension icon
    Popup->>Chrome: Query active tab
    Chrome-->>Popup: URL + page title
    Popup->>Worker: iris-request: POST /api/browser/pages/capture
    Worker->>Worker: Obtain or refresh Firebase ID token
    Worker->>API: Capture request + Bearer token
    API->>DB: Normalize URL and upsert document
    API->>DB: Create/update user's bookshelf mapping
    API->>DB: Load tags and highlights
    DB-->>API: Saved page state
    API-->>Worker: BrowserPageSchema
    Worker-->>Popup: Response payload
    Popup->>Chrome: Add exact/canonical URL to local savedUrls
    Popup->>Content: iris-page-saved message
    Popup-->>Reader: Saved state + organization controls
```

Important behavior:

- Capture is idempotent by normalized document URL.
- Repeat capture preserves existing notes and tags unless the request explicitly supplies replacements.
- The page is saved before the user edits favorite, read state, note, or topics.
- The popup does not turn an existing page selection into the document note. Text selection belongs to the highlight flow.
- The backend is authoritative. Local `savedUrls` is an activation/privacy hint, not the saved-page database.

## Authentication architecture

### Why the extension needs its own session material

The Iris web app and a Chrome extension have different origins and storage sandboxes. Firebase login cookies/state inside `http://localhost:5175` are not automatically available to `chrome-extension://<extension-id>`.

The frontend therefore performs normal Firebase login and explicitly hands the installed extension renewable Firebase credentials. The extension does not show or embed its own Google login flow.

### Login handoff

```mermaid
sequenceDiagram
    actor Reader
    participant Popup as Extension popup
    participant FE as Iris frontend
    participant Firebase as Firebase SDK
    participant Worker as Background worker
    participant API as Iris FastAPI
    participant Store as chrome.storage.local

    Reader->>Popup: Open while disconnected
    Popup-->>Reader: Sign in to Iris
    Reader->>Popup: Click sign in
    Popup->>FE: Open /?iris_extension_auth=<extension-id>
    FE->>Firebase: Normal Firebase authentication
    Firebase-->>FE: Firebase User session
    FE->>Firebase: Force-fresh ID token + token result
    FE->>Worker: External message:<br/>ID token, refresh token, expiry, public API key
    Worker->>Worker: Verify sender origin is localhost:5175
    Worker->>API: GET /api/me with ID token
    API-->>Worker: Authenticated Iris user
    Worker->>Store: Save token material locally
    Worker-->>FE: ok: true
    FE->>FE: Remove auth query parameter
```

The external message is accepted only from the configured Iris frontend origin. The background worker validates the ID token against `/api/me` before persisting the session.

### Automatic token refresh

Firebase ID tokens are short-lived. The extension stores the Firebase refresh token so the site and extension do not drift into separate signed-in states.

```mermaid
flowchart TD
    Request["Extension API request"] --> Read["Read auth state from chrome.storage.local"]
    Read --> Fresh{"ID token valid for > 60 seconds?"}
    Fresh -->|Yes| Call["Call Iris API"]
    Fresh -->|No| Refresh["POST refresh_token grant to Firebase Secure Token API"]
    Refresh --> RefreshOK{"Refresh succeeded?"}
    RefreshOK -->|Yes| Persist["Persist rotated ID/refresh tokens + expiry"]
    Persist --> Call
    RefreshOK -->|No| Clear["Clear extension auth and require login"]
    Call --> Unauthorized{"API returned 401?"}
    Unauthorized -->|No| Return["Return response to caller"]
    Unauthorized -->|Yes| Retry["Force one refresh and retry once"]
    Retry --> RetryOK{"Retry succeeded?"}
    RetryOK -->|Yes| Return
    RetryOK -->|No| Clear
```

All extension surfaces use this path. The popup and content script do not attach tokens independently.

### Auth storage

`chrome.storage.local` contains:

- `authToken`: current Firebase ID token.
- `authRefreshToken`: Firebase refresh token.
- `authExpiresAt`: ID-token expiration time in epoch milliseconds.
- `firebaseApiKey`: public Firebase web API key required by the secure-token endpoint.
- `savedUrls`: bounded list of locally known saved URLs.

`chrome.storage.sync` contains non-secret extension state:

- `onboardingComplete`: onboarding connection state.

Tokens are intentionally stored in `local`, not `sync`, so they do not sync through the reader's browser account. Disconnecting clears all auth keys. A packaged production version should also consider explicit server-side session revocation and a more formal extension-session exchange if stronger centralized revocation is required.

## API communication

Extension callers send a runtime message rather than calling FastAPI directly:

```text
{ type: "iris-request", path: "/api/...", options: { method, body, headers } }
```

The background worker:

1. Loads or refreshes the Firebase token.
2. Adds `Authorization: Bearer <id-token>`.
3. Calls the configured Iris API base.
4. Retries once after a 401 using a forced token refresh.
5. Returns `{ ok, status, payload }` to the caller.

This centralization is important because Manifest V3 workers are ephemeral. Durable auth state lives in Chrome storage, while the worker can safely stop and restart between requests.

### Backend endpoints used

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/me` | GET | Validate the Firebase token and resolve the Iris user |
| `/api/browser/pages/capture` | POST | Idempotently save the active URL and return entry + highlights |
| `/api/browser/pages/resolve?url=...` | GET | Resolve saved state when revisiting a locally known URL |
| `/api/documents/{document_uuid}/bookshelf` | PATCH | Update favorite, read state, note, intent note, or topics |
| `/api/documents/{document_uuid}/highlights` | GET/POST | List or create user-owned highlights |
| `/api/highlights/{highlight_uuid}` | PATCH/DELETE | Update the highlight note/color or soft-delete it |

## Highlight lifecycle

Highlighting does not require opening the popup. The content script prepares the selection locally, then captures the page only after the reader clicks an Iris action.

```mermaid
sequenceDiagram
    actor Reader
    participant Page as Any HTTP(S) page
    participant Content as Content script
    participant Worker as Background worker
    participant API as Iris FastAPI
    participant DB as PostgreSQL

    Reader->>Page: Select text
    Content->>Content: Capture range, quote, context, offsets
    Content-->>Reader: Show Highlight + note actions
    Reader->>Content: Click Highlight
    alt Page is not yet saved in this tab
        Content->>Worker: POST /api/browser/pages/capture
        Worker->>API: Authenticated idempotent capture
        API->>DB: Normalize URL + create bookshelf mapping
        API-->>Content: Document UUID + existing highlights
    end
    Content->>Worker: POST /api/documents/{document_uuid}/highlights
    Worker->>API: Authenticated request
    API->>DB: Insert user-owned DocumentHighlight
    DB-->>API: Highlight row
    API-->>Content: Highlight schema
    Content->>Page: Wrap located text in an Iris mark
    Content-->>Reader: Highlighted in Iris toast
    Reader->>Page: Click saved highlight
    Content-->>Reader: Note/delete popover
    Reader->>Content: Save note
    Content->>Worker: PATCH /api/highlights/{highlight_uuid}
    Worker->>API: Authenticated update
```

The selection is converted into a payload before the toolbar is clicked. This matters because clicking browser UI normally collapses the page selection. The primary action saves the highlight directly; the adjacent note action saves it and opens the note editor. Notes can also be edited later by clicking the persisted highlight.

### Anchoring and restoration

Each highlight stores:

- Exact selected `quote`.
- Up to 64 characters of `prefix` and `suffix` context.
- `start_offset` and `end_offset` in the concatenated eligible page text.
- Optional note in the backend's `comment` field.
- Color and timestamps.

On revisit, restoration tries:

1. Stored offsets when the text at those offsets still matches the quote.
2. Exact quote search scored using prefix and suffix context.
3. No placement if neither strategy is reliable.

Scripts, styles, form controls, contenteditable regions, and Iris-owned floating UI are excluded from the page-text model. PDFs, canvas-rendered text, cross-origin frames, shadow DOM, and highly dynamic virtualized pages are not fully supported in the current version.

## Privacy and permission model

The manifest registers the content script on HTTP(S) pages because selection UI must be available without opening the popup. That broad injection permission does not mean every visited URL is sent to Iris.

The privacy gate is:

```mermaid
flowchart LR
    Load["Page loads"] --> Local{"Exact or tracking-normalized URL<br/>exists in local savedUrls?"}
    Local -->|No| Ready["Selection UI ready locally;<br/>no Iris request"]
    Local -->|Yes| Resolve["Resolve URL with Iris API"]
    Resolve --> Saved{"Saved for authenticated user?"}
    Saved -->|No| Stop
    Saved -->|Yes| Activate["Restore highlights and enable selection toolbar"]
```

Relevant permissions:

- `activeTab`: read the active tab only after the user invokes the extension.
- `storage`: persist auth state and saved-URL activation hints.
- HTTP(S) content-script matches: provide local selection controls and highlight restoration.
- `securetoken.googleapis.com`: refresh Firebase tokens.
- `externally_connectable` for the Iris frontend: receive the authenticated handoff.

The extension does not request Chrome history permission and does not continuously upload general browsing activity.

## Backend data model

```mermaid
erDiagram
    USER ||--o{ USER_DOCUMENT_MAPPING : owns
    DOCUMENT ||--o{ USER_DOCUMENT_MAPPING : saved_by
    USER ||--o{ DOCUMENT_HIGHLIGHT : creates
    DOCUMENT ||--o{ DOCUMENT_HIGHLIGHT : contains
    DOCUMENT ||--o{ DOCUMENT_TAG : tagged_with
    TAG ||--o{ DOCUMENT_TAG : assigned_as

    USER_DOCUMENT_MAPPING {
        int user_id
        int document_id
        string bookshelf_status
        datetime favorited_at
        datetime read_at
        text note
        text intent_note
    }

    DOCUMENT_HIGHLIGHT {
        int user_id
        int document_id
        text quote
        text prefix
        text suffix
        int start_offset
        int end_offset
        text comment
        string color
        datetime deleted_at
    }
```

Highlights and bookshelf mappings are scoped by `user_id`. Highlight update/delete routes look up owned rows, so another authenticated user receives a not-found response rather than access to the annotation.

## UI and build architecture

Source UI lives under `extension/ui/`. Vite has three HTML entry points:

- `popup.html`
- `onboarding.html`
- `settings.html`

The build writes a clean unpacked artifact into `extension/dist/`. A preparation step copies the background worker, content script, anchoring library, content CSS, and icons, then generates an environment-specific manifest and config module from `config/environments.json`.

```mermaid
flowchart LR
    ReactSource["extension/ui/src/*.tsx"] --> TS["TypeScript"]
    TS --> Vite["Vite multi-entry build"]
    Tailwind["Tailwind + Iris tokens"] --> Vite
    Vite --> Built["extension/dist/*.html<br/>extension/dist/assets/*"]
    Static["worker + content scripts + icons"] --> Root["extension/dist/"]
    Built --> Root
    Root --> Browser["Load unpacked in Chrome / Arc"]
```

Build and validate:

```bash
npm --prefix extension/ui install
npm --prefix extension run build:local
python3 -m json.tool extension/dist/manifest.json >/dev/null
node --check extension/background.js
node --check extension/content.js
node extension/anchoring.test.js
npm --prefix frontend run build
git diff --check
```

After changing the manifest, background worker, or content script, reload the extension in `chrome://extensions` or `arc://extensions`. Existing page tabs must then be refreshed because Chrome does not replace an already-injected content-script execution context.

## Local development topology

Development and production origins are defined in `config/environments.json` and compiled into the selected artifact:

| Service | Origin |
| --- | --- |
| Iris frontend/login bridge | `http://localhost:5175` |
| Iris FastAPI backend | `http://127.0.0.1:8000` |
| Firebase token refresh | `https://securetoken.googleapis.com` |

Use `localhost` for the frontend because Firebase authorizes it as a domain; `127.0.0.1` is a different Firebase origin and the current Firebase console rejects raw IPs in its authorized-domain form.

The frontend and backend must come from the same worktree as the loaded extension. When multiple development worktrees auto-restart servers on the same ports, verify their working directories with `lsof` before debugging extension behavior.

## Failure behavior

| Failure | Current behavior |
| --- | --- |
| No extension auth | Popup and onboarding offer Sign in to Iris |
| ID token near expiry | Worker refreshes before making the request |
| API returns 401 | Worker forces one refresh and retries |
| Refresh rejected | Auth storage is cleared and login is required |
| Backend unavailable | Popup shows a retryable error; content UI shows a toast |
| Unsupported browser page | Popup explains that only regular HTTP(S) pages can be saved |
| Saved URL absent locally | Content script makes no Iris request |
| Highlight cannot be re-anchored | It remains detached rather than highlighting the wrong passage |
| Extension reloaded while a page is open | Old context may report “Extension context invalidated”; refresh the page |

## Architectural tradeoffs and next steps

Current choices preserve a narrow, explicit-save product boundary:

- Firebase refresh credentials live in extension-local storage. A production hardening option is a backend-issued, revocable extension session exchanged through a short-lived one-time code.
- Frontend and extension use matching Tailwind theme values. The repo-wide environment registry prevents origin drift between release artifacts and deployment documentation.
- `savedUrls` is bounded local state, not a complete offline index. A production sync design may need a compact server-derived activation index or explicit per-page resolution rules.
- Content scripts run in the page's DOM environment. Shadow DOM encapsulation for Iris floating UI would further reduce host-style collisions.
- Refresh-token and API behavior should gain unit tests around proactive refresh, refresh rotation, retry-once behavior, and terminal logout.

## File map

```text
extension/
├── package.json                   Build and Web Store packaging commands
├── background.js                  Renewable auth and central API proxy
├── content.js                     Saved-page activation and annotation UI
├── content.css                    Host-page highlight/toolbar styles
├── anchoring.js                   Pure highlight-location strategies
├── anchoring.test.js              Anchoring unit checks
├── icons/                         Browser action icons
├── scripts/                       Artifact preparation and ZIP packaging
├── dist/                          Generated unpacked extension
├── release/                       Generated Web Store ZIP
└── ui/
    ├── vite.config.ts             Multi-entry build into extension/dist
    ├── package.json               React/Tailwind build dependencies
    └── src/
        ├── popup.tsx
        ├── onboarding.tsx
        ├── settings.tsx
        ├── chrome.ts              Runtime-message client
        ├── index.css              Iris Tailwind theme
        └── components/            Extension UI primitives

frontend/src/
├── App.tsx                        Firebase login and extension handoff
└── firebase.ts                    Firebase app configuration/public API key

backend/iris/
├── routes/api.py                  Capture, resolve, bookshelf, highlight APIs
├── dao/bookshelf.py               Per-user save/update behavior
├── dao/highlights.py              Highlight ownership and persistence
└── models/user.py                 Mapping, tags, and highlight models
```
