import { FormEvent, MouseEvent, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Check, Plus, Search, Trash2 } from 'lucide-react';
import {
  addBookshelfCollectionItem,
  createBookshelfCollection,
  createBookshelfLink,
  deleteBookshelfCollection,
  getBookshelf,
  getBookshelfCollections,
  getDocument,
  removeBookshelfCollectionItem,
  searchDocuments,
  updateDocumentBookshelf,
} from '../api';
import { emptyPage } from '../app/paging';
import { DenseDocumentTable } from '../components/DenseDocumentTable';
import { Button } from '../components/ui';
import type { BookshelfCollection, BookshelfEntry, BookshelfStatus, Document, DocumentDetail, SearchResult } from '../types';

type BookshelfViewKey = 'unread' | 'favorites' | 'reading-log' | `collection:${number}`;

export function BookshelfView({ onDiscover }: { onDiscover: () => void }) {
  const [entries, setEntries] = useState<BookshelfEntry[]>([]);
  const [collections, setCollections] = useState<BookshelfCollection[]>([]);
  const [activeView, setActiveView] = useState<BookshelfViewKey>('unread');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addingLink, setAddingLink] = useState(false);
  const [creatingCollection, setCreatingCollection] = useState(false);
  const [linkUrl, setLinkUrl] = useState('');
  const [linkTitle, setLinkTitle] = useState('');
  const [collectionName, setCollectionName] = useState('');
  const [collectionSearchQuery, setCollectionSearchQuery] = useState('');
  const [collectionSearchResults, setCollectionSearchResults] = useState<SearchResult[]>([]);
  const [collectionSearching, setCollectionSearching] = useState(false);
  const [addingDocumentId, setAddingDocumentId] = useState<number | null>(null);
  const [confirmDeleteCollectionId, setConfirmDeleteCollectionId] = useState<number | null>(null);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<Set<number>>(new Set());
  const [lastSelectedDocumentId, setLastSelectedDocumentId] = useState<number | null>(null);
  const [bulkMenuOpen, setBulkMenuOpen] = useState(false);
  const [drawerEntry, setDrawerEntry] = useState<BookshelfEntry | null>(null);
  const [drawerDetail, setDrawerDetail] = useState<DocumentDetail | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);
  const [drawerClosing, setDrawerClosing] = useState(false);
  const collectionDraftRef = useRef<HTMLInputElement | null>(null);
  const bookshelfPanelRef = useRef<HTMLDivElement | null>(null);
  const drawerRef = useRef<HTMLDivElement | null>(null);
  const drawerCloseTimeoutRef = useRef<number | null>(null);

  const tableRows = filterBookshelfEntries(entries, collections, activeView);
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
    return () => {
      if (drawerCloseTimeoutRef.current !== null) window.clearTimeout(drawerCloseTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    if (creatingCollection) collectionDraftRef.current?.focus();
  }, [creatingCollection]);

  useEffect(() => {
    setConfirmDeleteCollectionId(null);
    setCollectionSearchQuery('');
    setCollectionSearchResults([]);
    setSelectedDocumentIds(new Set());
    setLastSelectedDocumentId(null);
    setBulkMenuOpen(false);
  }, [activeView]);

  useEffect(() => {
    if (selectedDocumentIds.size === 0) setBulkMenuOpen(false);
  }, [selectedDocumentIds.size]);

  useEffect(() => {
    if (!drawerEntry) {
      setDrawerDetail(null);
      setDrawerError(null);
      return;
    }
    let cancelled = false;
    setDrawerLoading(true);
    setDrawerError(null);
    getDocument(drawerEntry.document.id)
      .then((detail) => {
        if (!cancelled) setDrawerDetail(detail);
      })
      .catch((err) => {
        if (!cancelled) setDrawerError(err instanceof Error ? err.message : 'Could not load document');
      })
      .finally(() => {
        if (!cancelled) setDrawerLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [drawerEntry?.document.id]);

  useEffect(() => {
    if (selectedDocumentIds.size === 0) return;
    function clearSelectionOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && bookshelfPanelRef.current?.contains(target)) return;
      setSelectedDocumentIds(new Set());
      setLastSelectedDocumentId(null);
      setBulkMenuOpen(false);
    }
    document.addEventListener('pointerdown', clearSelectionOnOutsideClick);
    return () => document.removeEventListener('pointerdown', clearSelectionOnOutsideClick);
  }, [selectedDocumentIds.size]);

  useEffect(() => {
    if (!drawerEntry) return;
    function closeDrawerOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && drawerRef.current?.contains(target)) return;
      closeBookshelfDrawer();
    }
    document.addEventListener('pointerdown', closeDrawerOnOutsideClick);
    return () => document.removeEventListener('pointerdown', closeDrawerOnOutsideClick);
  }, [drawerEntry, drawerClosing]);

  useEffect(() => {
    const query = collectionSearchQuery.trim();
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
    }, 160);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [collectionSearchQuery]);

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
    if (saving || addingDocumentId === result.document.id) return;
    setAddingDocumentId(result.document.id);
    setError(null);
    try {
      if (activeCollection) {
        const collection = await addBookshelfCollectionItem(activeCollection.id, result.document.id);
        setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
        const entry = collection.items.find((item) => item.document.id === result.document.id);
        if (entry) mergeBookshelfEntry(entry);
      } else if (activeView === 'favorites') {
        const entry = await updateDocumentBookshelf(result.document.id, { favorited: true });
        mergeBookshelfEntry(entry);
      } else if (activeView === 'reading-log') {
        const entry = await updateDocumentBookshelf(result.document.id, { status: 'read' });
        mergeBookshelfEntry(entry);
      } else {
        const entry = await updateDocumentBookshelf(result.document.id, { status: 'saved' });
        mergeBookshelfEntry(entry);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add document');
    } finally {
      setAddingDocumentId(null);
    }
  }

  async function removeDocumentFromActiveView(documentId: number) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      if (activeCollection) {
        const collection = await removeBookshelfCollectionItem(activeCollection.id, documentId);
        setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
      } else if (activeView === 'favorites') {
        const entry = await updateDocumentBookshelf(documentId, { favorited: false });
        setEntries((current) => current.map((item) => (item.document.id === documentId ? entry : item)));
      } else {
        const entry = await updateDocumentBookshelf(documentId, { status: 'archived' });
        setEntries((current) => current.map((item) => (item.document.id === documentId ? entry : item)));
      }
      setSelectedDocumentIds((current) => {
        if (!current.has(documentId)) return current;
        const next = new Set(current);
        next.delete(documentId);
        return next;
      });
      setBulkMenuOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove document');
    } finally {
      setSaving(false);
    }
  }

  async function addSelectedToCollection(collectionId: number) {
    const documentIds = Array.from(selectedDocumentIds);
    if (documentIds.length === 0 || saving) return;
    setSaving(true);
    setError(null);
    try {
      const updates = await Promise.all(documentIds.map((documentId) => addBookshelfCollectionItem(collectionId, documentId)));
      const collection = updates.at(-1);
      if (collection) {
        setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
      }
      setBulkMenuOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add selected documents');
    } finally {
      setSaving(false);
    }
  }

  async function removeSelectedFromActiveCollection() {
    if (selectedDocumentIds.size === 0 || saving) return;
    const documentIds = Array.from(selectedDocumentIds);
    setSaving(true);
    setError(null);
    try {
      if (activeCollection) {
        const updates = await Promise.all(documentIds.map((documentId) => removeBookshelfCollectionItem(activeCollection.id, documentId)));
        const collection = updates.at(-1);
        if (collection) {
          setCollections((current) => current.map((item) => (item.id === collection.id ? collection : item)));
        }
      } else if (activeView === 'favorites') {
        const updates = await Promise.all(documentIds.map((documentId) => updateDocumentBookshelf(documentId, { favorited: false })));
        setEntries((current) => mergeBookshelfEntryUpdates(current, updates));
      } else {
        const updates = await Promise.all(documentIds.map((documentId) => updateDocumentBookshelf(documentId, { status: 'archived' })));
        setEntries((current) => mergeBookshelfEntryUpdates(current, updates));
      }
      setSelectedDocumentIds(new Set());
      setLastSelectedDocumentId(null);
      setBulkMenuOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove selected documents');
    } finally {
      setSaving(false);
    }
  }

  function selectBookshelfRow(entry: BookshelfEntry, event: MouseEvent<HTMLDivElement>, forceSelect = false) {
    const target = event.target as HTMLElement;
    if (target.closest('a, button, select')) return;
    const documentId = entry.document.id;
    if (event.shiftKey && lastSelectedDocumentId !== null) {
      event.preventDefault();
      const startIndex = tableRows.findIndex((row) => row.document.id === lastSelectedDocumentId);
      const endIndex = tableRows.findIndex((row) => row.document.id === documentId);
      if (startIndex !== -1 && endIndex !== -1) {
        const [start, end] = startIndex < endIndex ? [startIndex, endIndex] : [endIndex, startIndex];
        setSelectedDocumentIds((current) => {
          const next = new Set(current);
          tableRows.slice(start, end + 1).forEach((row) => next.add(row.document.id));
          return next;
        });
        setLastSelectedDocumentId(documentId);
        return;
      }
    }
    if (!forceSelect && !event.metaKey && !event.ctrlKey) return;
    setSelectedDocumentIds((current) => {
      if (event.metaKey || event.ctrlKey) {
        const next = new Set(current);
        if (next.has(documentId)) {
          next.delete(documentId);
        } else {
          next.add(documentId);
        }
        return next;
      }
      return new Set([documentId]);
    });
    setLastSelectedDocumentId(documentId);
    if (forceSelect) setBulkMenuOpen(true);
  }

  function openBookshelfDrawer(entry: BookshelfEntry) {
    if (drawerCloseTimeoutRef.current !== null) window.clearTimeout(drawerCloseTimeoutRef.current);
    drawerCloseTimeoutRef.current = null;
    setDrawerClosing(false);
    setDrawerEntry(entry);
  }

  function openSearchResultDrawer(result: SearchResult) {
    openBookshelfDrawer(findBookshelfEntry(result.document.id) ?? entryFromDocument(result.document));
  }

  function findBookshelfEntry(documentId: number) {
    return entries.find((entry) => entry.document.id === documentId) ?? collections.flatMap((collection) => collection.items).find((entry) => entry.document.id === documentId) ?? null;
  }

  function closeBookshelfDrawer() {
    if (!drawerEntry || drawerClosing) return;
    setDrawerClosing(true);
    drawerCloseTimeoutRef.current = window.setTimeout(() => {
      setDrawerEntry(null);
      setDrawerClosing(false);
      drawerCloseTimeoutRef.current = null;
    }, 190);
  }

  function applyBookshelfEntryUpdate(entry: BookshelfEntry) {
    mergeBookshelfEntry(entry);
    setDrawerEntry((current) => (current?.document.id === entry.document.id ? entry : current));
  }

  function mergeBookshelfEntry(entry: BookshelfEntry) {
    setEntries((current) => current.map((item) => (item.document.id === entry.document.id ? entry : item)));
    setEntries((current) => (current.some((item) => item.document.id === entry.document.id) ? current : [entry, ...current]));
    setCollections((current) =>
      current.map((collection) => ({
        ...collection,
        items: collection.items.map((item) => (item.document.id === entry.document.id ? entry : item)),
      })),
    );
  }

  async function toggleFavorite(entry: BookshelfEntry) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateDocumentBookshelf(entry.document.id, { favorited: !entry.favorited });
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

        <div className="bookshelf-table-panel" ref={bookshelfPanelRef}>
          {(activeCollection || (selectedDocumentIds.size > 0 && bulkMenuOpen)) && (
            <div className="bookshelf-toolbar">
              {activeCollection && (
                <div className="bookshelf-toolbar-actions">
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
                </div>
              )}
              {selectedDocumentIds.size > 0 && bulkMenuOpen && (
                <div className="bookshelf-bulk-menu">
                  <span>{selectedDocumentIds.size} selected</span>
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
                      <option value="">Add to playlist...</option>
                      {collections
                        .filter((collection) => collection.id !== activeCollection?.id)
                        .map((collection) => (
                          <option key={collection.id} value={collection.id}>{collection.name}</option>
                        ))}
                    </select>
                  )}
                  <button type="button" onClick={removeSelectedFromActiveCollection} disabled={saving}>
                    <Trash2 size={13} />
                    Remove
                  </button>
                  <button type="button" onClick={() => setBulkMenuOpen(false)}>
                    Done
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="bookshelf-collection-search">
            <form
              onSubmit={(event) => {
                event.preventDefault();
              }}
            >
              <label className="visually-hidden" htmlFor="bookshelf-collection-search">Add documents</label>
              <div>
                <Search size={14} />
                <input
                  id="bookshelf-collection-search"
                  value={collectionSearchQuery}
                  onChange={(event) => setCollectionSearchQuery(event.target.value)}
                  placeholder={bookshelfSearchPlaceholder(activeView, activeCollection)}
                />
              </div>
            </form>
            {collectionSearching && <p>Searching...</p>}
            {collectionSearchResults.length > 0 && (
              <div className="bookshelf-collection-results">
                {collectionSearchResults.map((result) => {
                  const alreadyAdded = resultInActiveView(result.document.id, activeView, activeCollection, entries);
                  return (
                    <div
                      key={result.document.id}
                      className="bookshelf-collection-result"
                      role="button"
                      tabIndex={0}
                      onClick={() => openSearchResultDrawer(result)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') openSearchResultDrawer(result);
                      }}
                    >
                      <span>
                        <strong>{result.document.title ?? result.document.url}</strong>
                        <small>{result.document.source_domain}</small>
                      </span>
                      <span>{result.document.summary}</span>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          void addResultToActiveView(result);
                        }}
                        disabled={alreadyAdded || addingDocumentId === result.document.id}
                        aria-label={alreadyAdded ? 'Document added' : 'Add document'}
                        data-tooltip={alreadyAdded ? 'Added' : 'Add document'}
                      >
                        {alreadyAdded ? <Check size={14} /> : <Plus size={14} />}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
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
              selectedDocumentIds={selectedDocumentIds}
              selectionEnabled
              onRowClick={selectBookshelfRow}
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
      {drawerEntry && (
        <>
          <button className={drawerClosing ? 'drawer-backdrop drawer-closing' : 'drawer-backdrop'} type="button" aria-label="Close details" onClick={closeBookshelfDrawer} />
          <BookshelfDetailDrawer
            entry={drawerEntry}
            detail={drawerDetail}
            collections={collections}
            loading={drawerLoading}
            error={drawerError}
            drawerRef={drawerRef}
            closing={drawerClosing}
            onEntryChange={(entry) => {
              applyBookshelfEntryUpdate(entry);
            }}
            onClose={closeBookshelfDrawer}
          />
        </>
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

function bookshelfSearchPlaceholder(activeView: BookshelfViewKey, activeCollection: BookshelfCollection | null) {
  if (activeCollection) return `Search corpus to add to ${activeCollection.name}...`;
  if (activeView === 'favorites') return 'Search corpus to favorite...';
  if (activeView === 'reading-log') return 'Search corpus to mark read...';
  return 'Search corpus to add to Read next...';
}

function resultInActiveView(documentId: number, activeView: BookshelfViewKey, activeCollection: BookshelfCollection | null, entries: BookshelfEntry[]) {
  if (activeCollection) return activeCollection.items.some((entry) => entry.document.id === documentId);
  const entry = entries.find((item) => item.document.id === documentId);
  if (!entry) return false;
  if (activeView === 'favorites') return entry.favorited;
  if (activeView === 'reading-log') return entry.status === 'read';
  return entry.status === 'saved';
}

function entryFromDocument(document: Document): BookshelfEntry {
  return {
    document,
    status: 'saved',
    favorited: false,
    note: null,
    intent_note: null,
    tags: [],
    first_seen_at: null,
    read_at: null,
    archived_at: null,
    favorited_at: null,
  };
}

function notePreview(entry: BookshelfEntry): string {
  const text = (entry.note || entry.intent_note || '').trim();
  if (!text) return 'No note';
  return text.split('\n')[0];
}

function mergeBookshelfEntryUpdates(current: BookshelfEntry[], updates: BookshelfEntry[]): BookshelfEntry[] {
  const byDocumentId = new Map(updates.map((entry) => [entry.document.id, entry]));
  return current.map((entry) => byDocumentId.get(entry.document.id) ?? entry);
}

function BookshelfDetailDrawer({
  entry,
  detail,
  collections,
  loading,
  error,
  drawerRef,
  closing,
  onEntryChange,
  onClose,
}: {
  entry: BookshelfEntry;
  detail: DocumentDetail | null;
  collections: BookshelfCollection[];
  loading: boolean;
  error: string | null;
  drawerRef: React.RefObject<HTMLDivElement | null>;
  closing: boolean;
  onEntryChange: (entry: BookshelfEntry) => void;
  onClose: () => void;
}) {
  const document = detail ?? entry.document;
  const containingCollections = collections.filter((collection) =>
    collection.items.some((item) => item.document.id === entry.document.id),
  );
  const [noteDraft, setNoteDraft] = useState(entry.note ?? entry.intent_note ?? '');
  const [tagDraftOpen, setTagDraftOpen] = useState(false);
  const [tagDraft, setTagDraft] = useState('');
  const [savingNote, setSavingNote] = useState(false);
  const [savingTags, setSavingTags] = useState(false);
  const [referenceLimit, setReferenceLimit] = useState(5);
  const [referencedByLimit, setReferencedByLimit] = useState(5);

  useEffect(() => {
    setNoteDraft(entry.note ?? entry.intent_note ?? '');
    setTagDraft('');
    setTagDraftOpen(false);
  }, [entry.document.id]);

  useEffect(() => {
    const nextNote = noteDraft.trim();
    const currentNote = (entry.note ?? entry.intent_note ?? '').trim();
    if (nextNote === currentNote) return;
    const timeout = window.setTimeout(() => {
      setSavingNote(true);
      updateDocumentBookshelf(entry.document.id, { note: noteDraft })
        .then(onEntryChange)
        .finally(() => setSavingNote(false));
    }, 450);
    return () => window.clearTimeout(timeout);
  }, [entry.document.id, entry.note, entry.intent_note, noteDraft, onEntryChange]);

  async function addTag(event: FormEvent) {
    event.preventDefault();
    const tag = tagDraft.trim();
    if (!tag || entry.tags.includes(tag)) {
      setTagDraft('');
      setTagDraftOpen(false);
      return;
    }
    setSavingTags(true);
    try {
      const updated = await updateDocumentBookshelf(entry.document.id, { tags: [...entry.tags, tag] });
      onEntryChange(updated);
      setTagDraft('');
      setTagDraftOpen(false);
    } finally {
      setSavingTags(false);
    }
  }

  return (
    <aside ref={drawerRef} className={closing ? 'bookshelf-detail-drawer drawer-closing' : 'bookshelf-detail-drawer'} aria-label="Bookshelf document details">
      <div className="bookshelf-detail-header">
        <div>
          <span>{document.source_domain}</span>
          <h3>
            {document.title ?? document.url}
            <a href={document.url} target="_blank" rel="noreferrer" aria-label="Open document">
              <ArrowUpRight size={15} />
            </a>
          </h3>
        </div>
        <button type="button" onClick={onClose} aria-label="Close details">×</button>
      </div>

      <div className="bookshelf-detail-actions">
        {containingCollections.map((collection) => (
          <span key={collection.id}>{collection.name}</span>
        ))}
        {entry.favorited && <span>favorite</span>}
      </div>

      {loading && <div className="skeleton-stack" aria-label="Loading document details"><span className="skeleton-line" /><span className="skeleton-line" /><span className="skeleton-line" /></div>}
      {error && <div className="error">{error}</div>}

      <section className="bookshelf-detail-section">
        <h4>Summary</h4>
        <p>{document.summary || 'No summary yet.'}</p>
      </section>

      <section className="bookshelf-detail-section">
        <div className="bookshelf-detail-section-heading">
          <h4>Notes</h4>
          {savingNote && <span>Saving</span>}
        </div>
        <textarea
          className="bookshelf-detail-note-input"
          value={noteDraft}
          onChange={(event) => setNoteDraft(event.target.value)}
          placeholder="Add a note..."
        />
      </section>

      <section className="bookshelf-detail-section">
        <div className="bookshelf-detail-section-heading">
          <h4>Tags</h4>
          <button type="button" className="bookshelf-detail-add-tag" onClick={() => setTagDraftOpen((value) => !value)}>
            Add tag
          </button>
        </div>
        {tagDraftOpen && (
          <form className="bookshelf-detail-tag-form" onSubmit={addTag}>
            <input
              value={tagDraft}
              onChange={(event) => setTagDraft(event.target.value)}
              placeholder="New tag"
              disabled={savingTags}
              autoFocus
            />
          </form>
        )}
        {entry.tags.length > 0 || document.topics.length > 0 ? (
          <div className="bookshelf-detail-tags">
            {[...entry.tags, ...document.topics.filter((topic) => !entry.tags.includes(topic))].map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </div>
        ) : (
          <p>No tags yet.</p>
        )}
      </section>

      <div className="bookshelf-detail-reference-grid">
        <section className="bookshelf-detail-section">
          <h4>References</h4>
          {detail?.outgoing_links.length ? (
            <>
              <div className="bookshelf-detail-link-list">
                {detail.outgoing_links.slice(0, referenceLimit).map((link, index) => (
                  <a key={`${link.target_url}-${index}`} href={link.target_url} target="_blank" rel="noreferrer">
                    <strong>{link.anchor_text || link.target_domain || link.target_url}</strong>
                    <small>{link.target_domain || link.target_url}</small>
                    {link.context && <span>{link.context}</span>}
                  </a>
                ))}
              </div>
              {referenceLimit < detail.outgoing_links.length && (
                <button className="bookshelf-detail-more" type="button" onClick={() => setReferenceLimit((value) => value + 5)}>
                  More references
                </button>
              )}
            </>
          ) : (
            <p>No outgoing references indexed.</p>
          )}
        </section>

        <section className="bookshelf-detail-section">
          <h4>Referenced By</h4>
          {detail?.incoming_links.length ? (
            <>
              <div className="bookshelf-detail-link-list">
                {detail.incoming_links.slice(0, referencedByLimit).map((link, index) => (
                  <button key={`${link.source_document_id}-${index}`} type="button">
                    <strong>{link.anchor_text || link.target_url || 'Referenced document'}</strong>
                    <small>{link.target_url}</small>
                  </button>
                ))}
              </div>
              {referencedByLimit < detail.incoming_links.length && (
                <button className="bookshelf-detail-more" type="button" onClick={() => setReferencedByLimit((value) => value + 5)}>
                  More referenced by
                </button>
              )}
            </>
          ) : (
            <p>No incoming references indexed.</p>
          )}
        </section>
      </div>
    </aside>
  );
}

function entryDate(entry: BookshelfEntry): string {
  const value = entry.read_at ?? entry.first_seen_at ?? entry.favorited_at;
  if (!value) return '';
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function BookshelfTable({
  rows,
  selectedDocumentIds,
  selectionEnabled,
  onRowClick,
  onOpenDetail,
  onToggleFavorite,
  onRemoveFromCurrent,
}: {
  rows: BookshelfEntry[];
  selectedDocumentIds: Set<number>;
  selectionEnabled: boolean;
  onRowClick: (entry: BookshelfEntry, event: MouseEvent<HTMLDivElement>, forceSelect?: boolean) => void;
  onOpenDetail: (entry: BookshelfEntry) => void;
  onToggleFavorite: (entry: BookshelfEntry) => void;
  onRemoveFromCurrent: (documentId: number) => void;
}) {
  const entriesByDocumentId = new Map(rows.map((entry) => [entry.document.id, entry]));
  const tableRows = rows.map((entry) => ({
    document: entry.document,
    tags: entry.tags,
    note: entry.note || entry.intent_note ? notePreview(entry) : undefined,
    date: entryDate(entry),
    favorited: entry.favorited,
    selected: selectedDocumentIds.has(entry.document.id),
  }));

  return (
    <DenseDocumentTable
      rows={tableRows}
      ariaLabel="Bookshelf documents"
      selectionEnabled={selectionEnabled}
      showFavorite
      showActions
      onPrimaryClick={(row, event) => {
        const entry = entriesByDocumentId.get(row.document.id);
        if (entry) onOpenDetail(entry);
      }}
      onModifiedClick={(row, event) => {
        const entry = entriesByDocumentId.get(row.document.id);
        if (entry) onRowClick(entry, event);
      }}
      onDoubleClick={(row, event) => {
        const entry = entriesByDocumentId.get(row.document.id);
        if (entry) onRowClick(entry, event, true);
      }}
      onToggleFavorite={(row) => {
        const entry = entriesByDocumentId.get(row.document.id);
        if (entry) onToggleFavorite(entry);
      }}
      onRemove={(row) => onRemoveFromCurrent(row.document.id)}
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
