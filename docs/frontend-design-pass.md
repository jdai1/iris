# Iris Frontend Design Pass — Implementation Spec

Audience: an implementing agent (Codex) with no prior context on this task. This
spec is self-contained. Read it fully before starting. A separate reviewer will
inspect the result afterward, so keep the diff clean, wave-by-wave, and
build-verified.

## Goal

Polish the existing frontend and add a dark mode, **without changing the layout
or information architecture** (those are already good). Keep the current
disciplined editorial minimalism (pure grayscale, Inter, zero border-radius,
hairline borders, uppercase micro-labels). Spend all new "boldness" in exactly
two places:

1. A **restrained indigo accent** (the app is named *Iris* — indigo fits).
2. A genuine **light/dark theme**.

Everything else gets quietly tightened. One real bug is fixed along the way: the
UI is built entirely around the Inter typeface but Inter is never actually
loaded, so most machines silently fall back to system fonts.

## Ground rules

- **No layout/IA changes.** Do not move nav, restructure views, or rename routes.
- **Light mode must look essentially unchanged** after the token migration
  (Wave 1). The token layer is a refactor with a safety net, not a restyle. The
  only intended light-mode visual changes are the deliberate ones in Wave 2
  (accent, focus rings, hover, type scale, skeletons, scrollbars).
- **Run `npm --prefix frontend run build` after each wave** and fix any TS/build
  errors before moving on.
- Respect `prefers-reduced-motion` for every animation/transition you add.
- Do not introduce new dependencies beyond the one font package named below.

## Repo orientation

- App is React 19 + Vite + Chakra UI v3, in `frontend/`.
- Entry: `frontend/index.html` → `frontend/src/main.tsx` → `frontend/src/App.tsx`.
- Global Chakra theme + `iris.*` color tokens: `frontend/src/main.tsx`.
- CSS is plain CSS, imported in `frontend/src/index.css`, split across:
  - `src/styles/base.css` — app shell, sidebar, auth landing, search input, tooltips
  - `src/styles/search.css` — chat/search results, bookshelf, document cards
  - `src/styles/directory.css` — directory + profile pages
  - `src/styles/admin.css` — admin tables, metrics, status pills, pagination
  - `src/styles/graph.css` — graph explorer (SVG-based)
  - `src/styles/explorer.css` — embedding explorer (canvas/WebGL-based)
  - `src/styles/responsive.css` — media queries only (no colors to migrate)
- Components: `src/components/{DocumentCard,Pagination,ProfileAnalysisCard,StatusPill}.tsx`,
  plus `src/CorpusSearchForm.tsx`.
- Two canvas/WebGL views need special dark-mode handling:
  `src/GraphExplorer.tsx` (SVG) and `src/EmbeddingExplorer.tsx` (three.js + 2D canvas labels).
- Views (`type View`): `search | bookshelf | directory | explore | graph | admin`.
- Existing localStorage pattern to mirror: `VIEW_STORAGE_KEY = 'iris.activeView'`
  in `App.tsx` (~line 89), read ~line 107, written ~line 2398.
- Settings menu (natural home for a theme toggle) is in `App.tsx` ~line 2501,
  inside the `.settings-menu` block.

The Chakra layer is clean: the JSX uses only `iris.100/300/500/700/900` and has
**no inline hex literals**. So redefining `iris.*` to reference CSS variables
makes the entire inline-styled layer theme-aware for free.

---

# Wave 1 — Foundation (invisible; prerequisite for everything else)

## 1.1 Fix the Inter font bug

```bash
npm --prefix frontend install @fontsource-variable/inter
```

In `src/main.tsx`, add at the top with the other imports:

```ts
import '@fontsource-variable/inter';
```

In `src/index.css` `:root` (or `base.css` `:root`), enable the refined Inter
rendering globally on `body`:

```css
font-feature-settings: "cv11", "ss01";
font-optical-sizing: auto;
```

Keep the existing `font-family` fallback stack. Verify the build bundles the
font (no external network request at runtime — it must work offline).

## 1.2 Define the token layer

