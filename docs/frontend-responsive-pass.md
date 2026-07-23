# Iris Frontend — Responsiveness / Auto-Resize Spec

Audience: an implementing agent (Codex). Self-contained. This is a **separate,
smaller** pass from `frontend-design-pass.md` (tokens/dark mode). It can be done
before or after that one; where they overlap (`responsive.css`), coordinate.

## Goal

Make the existing layouts **fluidly auto-resize** instead of relying on fixed
pixel columns + horizontal scroll. No IA changes — same views, same content,
just adaptive. Target: looks right from ~360px phones up through ultrawide,
with no side-scrolling tables and no hardcoded structural widths.

## Current problems (facts in the code today)

1. **Tables horizontal-scroll instead of reflowing.** `.bookshelf-table-row`
   (`styles/search.css`) is a fixed 6-col grid; `.directory-table-row`
   (`styles/directory.css`) and `.admin-table` (`styles/admin.css`) similar. On
   narrow screens `responsive.css` just sets `min-width: 920px / 760px / 900px`
   + `overflow-x: auto`, forcing side-scroll on mobile.
2. **Search bar width hardcodes the sidebar.** In `styles/base.css`:
   `--app-search-width: min(760px, calc(100vw - 208px - 48px))` bakes in the
   literal `208px` sidebar width (also used in `.directory-view .profile-panel`
   width math in `directory.css`). Brittle.
3. **Fixed column counts.** `.metric-grid` (`admin.css`) is `repeat(6, 1fr)`,
   only dropping to `repeat(2, …)` at one breakpoint. Not fluid.
4. **`DocumentCard` adapts by prop, not width.** It renders full-width in results
   and narrow in the chat-artifact rail, switching via a `compact` prop instead
   of the container's actual width.
5. **Some fixed px type/spacing** (e.g. hero/heading sizes) don't scale.

## What to do

### 1. Kill the hardcoded sidebar width; drive layout from the container

- Add a `--sidebar-w` token in `:root` (`base.css`), default `208px`, and use it
  everywhere the `208px` literal currently appears (search width calc, profile
  panel width/margin math in `directory.css`). Single source of truth.
- Prefer container-relative sizing over `100vw - literal` math. The workspace is
  already `width: min(1240px, 100%)`; let the search bar be
  `--app-search-width: min(760px, 100%)` **within its own container** rather than
  subtracting the sidebar from the viewport. Verify the full-bleed search view
  still aligns (it uses `.workspace-search`). If a viewport calc is unavoidable,
  use `calc(100vw - var(--sidebar-w) - …)` so it tracks the token.

### 2. Tables reflow to stacked cards on narrow screens (no side-scroll)

For `.bookshelf-table`, `.directory-table`, and the admin tables: below a
breakpoint (~720px), stop being a fixed multi-column grid and **stack each row
into a labeled card** instead of `min-width + overflow-x: auto`.

- Remove the `min-width: 920px/760px/900px` + horizontal-scroll fallbacks.
- For the CSS-grid tables (bookshelf/directory), under the breakpoint switch the
  row to `grid-template-columns: 1fr` (or `auto / 1fr` label:value pairs) so
  cells wrap vertically. Hide the sticky header row on mobile (its columns no
  longer map) and, if a cell needs context without the header, expose a label
  via a `data-label` attribute + `::before` (only on mobile).
- For the `<table>`-based admin table: either apply the same
  `display:block`-rows-as-cards treatment under the breakpoint, or — since admin
  is a power-user/desktop surface — a slim horizontal scroll is acceptable there
  if stacking is too invasive. Bookshelf + directory **must** stack (they're the
  reader-facing views).

### 3. Fluid grids via auto-fit/auto-fill

Replace fixed column counts with intrinsic responsive grids so they resize
without breakpoints:

- `.metric-grid`: `grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));`
  (drop the `repeat(6…)` + the `repeat(2…)` media override).
- Any other fixed `repeat(N, …)` card/chip grids: same `auto-fit, minmax()`
  pattern where it makes sense (check `.bookshelf-add-link`, chip rows). Keep
  single-purpose toolbars as-is if auto-fit would look odd.

### 4. Container queries for context-adaptive components

`DocumentCard` and the results/answer split should respond to the space they're
actually in, not the viewport:

- Mark the relevant wrappers as query containers:
  `.results-list, .chat-artifact { container-type: inline-size; }` (name them if
  helpful, e.g. `container: results / inline-size;`).
- Convert `DocumentCard`'s density from the `compact` prop toward
  `@container (max-width: NNNpx)` rules where feasible (smaller title, tighter
  padding, hide the reason line) so the same card looks right in the wide results
  column and the narrow artifact rail. Keep the `compact` prop as a fallback if a
  full container-query migration is risky — but at minimum add container queries
  so it degrades gracefully at in-between widths.
- `.results-layout` (`grid-template-columns: minmax(0,1fr) 360px`): make the
  answer panel collapse under the sidebar-inclusive width, not just a viewport
  breakpoint — a container query on the workspace is cleaner than the current
  `@media (max-width: 980px)` rule.

### 5. Fluid type + spacing

- Give the large display/hero and section headings `clamp()` sizes so they scale
  (e.g. `font-size: clamp(20px, 2.4vw, 28px)` for section headers; the auth
  landing link already uses `clamp()` — extend that approach to
  `.profile-heading h3`, `.section-header h2`, `.bookshelf-detail-header h3`).
- Where fixed gaps/padding cause cramping on mobile, use `clamp()` or the
  existing `--app-search-left` token so spacing tracks viewport.

### 6. Keep the safety floor

- Test at 360px, 768px, 1024px, 1440px, and an ultrawide.
- Nothing should cause horizontal page scroll (`overflow-x` on `body` should
  never trigger). Tables stack; long titles ellipsize (they already do — keep
  `text-overflow: ellipsis` intact).
- `img`/canvas/svg stay `max-width: 100%`.
- Don't regress the existing `responsive.css` mobile behaviors for the sidebar
  (it becomes a top bar under 980px) — keep that, just replace the table
  side-scroll and hardcoded-width bits.

## Files to touch

- `styles/base.css` — add `--sidebar-w`; fix `--app-search-width`.
- `styles/directory.css` — profile panel width math → token; table stacking.
- `styles/search.css` — bookshelf table stacking; container-type wrappers.
- `styles/admin.css` — `.metric-grid` auto-fit; admin table decision.
- `styles/responsive.css` — remove `min-width + overflow-x` table hacks; adjust
  breakpoints that duplicate what auto-fit/container queries now handle.
- `components/DocumentCard.tsx` — container-query classes (+ optional prop
  cleanup).
- Possibly `App.tsx` — add `data-label` attributes on table cells if using the
  `::before` label technique for stacked rows.

## Verify

- `npm --prefix frontend run build` passes.
- Manually resize the window through the breakpoints above for: search results,
  bookshelf, directory, admin. Confirm: no table side-scroll on mobile, search
  bar width tracks the container, metric grid reflows smoothly, `DocumentCard`
  looks right in both the results column and the chat-artifact rail.
- Confirm no horizontal page scrollbar at any width.
