# Save to Iris browser extension

Minimal Manifest V3 extension for Chrome and Chromium browsers, including Arc.

## Load locally

1. Start Iris at `http://127.0.0.1:8010`.
2. Open `chrome://extensions` in Chrome, or `arc://extensions` in Arc.
3. Enable **Developer mode**.
4. Choose **Load unpacked** and select this `extension` directory.
5. Pin **Save to Iris**.

The extension uses the normal Iris frontend login and securely receives a renewable Firebase session for the installed extension. The background worker refreshes authentication and proxies every Iris API call. There are no URLs or tokens for the user to configure. Open an HTTP or HTTPS page and click the extension. Opening the popup immediately saves the page through `POST /api/browser/pages/capture`; afterward you can favorite it, move it between Read next and Read, add a note, or assign topics. Select text on a saved page to create a persistent highlight, then click the highlight to add a note or delete it.

For this local prototype, Iris runs at `http://localhost:5180` with its API at `http://127.0.0.1:8010`. Firebase authorizes `localhost`; do not substitute `127.0.0.1` for the frontend origin. A packaged release should replace these development origins with the hosted Iris origins.

The popup, onboarding, and settings pages use React 19 and Chakra UI 3 with the same Iris tokens as the frontend. Build them in place with `npm --prefix extension/ui install` and `npm --prefix extension/ui run build`, then reload the unpacked extension.

## Scope

- Saves the active page title and URL immediately on click.
- Saves selected text as a persistent, page-anchored highlight.
- Edits favorite, Read next/Read, note, and topics after capture.
- Includes a first-run connection onboarding flow.
- Does not request or collect browser history; its event-driven Manifest V3 worker wakes only for extension work such as authenticated API requests.