Add a token block to `:root` in `base.css` (it is imported first). Use these
**semantic** tokens. Light values below are chosen to match the current design
(so light mode does not visibly change); dark values are the new theme.

```css
:root {
  color-scheme: light;

  /* Surfaces */
  --bg: #ffffff;
  --bg-raised: #ffffff;      /* popovers/panels — distinguished by border+shadow */
  --bg-sunken: #f7f7f5;      /* chips, neutral status pill bg */
  --bg-hover: #f5f5f5;       /* hovered rows/buttons */
  --bg-active: #f1f1f1;      /* selected rows */

  /* Ink */
  --text: #111111;           /* primary */
  --text-secondary: #333333; /* body copy */
  --text-muted: #555555;
  --text-subtle: #777777;    /* subtle text, most labels */
  --text-faint: #8a8a8a;     /* faint eyebrows, uppercase micro-labels */
  --text-disabled: #aaaaaa;

  /* Lines */
  --border-strong: #111111;  /* structural: search underline, metric top border, source-form */
  --border: #e0e0de;         /* button/input outlines (the darker hairline family) */
  --border-subtle: #eeeeee;  /* default dividers (the most common hairline) */
  --border-faint: #f0f0f0;   /* lightest dividers */
  --border-input: #dedede;   /* input box/underline borders */

  /* Accent — indigo */
  --accent: #4f46e5;         /* indigo 600 */
  --accent-hover: #4338ca;   /* indigo 700 */
  --accent-contrast: #ffffff;/* text/icon on an accent fill */
  --accent-soft: rgba(79, 70, 229, 0.08);   /* tinted bg + text selection */
  --focus-ring: #4f46e5;

  /* Shadows (so dark mode can soften them) */
  --shadow-popover: 0 12px 28px rgba(0, 0, 0, 0.08);
  --shadow-panel: 0 18px 44px rgba(0, 0, 0, 0.08);

  /* Canvas/graph theming (used by graph.css + the two canvas views) */
  --graph-edge: rgba(17, 17, 17, 0.07);
  --graph-edge-active: rgba(17, 17, 17, 0.22);
  --graph-arrow: rgba(17, 17, 17, 0.34);
  --graph-node-stroke: rgba(255, 255, 255, 0.92);   /* halo separating nodes from bg */
  --graph-node-label: #555555;
  --graph-node-label-halo: rgba(255, 255, 255, 0.95);
  --canvas-bg: #ffffff;
  --canvas-label-halo: rgba(255, 255, 255, 0.82);
  --canvas-crosshair: rgba(17, 17, 17, 0.42);

  /* Semantic status (unchanged in light) */
  --status-good-border: #96b38d; --status-good-bg: #eef6ea; --status-good-text: #315c28;
  --status-busy-border: #9fb5d6; --status-busy-bg: #edf3fb; --status-busy-text: #284e83;
  --status-warn-border: #d4c196; --status-warn-bg: #f4f4f2; --status-warn-text: #765c1e;
  --status-bad-border:  #d59a8e; --status-bad-bg:  #fbebe8; --status-bad-text:  #8f2f20;
  --status-neutral-border: #d8d8d4; --status-neutral-bg: #f7f7f5; --status-neutral-text: #333333;
  --error-text: #8f2f20;
  --error-border: #b85542;
}
```

## 1.3 Migrate the 7 stylesheets to tokens

Replace every hardcoded color with the matching token. This is the bulk of Wave
1. **Do it context-aware, not with a blind global find/replace** — the same hex
means different things in different properties. In particular:

- `#111` / `#111111` is `--text` when it's a `color:`, but `--border-strong`
  when it's a `border`/`border-color`, and `--accent`/fill when it's a filled
  button background (see the accent rules in Wave 2).
- `#ffffff` / `#fff` is `--bg` for backgrounds, but `--accent-contrast` when it's
  the `color:` of text sitting on a dark fill (only occurrence: `explorer.css`
  `.explorer-panel a` / `.explorer-help` first rule, `color: #ffffff`).

Mapping families (consolidate near-duplicates — this is intended cleanup):

