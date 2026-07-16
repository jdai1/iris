import { FormEvent, useEffect, useRef, useState } from 'react';
import { Check, MoreHorizontal, Plus, Search, Trash2, X } from 'lucide-react';
import {
  addBookshelfCollectionItem,
  createBookshelfCollection,
  createBookshelfLink,
  deleteBookshelfCollection,
  getBookshelf,
  getBookshelfCollections,
  removeBookshelfCollectionItem,
  searchDocuments,
  updateDocumentBookshelf,
} from '../api';
import { emptyPage } from '../app/paging';
import { collectionIdFromSearch, documentPath, navigateTo } from '../app/navigation';
import { DenseDocumentTable } from '../components/DenseDocumentTable';
import { Button } from '../components/ui';
import type { BookshelfCollection, BookshelfEntry, BookshelfStatus, SearchResult } from '../types';

type BookshelfViewKey = 'unread' | 'favorites' | 'reading-log' | `collection:${number}`;

function collectionViewFromLocation(): BookshelfViewKey | null {
  if (!window.location.pathname.startsWith('/bookshelf')) return null;
  const collectionId = collectionIdFromSearch(window.location.search);
  return collectionId ? `collection:${collectionId}` : 'unread';
}

export function BookshelfView({ onDiscover }: { onDiscover: () => void }) {
  const [entries, setEntries] = useState<BookshelfEntry[]>([]);
  const [collections, setCollections] = useState<BookshelfCollection[]>([]);
  const [activeView, setActiveView] = useState<BookshelfViewKey>(() => collectionViewFromLocation() ?? 'unread');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addingLink, setAddingLink] = useState(false);
  const [creatingCollection, setCreatingCollection] = useState(false);
  const [linkUrl, setLinkUrl] = useState('');
  const [linkTitle, setLinkTitle] = useState('');
  const [collectionName, setCollectionName] = useState('');
  const [filterQuery, setFilterQuery] = useState('');
  const [collectionSearchQuery, setCollectionSearchQuery] = useState('');
  const [collectionSearchResults, setCollectionSearchResults] = useState<SearchResult[]>([]);
  const [collectionSearching, setCollectionSearching] = useState(false);
  const [addDrawerOpen, setAddDrawerOpen] = useState(false);
  const [addingDocumentUuid, setAddingDocumentUuid] = useState<string | null>(null);
  const [confirmDeleteCollectionId, setConfirmDeleteCollectionId] = useState<number | null>(null);
  const [selectedDocumentUuids, setSelectedDocumentUuids] = useState<Set<string>>(new Set());
  const [bulkActionsOpen, setBulkActionsOpen] = useState(false);
  const collectionDraftRef = useRef<HTMLInputElement | null>(null);
  const bulkActionsRef = useRef<HTMLDivElement | null>(null);

  const scopedRows = filterBookshelfEntries(entries, collections, activeView);
  const tableRows = filterVisibleBookshelfEntries(scopedRows, filterQuery);
  const discoverLabel = 'Discover';
  const activeCollection = activeView.startsWith('collection:')
    ? collections.find((collection) => collection.id === Number(activeView.slice('collection:'.length))) ?? null
    : null;
  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [nextPage, loadedCollections] = await Promise.all([getBookshelf({ limit: 500 }), getBookshelfCollections()]);
      setEntries(nextPage.items);
      setCollections(loadedCollections.filter((collection) => collection.name.trim().toLowerCase() !== 'read next'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bookshelf failed');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    function syncCollectionRoute() {
      const routeView = collectionViewFromLocation();
      if (routeView) setActiveView(routeView);
    }
    window.addEventListener('popstate', syncCollectionRoute);
    return () => window.removeEventListener('popstate', syncCollectionRoute);
  }, []);

  useEffect(() => {
    if (creatingCollection) collectionDraftRef.current?.focus();
  }, [creatingCollection]);

  useEffect(() => {
    setConfirmDeleteCollectionId(null);
    setFilterQuery('');
    setCollectionSearchQuery('');
    setCollectionSearchResults([]);
    setAddDrawerOpen(false);
    setSelectedDocumentUuids(new Set());
  }, [activeView]);

  useEffect(() => {
    const visibleIds = new Set(tableRows.map((row) => row.document.uuid));
    setSelectedDocumentUuids((current) => {
      const next = new Set(Array.from(current).filter((id) => visibleIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [entries, collections, activeView]);

  useEffect(() => {
    if (selectedDocumentUuids.size === 0) setBulkActionsOpen(false);
  }, [selectedDocumentUuids.size]);

  useEffect(() => {
    if (!bulkActionsOpen) return;
    function closeBulkActions(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && bulkActionsRef.current?.contains(target)) return;
      setBulkActionsOpen(false);
    }
    function closeBulkActionsOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setBulkActionsOpen(false);
    }
    window.addEventListener('pointerdown', closeBulkActions);
    window.addEventListener('keydown', closeBulkActionsOnEscape);
    return () => {
      window.removeEventListener('pointerdown', closeBulkActions);
      window.removeEventListener('keydown', closeBulkActionsOnEscape);
    };
  }, [bulkActionsOpen]);

  useEffect(() => {
    const query = collectionSearchQuery.trim();
    if (!addDrawerOpen) return;
    if (!query) {
      setCollectionSearchResults([]);
      setCollectionSearching(false);
      return;
    }
    let cancelled = false;
    setCollectionSearching(true);
    const timeout = window.setTimeout(() => {
      searchDocuments(query, 8)
        .then((response) => {
          if (!cancelled) setCollectionSearchResults(response.results);
        })
        .catch((err) => {
          if (!cancelled) setError(err instanceof Error ? err.message : 'Could not search corpus');
        })
        .finally(() => {
          if (!cancelled) setCollectionSearching(false);
        });
    }, 60);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [addDrawerOpen, collectionSearchQuery]);

  async function submitLink(event: FormEvent) {
    event.preventDefault();
    if (!linkUrl.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createBookshelfLink({
        url: linkUrl.trim(),
        title: linkTitle.trim() || null,
      });
      setLinkUrl('');
      setLinkTitle('');
      setAddingLink(false);
      setActiveView('unread');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save link');
    } finally {
      setSaving(false);
    }
  }

  async function submitCollection(event: FormEvent) {
    event.preventDefault();
    if (!collectionName.trim()) {
      setCreatingCollection(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const collection = await createBookshelfCollection({
        name: collectionName.trim(),
        description: null,
        visibility: 'private',
      });
      setCollectionName('');
      setCreatingCollection(false);
      setCollections((current) => [...current, collection]);
      setActiveView(`collection:${collection.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create collection');
    } finally {
      setSaving(false);
    }
  }

  async function deleteActiveCollection() {
    if (!activeCollection || saving) return;
    if (confirmDeleteCollectionId !== activeCollection.id) {
      setConfirmDeleteCollectionId(activeCollection.id);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await deleteBookshelfCollection(activeCollection.id);
      setCollections((current) => current.filter((collection) => collection.id !== activeCollection.id));
      setActiveView('unread');
      setCollectionSearchQuery('');
      setCollectionSearchResults([]);
      setConfirmDeleteCollectionId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete collection');
    } finally {
      setSaving(false);
    }
  }

  async function addResultToActiveView(result: SearchResult) {
    if (saving || addingDocumentUuid === result.document.uuid) return;
    setAddingDocumentUuid(result.document.uuid);
    setError(null);
    try {
      if (activeCollection) {
        const collection = await addBookshelfCollectionItem(activeCollection.id, result.document.uuid);
        setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
        const entry = collection.items.find((item) => item.document.uuid === result.document.uuid);
        if (entry) mergeBookshelfEntry(entry);
      } else if (activeView === 'favorites') {
        const entry = await updateDocumentBookshelf(result.document.uuid, { favorited: true });
        mergeBookshelfEntry(entry);
      } else if (activeView === 'reading-log') {
        const entry = await updateDocumentBookshelf(result.document.uuid, { status: 'read' });
        mergeBookshelfEntry(entry);
      } else {
        const entry = await updateDocumentBookshelf(result.document.uuid, { status: 'saved' });
        mergeBookshelfEntry(entry);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add document');
    } finally {
      setAddingDocumentUuid(null);
    }
  }

  async function removeDocumentFromActiveView(documentUuid: string) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      if (activeCollection) {
        const collection = await removeBookshelfCollectionItem(activeCollection.id, documentUuid);
        setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
      } else if (activeView === 'favorites') {
        const entry = await updateDocumentBookshelf(documentUuid, { favorited: false });
        setEntries((current) => current.map((item) => (item.document.uuid === documentUuid ? entry : item)));
      } else {
        const entry = await updateDocumentBookshelf(documentUuid, { status: 'archived' });
        setEntries((current) => current.map((item) => (item.document.uuid === documentUuid ? entry : item)));
      }
      setSelectedDocumentUuids((current) => {
        if (!current.has(documentUuid)) return current;
        const next = new Set(current);
        next.delete(documentUuid);
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove document');
    } finally {
      setSaving(false);
    }
  }

  async function addSelectedToCollection(collectionId: number) {
    const documentUuids = Array.from(selectedDocumentUuids);
    if (documentUuids.length === 0 || saving) return;
    setSaving(true);
    setError(null);
    try {
      const updates = await Promise.all(documentUuids.map((documentUuid) => addBookshelfCollectionItem(collectionId, documentUuid)));
      const collection = updates.at(-1);
      if (collection) {
        setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
      }
      setSelectedDocumentUuids(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add selected documents');
    } finally {
      setSaving(false);
    }
  }

  async function removeSelectedFromActiveCollection() {
    if (selectedDocumentUuids.size === 0 || saving) return;
    const documentUuids = Array.from(selectedDocumentUuids);
    setSaving(true);
    setError(null);
    try {
      if (activeCollection) {
        const updates = await Promise.all(documentUuids.map((documentUuid) => removeBookshelfCollectionItem(activeCollection.id, documentUuid)));
        const collection = updates.at(-1);
        if (collection) {
          setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
        }
      } else if (activeView === 'favorites') {
        const updates = await Promise.all(documentUuids.map((documentUuid) => updateDocumentBookshelf(documentUuid, { favorited: false })));
        setEntries((current) => mergeBookshelfEntryUpdates(current, updates));
      } else {
        const updates = await Promise.all(documentUuids.map((documentUuid) => updateDocumentBookshelf(documentUuid, { status: 'archived' })));
        setEntries((current) => mergeBookshelfEntryUpdates(current, updates));
      }
      setSelectedDocumentUuids(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove selected documents');
    } finally {
      setSaving(false);
    }
  }

  function toggleBookshelfRow(entry: BookshelfEntry) {
    const documentUuid = entry.document.uuid;
    setSelectedDocumentUuids((current) => {
      const next = new Set(current);
      if (next.has(documentUuid)) next.delete(documentUuid);
      else next.add(documentUuid);
      return next;
    });
  }

  function toggleAllBookshelfRows() {
    const visibleUuids = tableRows.map((row) => row.document.uuid);
    const allSelected = visibleUuids.length > 0 && visibleUuids.every((uuid) => selectedDocumentUuids.has(uuid));
    setSelectedDocumentUuids(allSelected ? new Set() : new Set(visibleUuids));
  }

  function openBookshelfDrawer(entry: BookshelfEntry) {
    navigateTo(documentPath(entry.document.uuid));
  }

  function openSearchResultDrawer(result: SearchResult) {
    navigateTo(documentPath(result.document.uuid));
  }

  function applyBookshelfEntryUpdate(entry: BookshelfEntry) {
    mergeBookshelfEntry(entry);
  }

  function mergeBookshelfEntry(entry: BookshelfEntry) {
    setEntries((current) => current.map((item) => (item.document.uuid === entry.document.uuid ? entry : item)));
    setEntries((current) => (current.some((item) => item.document.uuid === entry.document.uuid) ? current : [entry, ...current]));
    setCollections((current) =>
      current.map((collection) => ({
        ...collection,
        items: collection.items.map((item) => (item.document.uuid === entry.document.uuid ? entry : item)),
      })),
    );
  }

  async function toggleFavorite(entry: BookshelfEntry) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateDocumentBookshelf(entry.document.uuid, { favorited: !entry.favorited });
      applyBookshelfEntryUpdate(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update favorite');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="bookshelf-view">
      <div className="bookshelf-playlist-shell">
        <aside className="bookshelf-rail">
          <div className="bookshelf-rail-label">Library</div>
          <button className={activeView === 'unread' ? 'bookshelf-rail-item bookshelf-rail-item-active' : 'bookshelf-rail-item'} type="button" onClick={() => setActiveView('unread')}>
            <span>Read next</span>
            <small>{entries.filter((entry) => entry.status === 'saved').length}</small>
          </button>
          <button className={activeView === 'favorites' ? 'bookshelf-rail-item bookshelf-rail-item-active' : 'bookshelf-rail-item'} type="button" onClick={() => setActiveView('favorites')}>
            <span>Favorites</span>
            <small>{entries.filter((entry) => entry.favorited).length}</small>
          </button>
          <button className={activeView === 'reading-log' ? 'bookshelf-rail-item bookshelf-rail-item-active' : 'bookshelf-rail-item'} type="button" onClick={() => setActiveView('reading-log')}>
            <span>Reading log</span>
            <small>{entries.filter((entry) => entry.status === 'read').length}</small>
          </button>
          <div className="bookshelf-rail-divider" />
          <div className="bookshelf-rail-section-heading">
            <span>Collections</span>
            <button
              type="button"
              onClick={() => {
                setCollectionName('');
                setCreatingCollection(true);
              }}
              aria-label="Create collection"
            >
              +
            </button>
          </div>
          {creatingCollection && (
            <form className="bookshelf-rail-draft" onSubmit={submitCollection}>
              <input
                ref={collectionDraftRef}
                value={collectionName}
                onChange={(event) => setCollectionName(event.target.value)}
                onBlur={() => {
                  if (!collectionName.trim()) setCreatingCollection(false);
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    setCollectionName('');
                    setCreatingCollection(false);
                  }
                }}
                placeholder="Untitled collection"
                disabled={saving}
              />
            </form>
          )}
          {collections.map((collection) => (
            <button
              key={collection.id}
              className={activeView === `collection:${collection.id}` ? 'bookshelf-rail-item bookshelf-rail-item-active' : 'bookshelf-rail-item'}
              type="button"
              onClick={() => setActiveView(`collection:${collection.id}`)}
            >
              <span>{collection.name}</span>
              <small>{collection.items.length}</small>
            </button>
          ))}
        </aside>

        <div className="bookshelf-table-panel">
          <div className="bookshelf-toolbar">
            <form
              className="bookshelf-toolbar-search"
              onSubmit={(event) => event.preventDefault()}
            >
              <label className="visually-hidden" htmlFor="bookshelf-collection-search">Add documents</label>
              <Search size={14} />
              <input
                id="bookshelf-collection-search"
                value={filterQuery}
                onChange={(event) => setFilterQuery(event.target.value)}
                placeholder={bookshelfFilterPlaceholder(activeView, activeCollection)}
              />
            </form>
            <div className="bookshelf-toolbar-actions">
              <button
                className="bookshelf-icon-action"
                type="button"
                onClick={() => setAddDrawerOpen(true)}
                aria-label="Add documents"
                data-tooltip="Add documents"
              >
                <Plus size={16} />
              </button>
              {selectedDocumentUuids.size > 0 && (
                <>
                  <div className="bookshelf-bulk-toolbar" aria-label="Selected documents">
                    <span aria-live="polite">{selectedDocumentUuids.size} selected</span>
                  </div>
                  <div className="bookshelf-bulk-actions" ref={bulkActionsRef}>
                    <button
                      className="bookshelf-icon-action"
                      type="button"
                      onClick={() => setBulkActionsOpen((open) => !open)}
                      aria-label="Selected document actions"
                      aria-haspopup="menu"
                      aria-expanded={bulkActionsOpen}
                      data-tooltip="Actions"
                    >
                      <MoreHorizontal size={16} />
                    </button>
                    {bulkActionsOpen && (
                      <div className="bookshelf-bulk-action-menu" role="menu">
                    {collections.length > (activeCollection ? 1 : 0) && (
                      <select
                        value=""
                        onChange={(event) => {
                          const collectionId = Number(event.target.value);
                          if (collectionId) void addSelectedToCollection(collectionId);
                        }}
                        disabled={saving}
                        aria-label="Add selected documents to collection"
                      >
                        <option value="">Add to collection...</option>
                        {collections
                          .filter((collection) => collection.id !== activeCollection?.id)
                          .map((collection) => (
                            <option key={collection.id} value={collection.id}>{collection.name}</option>
                          ))}
                      </select>
                    )}
                    <button type="button" role="menuitem" onClick={() => {
                      setBulkActionsOpen(false);
                      void removeSelectedFromActiveCollection();
                    }} disabled={saving}>
                      <Trash2 size={13} />
                      Remove
                    </button>
                      </div>
                    )}
                  </div>
                </>
              )}
              {activeCollection && (
                <button
                  className={confirmDeleteCollectionId === activeCollection.id ? 'bookshelf-icon-action bookshelf-icon-action-danger bookshelf-icon-action-confirm' : 'bookshelf-icon-action bookshelf-icon-action-danger'}
                  type="button"
                  onClick={deleteActiveCollection}
                  disabled={saving}
                  aria-label={confirmDeleteCollectionId === activeCollection.id ? 'Confirm delete collection' : 'Delete collection'}
                  data-tooltip={confirmDeleteCollectionId === activeCollection.id ? 'Confirm delete' : 'Delete collection'}
                >
                  {confirmDeleteCollectionId === activeCollection.id ? <Check size={15} /> : <Trash2 size={15} />}
                </button>
              )}
            </div>
          </div>

          {addingLink && (
            <form className="bookshelf-add-link bookshelf-add-link-compact" onSubmit={submitLink}>
              <input value={linkUrl} onChange={(event) => setLinkUrl(event.target.value)} placeholder="Paste a URL..." />
              <input value={linkTitle} onChange={(event) => setLinkTitle(event.target.value)} placeholder="Title override" />
              <Button type="submit" disabled={saving || !linkUrl.trim()} borderRadius="0">Save</Button>
            </form>
          )}

          {error && <div className="error">{error}</div>}
          {loading ? (
            <BookshelfTableSkeleton />
          ) : (
            <BookshelfTable
              rows={tableRows}
              selectedDocumentUuids={selectedDocumentUuids}
              selectionEnabled
              collectionMode={Boolean(activeCollection)}
              onToggleSelection={toggleBookshelfRow}
              onToggleAll={toggleAllBookshelfRows}
              onOpenDetail={openBookshelfDrawer}
              onToggleFavorite={toggleFavorite}
              onRemoveFromCurrent={removeDocumentFromActiveView}
            />
          )}
          {!loading && tableRows.length === 0 && (
            <div className="bookshelf-empty-cta">
              <h3>No rows yet</h3>
              <button className="bookshelf-discover-cta" type="button" onClick={onDiscover}>
                <Search size={15} />
                {discoverLabel}
              </button>
            </div>
          )}
        </div>
      </div>
      {addDrawerOpen && (
        <aside className="bookshelf-add-drawer" aria-label="Add documents">
          <header>
            <div>
              <strong>Add documents</strong>
              <small>{activeCollection?.name ?? bookshelfViewLabel(activeView)}</small>
            </div>
            <button type="button" onClick={() => setAddDrawerOpen(false)} aria-label="Close add documents">
              <X size={18} />
            </button>
          </header>
          <label className="bookshelf-add-drawer-search">
            <Search size={15} />
            <input
              value={collectionSearchQuery}
              onChange={(event) => setCollectionSearchQuery(event.target.value)}
              placeholder="Search the corpus..."
              autoFocus
            />
          </label>
          <div className="bookshelf-add-drawer-results">
            {collectionSearching && <p>Searching...</p>}
            {!collectionSearching && collectionSearchQuery.trim() && collectionSearchResults.length === 0 && <p>No documents found.</p>}
            {collectionSearchResults.map((result) => {
              const alreadyAdded = resultInActiveView(result.document.uuid, activeView, activeCollection, entries);
              return (
                <div key={result.document.uuid} className="bookshelf-add-drawer-result">
                  <button type="button" onClick={() => openSearchResultDrawer(result)}>
                    <strong>{result.document.title ?? result.document.url}</strong>
                    <small>{result.document.source_domain}</small>
                    <span>{result.document.summary}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void addResultToActiveView(result)}
                    disabled={alreadyAdded || addingDocumentUuid === result.document.uuid}
                    aria-label={alreadyAdded ? 'Document added' : 'Add document'}
                  >
                    {alreadyAdded ? <Check size={16} /> : <Plus size={16} />}
                  </button>
                </div>
              );
            })}
          </div>
        </aside>
      )}
    </section>
  );
}

function filterBookshelfEntries(entries: BookshelfEntry[], collections: BookshelfCollection[], activeView: BookshelfViewKey): BookshelfEntry[] {
  let scoped = entries;
  if (activeView === 'favorites') {
    scoped = entries.filter((entry) => entry.favorited);
  } else if (activeView === 'unread') {
    scoped = entries.filter((entry) => entry.status === 'saved');
  } else if (activeView === 'reading-log') {
    scoped = entries.filter((entry) => entry.status === 'read');
  } else if (activeView.startsWith('collection:')) {
    const collectionId = Number(activeView.slice('collection:'.length));
    scoped = collections.find((collection) => collection.id === collectionId)?.items ?? [];
  }
  return scoped;
}

function filterVisibleBookshelfEntries(entries: BookshelfEntry[], query: string): BookshelfEntry[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return entries;
  return entries.filter((entry) =>
    [entry.document.title, entry.document.url, entry.document.source_domain, entry.document.summary, entry.note, entry.intent_note]
      .some((value) => value?.toLowerCase().includes(normalized)),
  );
}

function bookshelfFilterPlaceholder(activeView: BookshelfViewKey, activeCollection: BookshelfCollection | null) {
  return `Filter ${activeCollection?.name ?? bookshelfViewLabel(activeView)}...`;
}

function bookshelfViewLabel(activeView: BookshelfViewKey) {
  if (activeView === 'favorites') return 'Favorites';
  if (activeView === 'reading-log') return 'Reading log';
  return 'Read next';
}

function resultInActiveView(documentUuid: string, activeView: BookshelfViewKey, activeCollection: BookshelfCollection | null, entries: BookshelfEntry[]) {
  if (activeCollection) return activeCollection.items.some((entry) => entry.document.uuid === documentUuid);
  const entry = entries.find((item) => item.document.uuid === documentUuid);
  if (!entry) return false;
  if (activeView === 'favorites') return entry.favorited;
  if (activeView === 'reading-log') return entry.status === 'read';
  return entry.status === 'saved';
}

function notePreview(entry: BookshelfEntry): string {
  const text = (entry.note || entry.intent_note || '').trim();
  if (!text) return '—';
  return text.split('\n')[0];
}

function mergeBookshelfEntryUpdates(current: BookshelfEntry[], updates: BookshelfEntry[]): BookshelfEntry[] {
  const byDocumentUuid = new Map(updates.map((entry) => [entry.document.uuid, entry]));
  return current.map((entry) => byDocumentUuid.get(entry.document.uuid) ?? entry);
}

function entryDate(entry: BookshelfEntry): string {
  const value = entry.read_at ?? entry.first_seen_at ?? entry.favorited_at;
  if (!value) return '';
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function BookshelfTable({
  rows,
  selectedDocumentUuids,
  selectionEnabled,
  collectionMode,
  onToggleSelection,
  onToggleAll,
  onOpenDetail,
  onToggleFavorite,
  onRemoveFromCurrent,
}: {
  rows: BookshelfEntry[];
  selectedDocumentUuids: Set<string>;
  selectionEnabled: boolean;
  collectionMode: boolean;
  onToggleSelection: (entry: BookshelfEntry) => void;
  onToggleAll: () => void;
  onOpenDetail: (entry: BookshelfEntry) => void;
  onToggleFavorite: (entry: BookshelfEntry) => void;
  onRemoveFromCurrent: (documentUuid: string) => void;
}) {
  const entriesByDocumentUuid = new Map(rows.map((entry) => [entry.document.uuid, entry]));
  const tableRows = rows.map((entry) => ({
    document: entry.document,
    tags: entry.tags,
    note: entry.note || entry.intent_note ? notePreview(entry) : undefined,
    date: entryDate(entry),
    favorited: entry.favorited,
    selected: selectedDocumentUuids.has(entry.document.uuid),
  }));

  return (
    <DenseDocumentTable
      rows={tableRows}
      ariaLabel="Bookshelf documents"
      selectionEnabled={selectionEnabled}
      showNote={!collectionMode}
      showFavorite={!collectionMode}
      showActions={collectionMode}
      showSource={false}
      sourceAsTitle
      onPrimaryClick={(row, event) => {
        const entry = entriesByDocumentUuid.get(row.document.uuid);
        if (entry) onOpenDetail(entry);
      }}
      onToggleSelection={(row) => {
        const entry = entriesByDocumentUuid.get(row.document.uuid);
        if (entry) onToggleSelection(entry);
      }}
      onToggleAll={onToggleAll}
      onToggleFavorite={(row) => {
        const entry = entriesByDocumentUuid.get(row.document.uuid);
        if (entry) onToggleFavorite(entry);
      }}
      onRemove={(row) => onRemoveFromCurrent(row.document.uuid)}
    />
  );
}

function BookshelfTableSkeleton() {
  return (
    <div className="bookshelf-table bookshelf-table-skeleton" role="table" aria-label="Loading bookshelf rows">
      <div className="bookshelf-table-row bookshelf-table-head" role="row">
        <span>Title</span>
        <span>Tags</span>
        <span>Notes</span>
        <span>Date</span>
        <span />
        <span />
      </div>
      {Array.from({ length: 8 }).map((_, row) => (
        <div className="bookshelf-table-row" role="row" key={row}>
          <span className="skeleton-line" />
          <span className="skeleton-line" />
          <span className="skeleton-line" />
          <span className="skeleton-line" />
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}
