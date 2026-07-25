# Iris Product Roadmap

## Product thesis

Iris should use Curius's capture, library, profile, and friend loop while changing the intelligence and privacy model:

> A friend-private personal knowledge system where AI search can deliberately operate over your corpus, your friends' reading, or the full Iris index.

Human-triggered indexing remains desirable, but it is not on the critical path for the first social product.

## Decisions

- Profiles and reading activity are private to the owner and accepted friends.
- Friendships are reciprocal. A directed request has `requested` state and becomes `connected` only when the recipient accepts.
- Users can attach personal websites to their profiles. Ownership verification is deferred; assume honest input for now.
- Search remains AI chat only. Full-text search is an internal retrieval tool rather than a separate user-facing mode.
- Chat has explicit corpus modes: `Mine`, `Friends`, and `All Iris`.
- Friends get a reading feed based on saved/read bookshelf activity.
- Explore and Graph become contextual modes inside Directory instead of standalone primary destinations.
- Human-triggered crawl/index priority is a later improvement.

## Product shape

```text
Private profile
├── personal websites
├── bookshelf and reading activity
├── friends
│   ├── incoming requests
│   ├── outgoing requests
│   └── connected friends
└── AI chat
    ├── Mine
    ├── Friends
    └── All Iris

Directory
├── Sources
├── Explore
└── Graph
```

## PR sequence

### 1. Private profiles and friendship foundation

- Add private user profiles with stable usernames and bios.
- Attach personal websites to existing `Source` rows without verification.
- Add user-to-user friendships with `requested` and `connected` states.
- Add request, accept, cancel/decline, disconnect, user-finder, friends-list, and friend-only profile APIs.
- Keep full profiles inaccessible until friendship acceptance.

### 2. AI chat corpus modes

- Add `mine`, `friends`, and `all` to agent chat requests.
- Filter candidate documents before they reach keyword, semantic, tag, category, or metadata tools.
- `Mine` searches the current user's non-archived bookshelf corpus.
- `Friends` searches non-archived documents saved or read by connected users.
- `All Iris` searches the existing global essay index.
- Keep FTS available to the agent through keyword search; do not expose an FTS mode.
- Pass the active user to feedback/personalization lookups instead of using the singleton local user.

### 3. Profiles, friendships, and reading feed UI

- Add a People destination with Find people, Requests, Friends, and Feed sections.
- Add profile editing and personal-website attachment.
- Let connected friends open each other's profiles.
- Add a reverse-chronological friend reading feed showing the friend, document, source, and reading state.
- Do not expose notes or highlights in the feed.

### 4. Directory consolidation

- Add Sources, Explore, and Graph modes inside Directory.
- Preserve source profile and document navigation from the visual modes.
- Remove standalone Explore and Graph items from primary navigation.
- Keep their routes as compatibility redirects or internal routes until old links are no longer needed.

### 5. Later: human-triggered indexing

- Prioritize explicitly added pages and personal websites in the crawl queue.
- Preserve user-owned placeholders when fetching fails.
- Add durable retries, ingestion status, and capture-to-searchable latency.
- Weight notes and highlights more strongly than passive opens.

## Privacy boundary

Friendship is the only sharing boundary for the first version:

- The owner can always see their profile and reading data.
- A requested friendship reveals only minimal discovery identity.
- An accepted friend can see the profile, attached websites, and reading activity.
- Non-friends cannot retrieve a full user profile or personal reading corpus.
- `All Iris` searches globally indexed documents, not private annotations or private user metadata.
- Access filtering happens before candidate ranking and before LLM context construction.

## Feed definition

The first feed is deliberately simple:

- Reverse chronological.
- Accepted friends only.
- Saved and read documents; archived/dismissed items excluded.
- One row per friend/document activity with friend, document, source, state, and timestamp.
- No likes, comments, follower counts, popularity scores, or opaque recommendation ranking.

Auto-mixing can later rank or diversify this feed, but a legible chronological feed should establish the social value first.

## Navigation

Near-term primary destinations:

- **Search** — AI chat with Mine/Friends/All modes.
- **Bookshelf** — durable personal reading state.
- **People** — profile, friends, requests, and reading feed.
- **Directory** — source table, source profiles, Explore, and Graph modes.
- **Admin** — administrators only.

Search remains the default action for now. A future Home destination is only justified after the friend feed or an auto-mix consistently provides more value than opening directly into chat.

## What already exists

- Authenticated users and per-user document state.
- Bookshelf status, notes, tags, highlights, collections, and share-link collections.
- Browser capture and in-page highlighting.
- Hybrid keyword/semantic AI search.
- Source/document/link corpus and source-level AI profiles.
- Embedding Explore and source/document Graph views.
- Source crawl planning and indexing infrastructure.

## Guardrails

- Do not let a pending request grant profile or corpus access.
- Do not send private notes, highlights, or user metadata to the LLM in Friends or All modes.
- Do not treat an attached website as verified identity.
- Do not expose user-facing numeric relevance scores.
- Do not add a separate FTS product mode until there is evidence that users need deterministic literal search.
- Do not optimize the feed for time spent.