| Current hex(es) | Token |
|---|---|
| `#ffffff`, `#fff` (as background) | `--bg` |
| `#f7f7f5`, `#f4f4f2` (chip/sunken bg) | `--bg-sunken` |
| `#f8f8f8`, `#f6f6f6`, `#f5f5f5`, `#f4f4f4`, `#f7f7f7`, `#fafafa`, `#f3f3f3` (hover washes) | `--bg-hover` |
| `#f2f2f2`, `#f1f1f1` (active/selected rows) | `--bg-active` |
| `#111`, `#111111`, `#161616`, `#000000` (text) | `--text` |
| `#222`, `#222222`, `#262626`, `#2f2f2f` | `--text-secondary` |
| `#333`, `#333333`, `#444`, `#444444` | `--text-secondary` |
| `#555`, `#555555`, `#666`, `#666666`, `#6b6b6b`, `#767676` | `--text-muted` |
| `#777`, `#777777` | `--text-subtle` |
| `#858585`, `#888`, `#888888`, `#8a8a8a`, `#8a8a84` | `--text-faint` |
| `#999`, `#999999`, `#aaa`, `#aaaaaa`, `#a9a9a9`, `#cfcfcf` | `--text-disabled` |
| `#111` (as border) | `--border-strong` |
| `#e0e0de`, `#e3e3e3`, `#e5e5e5`, `#e6e6e6` | `--border` |
| `#eeeeee`, `#ededed`, `#e8e8e8`, `#e9e9e9`, `#e7e7e7`, `#ececec`, `#ececea` | `--border-subtle` |
| `#f0f0f0` | `--border-faint` |
| `#dedede`, `#dcdcdc`, `#d8d8d4`, `#cfcfcb` | `--border-input` |
| status pill hexes (`#96b38d` etc.) | matching `--status-*` token |
| `#9a3a3a`, `#8f2f20`, `#b85542` (error) | `--error-text` / `--error-border` |
| `rgba(255,255,255,x)` / `rgba(17,17,17,x)` panel tints & blur overlays | see note below |

**Translucent overlays** (the `rgba(255,255,255,0.9)` frosted panels and
`rgba(17,17,17,x)` in `graph.css`/`explorer.css`): route through the
`--graph-*` / `--canvas-*` tokens where they concern nodes/edges/labels. For the
frosted glass panel backgrounds, add `--glass-bg: rgba(255,255,255,0.9)` and
`--glass-border` tokens so dark mode can flip them to a dark translucent value.
Keep `backdrop-filter: blur(...)`.

After migration, `grep -rniE "#[0-9a-f]{3,8}" frontend/src/styles` should return
**only** the token definitions in `base.css` `:root` (and the dark `:root`
block from Wave 3). Everything else should be `var(--…)`.

## 1.4 Rewire the Chakra `iris.*` scale to the CSS variables

In `src/main.tsx`, change the `iris` color token *values* to reference the CSS
variables so the inline-styled JSX inherits theming:

```ts
colors: {
  iris: {
    50:  { value: 'var(--bg)' },
    100: { value: 'var(--bg-sunken)' },
    200: { value: 'var(--border-subtle)' },
    300: { value: 'var(--border-input)' },
    500: { value: 'var(--text-subtle)' },
    700: { value: 'var(--text-secondary)' },
    900: { value: 'var(--text)' },
  },
},
```

Also update `globalCss.body` `bg`/`color` to `var(--bg)` / `var(--text)`.

Verify: `npm --prefix frontend run build` passes and, running dev, **light mode
looks the same as before** (spot-check search, bookshelf, directory, admin,
graph, explore, and the signed-out auth landing).

---

# Wave 2 — Visible polish (light mode)

Keep it disciplined: roughly one accent moment per screen.

## 2.1 Indigo accent — apply only in these spots

- **Active nav indicator**: `sidebar-nav button[data-active="true"]::before`
  background → `--accent` (the 1px bar). Active nav *text* stays `--text`.
