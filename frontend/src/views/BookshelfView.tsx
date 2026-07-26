import { FormEvent, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
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
import { OverflowText } from '../components/OverflowText';
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
    if (!addDrawerOpen) return;
    function closeAddDrawerOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setAddDrawerOpen(false);
    }
    window.addEventListener('keydown', closeAddDrawerOnEscape);
    return () => window.removeEventListener('keydown', closeAddDrawerOnEscape);
  }, [addDrawerOpen]);

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
    <section className="min-h-svh p-4 sm:p-6">
      <div className="grid min-h-[calc(100svh-3rem)] overflow-hidden rounded-xl border bg-card lg:grid-cols-[11rem_minmax(0,1fr)]">
        <aside className="border-b bg-muted/20 p-3 lg:border-r lg:border-b-0">
          <div className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Library</div>
          <button className={`flex h-9 w-full items-center justify-between rounded-md px-2 text-sm ${activeView === 'unread' ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground'}`} type="button" onClick={() => setActiveView('unread')}>
            <span className="truncate">Read next</span>
            <small className="ml-2 tabular-nums">{entries.filter((entry) => entry.status === 'saved').length}</small>
          </button>
          <button className={`flex h-9 w-full items-center justify-between rounded-md px-2 text-sm ${activeView === 'favorites' ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground'}`} type="button" onClick={() => setActiveView('favorites')}>
            <span className="truncate">Favorites</span>
            <small className="ml-2 tabular-nums">{entries.filter((entry) => entry.favorited).length}</small>
          </button>
          <button className={`flex h-9 w-full items-center justify-between rounded-md px-2 text-sm ${activeView === 'reading-log' ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground'}`} type="button" onClick={() => setActiveView('reading-log')}>
            <span className="truncate">Reading log</span>
            <small className="ml-2 tabular-nums">{entries.filter((entry) => entry.status === 'read').length}</small>
          </button>
          <div className="my-3 h-px bg-border" />
          <div className="flex items-center justify-between px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <span>Collections</span>
            <button className="grid size-6 place-items-center rounded hover:bg-accent hover:text-accent-foreground"
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
            <form className="px-1 pb-1" onSubmit={submitCollection}>
              <input
                className="h-8 w-full rounded-md border bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring/20"
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
              className={`flex h-9 w-full items-center justify-between gap-2 rounded-md px-2 text-sm ${activeView === `collection:${collection.id}` ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground'}`}
              type="button"
              onClick={() => setActiveView(`collection:${collection.id}`)}
            >
              <OverflowText>{collection.name}</OverflowText>
              <small className="shrink-0 tabular-nums">{collection.items.length}</small>
            </button>
          ))}
        </aside>

        <div className="min-w-0">
          <div className="flex min-h-14 items-center justify-between gap-3 border-b px-4 py-2">
            <form
              className="flex h-9 max-w-md flex-1 items-center gap-2 rounded-md border bg-background px-3 focus-within:ring-2 focus-within:ring-ring/20"
              onSubmit={(event) => event.preventDefault()}
            >
              <label className="sr-only" htmlFor="bookshelf-collection-search">Add documents</label>
              <Search className="size-3.5 text-muted-foreground" />
              <input
                className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                id="bookshelf-collection-search"
                value={filterQuery}
                onChange={(event) => setFilterQuery(event.target.value)}
                placeholder={bookshelfFilterPlaceholder(activeView, activeCollection)}
              />
            </form>
            <div className="flex items-center gap-2">
              <button
                className="grid size-9 place-items-center rounded-md border bg-background text-muted-foreground shadow-xs hover:bg-accent hover:text-accent-foreground"
                type="button"
                onClick={() => setAddDrawerOpen(true)}
                aria-label="Add documents"
                data-tooltip="Add documents"
              >
                <Plus size={16} />
              </button>
              {selectedDocumentUuids.size > 0 && (
                <>
                  <div className="text-xs text-muted-foreground" aria-label="Selected documents">
                    <span aria-live="polite">{selectedDocumentUuids.size} selected</span>
                  </div>
                  <div className="relative" ref={bulkActionsRef}>
                    <button
                      className="grid size-9 place-items-center rounded-md border bg-background text-muted-foreground shadow-xs hover:bg-accent hover:text-accent-foreground"
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
                      <div className="absolute right-0 top-11 z-20 grid min-w-48 gap-1 rounded-lg border bg-popover p-1 text-popover-foreground shadow-lg" role="menu">
                    {collections.length > (activeCollection ? 1 : 0) && (
                      <select
                        className="h-8 rounded-md border bg-background px-2 text-xs"
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
                    <button className="flex h-8 items-center gap-2 rounded-md px-2 text-sm text-destructive hover:bg-destructive/10" type="button" role="menuitem" onClick={() => {
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
                  className={`grid size-9 place-items-center rounded-md border shadow-xs ${confirmDeleteCollectionId === activeCollection.id ? 'border-destructive bg-destructive text-white' : 'border-destructive/30 bg-background text-destructive hover:bg-destructive/10'}`}
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
            <form className="grid grid-cols-1 gap-2 border-b p-4 sm:grid-cols-[2fr_1fr_auto]" onSubmit={submitLink}>
              <input className="h-9 rounded-md border bg-background px-3 text-sm" value={linkUrl} onChange={(event) => setLinkUrl(event.target.value)} placeholder="Paste a URL..." />
              <input className="h-9 rounded-md border bg-background px-3 text-sm" value={linkTitle} onChange={(event) => setLinkTitle(event.target.value)} placeholder="Title override" />
              <Button type="submit" disabled={saving || !linkUrl.trim()}>Save</Button>
            </form>
          )}

          {error && <div className="m-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
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
            <div className="grid place-items-center gap-4 px-6 py-20 text-center">
              <h3 className="text-base font-medium">No rows yet</h3>
              <button className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90" type="button" onClick={onDiscover}>
                <Search size={15} />
                {discoverLabel}
              </button>
            </div>
          )}
        </div>
      </div>
      {addDrawerOpen && createPortal(
        <>
          <button
            className="fixed inset-0 z-40 bg-black/35 backdrop-blur-[1px]"
            type="button"
            aria-label="Close add documents"
            onClick={() => setAddDrawerOpen(false)}
          />
          <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l bg-background shadow-2xl" aria-label="Add documents">
          <header className="flex items-center justify-between border-b px-5 py-4">
            <div className="min-w-0">
              <strong className="block font-medium">Add documents</strong>
              <small className="block truncate text-muted-foreground">{activeCollection?.name ?? bookshelfViewLabel(activeView)}</small>
            </div>
            <button className="grid size-9 place-items-center rounded-md hover:bg-accent" type="button" onClick={() => setAddDrawerOpen(false)} aria-label="Close add documents">
              <X size={18} />
            </button>
          </header>
          <label className="mx-5 mt-4 flex h-10 items-center gap-2 rounded-md border bg-background px-3 focus-within:ring-2 focus-within:ring-ring/20">
            <Search className="size-4 text-muted-foreground" />
            <input
              className="min-w-0 flex-1 bg-transparent text-sm outline-none"
              value={collectionSearchQuery}
              onChange={(event) => setCollectionSearchQuery(event.target.value)}
              placeholder="Search the corpus..."
              autoFocus
            />
          </label>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-5">
            {collectionSearching && <p className="py-6 text-center text-sm text-muted-foreground">Searching...</p>}
            {!collectionSearching && collectionSearchQuery.trim() && collectionSearchResults.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">No documents found.</p>}
            {collectionSearchResults.map((result) => {
              const alreadyAdded = resultInActiveView(result.document.uuid, activeView, activeCollection, entries);
              return (
                <div key={result.document.uuid} className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 rounded-lg border p-3">
                  <button className="min-w-0 text-left" type="button" onClick={() => openSearchResultDrawer(result)}>
                    <strong className="block truncate text-sm font-medium">{result.document.title ?? result.document.url}</strong>
                    <small className="block truncate text-muted-foreground">{result.document.source_domain}</small>
                    <span className="mt-1 line-clamp-2 block text-xs text-muted-foreground">{result.document.summary}</span>
                  </button>
                  <button
                    className="grid size-8 place-items-center rounded-md border hover:bg-accent disabled:opacity-50"
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
        </>,
        document.body,
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
    <div className="overflow-hidden" role="table" aria-label="Loading bookshelf rows">
      <div className="grid grid-cols-[minmax(14rem,2fr)_minmax(8rem,1fr)_minmax(10rem,1.5fr)_7rem_2rem_2rem] gap-3 border-b bg-muted/40 px-4 py-2 text-xs font-semibold uppercase text-muted-foreground" role="row">
        <span>Title</span>
        <span>Tags</span>
        <span>Notes</span>
        <span>Date</span>
        <span />
        <span />
      </div>
      {Array.from({ length: 8 }).map((_, row) => (
        <div className="grid grid-cols-[minmax(14rem,2fr)_minmax(8rem,1fr)_minmax(10rem,1.5fr)_7rem_2rem_2rem] gap-3 border-b px-4 py-3 last:border-0" role="row" key={row}>
          <span className="h-4 animate-pulse rounded bg-muted" />
          <span className="h-4 animate-pulse rounded bg-muted" />
          <span className="h-4 animate-pulse rounded bg-muted" />
          <span className="h-4 animate-pulse rounded bg-muted" />
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}