- **Real hyperlinks / primary text links**: `.profile-link`, `.auth-link-button`
  underline, `.message-content a` (chat link lists), `.bookshelf-detail-*` links
  → color `--accent`, hover `--accent-hover`. (Buttons that merely look like
  links stay neutral — only genuine navigational links get indigo.)
- **Primary submit affordance**: `.corpus-search button[type="submit"]` icon →
  `--text` at rest, `--accent` on hover/focus.
- **Tab/segmented active underlines** (`.tab-strip button.active`,
  `.graph-toolbar .segmented button.active`): active underline → `--accent`,
  active label stays `--text`.
- **Text selection**: `::selection { background: var(--accent-soft); }`.
- Do **not** put indigo on body text, structural black underlines (search input,
  metric top borders), or hairline borders.

## 2.2 Consistent focus-visible ring

Add one global rule and remove ad-hoc focus styling that conflicts:

```css
:where(a, button, input, select, textarea, [tabindex]):focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
  border-radius: 2px; /* ring only; do not round the elements themselves */
}
```

Keep the existing `.directory-table-row:focus-visible` behavior but recolor its
outline to `--focus-ring`. Ensure inputs that currently show focus only via a
border-color change also get the ring (or a consistent `:focus-within` ring on
their wrapper for the underline-style search inputs).

## 2.3 Tactility (hover + motion)

- Give result/document cards a hover response (currently none):
  `.document-card:hover { background: var(--bg-hover); }` — but scope it so it
  does not fight the compact cards inside the chat artifact list; test both.
  Alternatively a subtle left-border-accent on hover if a full-row wash looks
  heavy. Use judgment; keep it quiet.
- Add `transition: color 120ms ease, background-color 120ms ease` to nav
  buttons, cards, table rows, and menu items that change on hover.
- Wrap all of this in `@media (prefers-reduced-motion: no-preference) { … }` or
  add a global `@media (prefers-reduced-motion: reduce) { *{transition:none!important;animation:none!important} }` guard.

## 2.4 Typography weight cleanup

Collapse the near-duplicate weights (currently 380, 440, 520, 550, 560, 650,
660, 680 appear across the CSS + Chakra props) to a 4-step scale:

- `400` — body / inactive
- `500` — medium (labels, inactive nav, chips)
- `600` — semibold (active nav, headings, emphasis)
- `700` — bold (uppercase eyebrows, strong emphasis)

Map: 380→400; 440/520/550/560→ 500 or 600 (pick by role — headings 600, labels
500); 650/660/680→600 (or 700 for uppercase eyebrows). Update both the CSS files
and the Chakra `fontWeight=` props in `App.tsx` / `DocumentCard.tsx`. Verify
headings still read as headings.

## 2.5 Skeleton loaders

Add skeleton placeholders for the three list views that currently pop in with no
loading state (graph + explore already have spinners; leave them):

- Search results list
- Bookshelf table
- Directory table

Implement a small reusable shimmer (a `.skeleton` class: `--bg-sunken` base with
a subtle animated highlight sweep, reduced-motion → static). Render N placeholder
rows matching each list's row height while its data is loading. Wire to the
existing loading booleans in the relevant components (find the `loading`/
`isLoading` state already used for each fetch).

## 2.6 Slim styled scrollbars

Replace the fully-hidden scrollbars (`scrollbar-width: none` +
`::-webkit-scrollbar{display:none}`) in `.chat-history-list`, `.chat-artifact`,
`.bookshelf-detail-reference-grid .bookshelf-detail-link-list`, and similar with
a slim styled scrollbar:

```css
.scroll-slim { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
.scroll-slim::-webkit-scrollbar { width: 8px; height: 8px; }
.scroll-slim::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
.scroll-slim::-webkit-scrollbar-track { background: transparent; }
```

Apply to those overflow containers. (This improves scroll discoverability.)

Verify build + visual spot-check after Wave 2.

---

# Wave 3 — Dark mode

## 3.1 Theme state + toggle

- Add `THEME_STORAGE_KEY = 'iris.theme'` alongside `VIEW_STORAGE_KEY`.
- Resolve initial theme: saved value if present, else
  `window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'`.
- Apply by setting `document.documentElement.dataset.theme = theme` in an effect,
  and persist to localStorage on change (mirror the existing view-persistence
  effect).
- Add a **theme toggle** in the Settings menu (`App.tsx` ~line 2501), styled like
  the other `.settings-menu-row` items, with a sun/moon icon
  (`lucide-react` has `Sun` / `Moon`). Label: "Dark mode" / "Light mode" as a
  toggle, or a 3-state (System / Light / Dark) if easy — a simple 2-state toggle
  is acceptable.
- **Prevent FOUC**: add a tiny inline script in `index.html` `<head>` that reads
  the stored/preferred theme and sets `data-theme` on `<html>` *before* the app
  mounts:

```html
<script>
  (function(){try{var t=localStorage.getItem('iris.theme');
  if(!t){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
  document.documentElement.dataset.theme=t;}catch(e){}})();
</script>
```

## 3.2 Dark token overrides

Because Wave 1 routed everything through tokens, dark mode is one override block.
Add to `base.css`:

```css
:root[data-theme="dark"] {
  color-scheme: dark;

  --bg: #0f0f11;
  --bg-raised: #17171a;
  --bg-sunken: #1c1c20;
  --bg-hover: #1f1f24;
  --bg-active: #26262c;

  --text: #f2f2f3;
  --text-secondary: #d2d2d5;
  --text-muted: #a6a6ac;
  --text-subtle: #8a8a90;
  --text-faint: #6f6f76;
  --text-disabled: #55555b;

  --border-strong: #4a4a52;
  --border: #303036;
  --border-subtle: #26262b;
  --border-faint: #202024;
  --border-input: #3a3a41;

  /* Indigo reads lighter on dark for contrast */
  --accent: #818cf8;         /* indigo 400 */
  --accent-hover: #a5b4fc;   /* indigo 300 */
  --accent-contrast: #0f0f11;
  --accent-soft: rgba(129, 140, 248, 0.16);
  --focus-ring: #818cf8;

  --shadow-popover: 0 12px 28px rgba(0, 0, 0, 0.5);
  --shadow-panel: 0 18px 44px rgba(0, 0, 0, 0.55);

  /* Canvas/graph flips */
  --graph-edge: rgba(255, 255, 255, 0.08);
  --graph-edge-active: rgba(255, 255, 255, 0.28);
  --graph-arrow: rgba(255, 255, 255, 0.4);
  --graph-node-stroke: rgba(15, 15, 17, 0.9);       /* halo now dark */
  --graph-node-label: #b8b8be;
  --graph-node-label-halo: rgba(15, 15, 17, 0.95);
  --canvas-bg: #0f0f11;
  --canvas-label-halo: rgba(15, 15, 17, 0.82);
  --canvas-crosshair: rgba(255, 255, 255, 0.42);

  --glass-bg: rgba(23, 23, 26, 0.9);
  --glass-border: rgba(255, 255, 255, 0.08);

  /* Status: darker, still legible */
  --status-good-border: #3f6a37; --status-good-bg: #16241380; --status-good-text: #9fd18f;
  --status-busy-border: #3c5a86; --status-busy-bg: #13203380; --status-busy-text: #9fbdf0;
  --status-warn-border: #6a5a2e; --status-warn-bg: #241f1380; --status-warn-text: #d9c78f;
  --status-bad-border:  #86392e; --status-bad-bg:  #2413118 0; --status-bad-text:  #e8a99f;
  --status-neutral-border: #34343a; --status-neutral-bg: #1c1c20; --status-neutral-text: #c8c8cd;
  --error-text: #e8a99f;
  --error-border: #86392e;
}
```

(Tune the exact dark hexes by eye; the point is the structure. Fix the obvious
typos when you paste — e.g. `#13203380` is `#132033` at 50% via an 8-digit hex;
make sure all 8-digit hexes are valid.)

## 3.3 Canvas / SVG views — the hard part (do not blanket-swap)

**`graph.css` (GraphExplorer, SVG):** these currently bake in white halos and
near-black edges that assume a white backdrop. Point them at tokens:

- `.graph-edge` stroke → `var(--graph-edge)`; `.graph-edge.active` →
  `var(--graph-edge-active)`; arrow marker fill → `var(--graph-arrow)`.
- `.graph-node circle` stroke → `var(--graph-node-stroke)` (the halo that
  separates nodes from the background — must flip dark in dark mode).
- `.graph-node text` fill → `var(--graph-node-label)`, its `stroke` (halo) →
  `var(--graph-node-label-halo)`.
- The `.graph-node.related/.active/.muted` stroke rgba values → derive from the
  same tokens or add `--graph-node-stroke-strong` etc. Keep opacities.
- Frosted `.graph-panel` etc. → `--glass-bg` / `--glass-border`.
- **Node fill colors**: check `GraphExplorer.tsx` for how node fill is computed.
  If nodes are filled with a fixed light/dark value in JS, make it theme-aware
  (read `document.documentElement.dataset.theme`). If fills come from the data,
  ensure they remain visible on the dark canvas.

**`EmbeddingExplorer.tsx` (three.js + 2D canvas labels):** colors are in JS.

- The **24-color category palette** (top of the file, `#47c2ff` … `#eab308`) is
  **data encoding — keep it vivid, do not tokenize**. It works on both backgrounds.
- The **canvas clear/background color** must become theme-aware. Read the theme
  (e.g. `const dark = document.documentElement.dataset.theme === 'dark'`, or read
  a CSS var via `getComputedStyle`) and set the renderer clear color / scene
  background to `--canvas-bg` accordingly. Re-run on theme change.
- The **2D label halos** drawn with `rgba(255,255,255,x)` (`fillStyle`/
  `strokeStyle` around line 124–152) must flip to the dark halo in dark mode
  (use `--canvas-label-halo` / read theme). The `rgba(17,17,17,x)` label text /
  point outlines likewise flip.
- The **crosshair** (`explorer.css .explorer-crosshair`, `rgba(17,17,17,0.42)`)
  → `var(--canvas-crosshair)`.
- The base gray `#9ca3af` (line ~47) used as a neutral point color: keep, but
  verify it's visible on both backgrounds; if it disappears on light, pick a
  theme-aware neutral.
- Frosted `.explorer-panel`, `.explorer-loading`, `.explorer-start`,
  `.explorer-tooltip`, `.explorer-focus-label` backgrounds → `--glass-bg` /
  tokens.

Practical approach for the canvas views: add a `useTheme()`-style read (a small
hook or just read `document.documentElement.dataset.theme` and subscribe to a
`MutationObserver` on `documentElement` `data-theme`, or lift the theme value
from App via context/prop) so the three.js scene and 2D label draws re-render
when the theme flips. A prop passed from `App` is simplest.

## 3.4 Verify

- `npm --prefix frontend run build` passes.
- Toggle the theme and spot-check **all six views + auth landing** in both
  themes: search, bookshelf, directory, explore (embedding canvas), graph,
  admin. Pay special attention to: graph node/edge legibility on dark, embedding
  point + label legibility on dark, status pills, popovers/menus, focus rings,
  and that no element has stranded white/black backgrounds.
- Confirm no FOUC on reload in dark mode.
- Confirm `prefers-reduced-motion` disables the skeleton shimmer and hover
  transitions.

---

# Handoff checklist

- [ ] Wave 1: font loads (offline), all `styles/*.css` colors are `var(--…)`,
      Chakra `iris.*` → CSS vars, light mode visually unchanged, build green.
- [ ] Wave 2: indigo accent in the listed spots only, global focus ring, card
      hover + transitions, 4-step weight scale, skeletons on 3 lists, slim
      scrollbars, reduced-motion respected, build green.
- [ ] Wave 3: theme state + persisted toggle in Settings, no-FOUC inline script,
      dark token block, graph + embedding canvases legible and theme-reactive,
      all views checked in both themes, build green.

Leave the diff reviewable and grouped by wave (ideally 3 commits). Do not
refactor unrelated code.
