import { FormEvent, MouseEvent, RefObject, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Check, Folder, Loader2, Orbit, Plus, Users } from 'lucide-react';
import { addBookshelfCollectionItem, updateDocumentBookshelf } from '../api';
import { documentPath, navigateTo } from '../app/navigation';
import type { BookshelfCollection, BookshelfEntry, Document, DocumentDetail } from '../types';
import { DocumentBookshelfActions } from './DocumentBookshelfActions';
import { StateMessage } from './ui';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from './ui/dropdown-menu';

export function entryFromDocument(document: Document): BookshelfEntry {
  return {
    document,
    status: document.bookshelf_status ?? 'archived',
    favorited: Boolean(document.bookshelf_favorited),
    note: null,
    intent_note: null,
    tags: [],
    first_seen_at: null,
    read_at: null,
    archived_at: null,
    favorited_at: null,
  };
}

export function DocumentDetailDrawer({
  entry,
  detail,
  collections,
  loading,
  error,
  drawerRef,
  closing,
  className = '',
  ariaLabel = 'Document details',
  presentation = 'drawer',
  reason,
  friendHighlights,
  onEntryChange,
  onCollectionsChange,
  onClose,
}: {
  entry: BookshelfEntry;
  detail: DocumentDetail | null;
  collections: BookshelfCollection[];
  loading: boolean;
  error: string | null;
  drawerRef?: RefObject<HTMLDivElement | null>;
  closing: boolean;
  className?: string;
  ariaLabel?: string;
  presentation?: 'drawer' | 'artifact';
  reason?: string | null;
  friendHighlights?: { username: string; quotes: string[] } | null;
  onEntryChange: (entry: BookshelfEntry) => void;
  onCollectionsChange: (collections: BookshelfCollection[]) => void;
  onClose: () => void;
}) {
  const document = detail ?? entry.document;
  const containingCollections = collections.filter((collection) =>
    collection.items.some((item) => item.document.uuid === entry.document.uuid),
  );
  const [noteDraft, setNoteDraft] = useState(entry.note ?? entry.intent_note ?? '');
  const [tagDraftOpen, setTagDraftOpen] = useState(false);
  const [tagDraft, setTagDraft] = useState('');
  const [savingNote, setSavingNote] = useState(false);
  const [savingTags, setSavingTags] = useState(false);
  const [collectionSavingId, setCollectionSavingId] = useState<number | null>(null);
  const [collectionError, setCollectionError] = useState<string | null>(null);
  const [referenceLimit, setReferenceLimit] = useState(5);
  const [referencedByLimit, setReferencedByLimit] = useState(5);
  const tagFormRef = useRef<HTMLFormElement | null>(null);
  const outgoingDocumentLinks = detail?.outgoing_links.filter((link) => link.target_document_uuid) ?? [];
  const incomingDocumentLinks = detail?.incoming_links ?? [];

  useEffect(() => {
    setNoteDraft(entry.note ?? entry.intent_note ?? '');
    setTagDraft('');
    setTagDraftOpen(false);
    setReferenceLimit(5);
    setReferencedByLimit(5);
  }, [entry.document.uuid]);

  useEffect(() => {
    if (!tagDraftOpen) return;
    function handlePointerDown(event: globalThis.PointerEvent) {
      const target = event.target;
      if (target instanceof Node && tagFormRef.current?.contains(target)) return;
      setTagDraft('');
      setTagDraftOpen(false);
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return;
      setTagDraft('');
      setTagDraftOpen(false);
    }
    window.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [tagDraftOpen]);

  useEffect(() => {
    const nextNote = noteDraft.trim();
    const currentNote = (entry.note ?? entry.intent_note ?? '').trim();
    if (nextNote === currentNote) return;
    const timeout = window.setTimeout(() => {
      setSavingNote(true);
      updateDocumentBookshelf(entry.document.uuid, { note: noteDraft })
        .then(onEntryChange)
        .finally(() => setSavingNote(false));
    }, 450);
    return () => window.clearTimeout(timeout);
  }, [entry.document.uuid, entry.note, entry.intent_note, noteDraft, onEntryChange]);

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
      const updated = await updateDocumentBookshelf(entry.document.uuid, { tags: [...entry.tags, tag] });
      onEntryChange(updated);
      setTagDraft('');
      setTagDraftOpen(false);
    } finally {
      setSavingTags(false);
    }
  }

  async function addToCollection(collectionId: number) {
    if (collectionSavingId !== null) return;
    setCollectionSavingId(collectionId);
    setCollectionError(null);
    try {
      const updated = await addBookshelfCollectionItem(collectionId, document.uuid);
      onCollectionsChange(collections.map((collection) => collection.id === updated.id ? updated : collection));
    } catch {
      setCollectionError('Could not add to collection');
    } finally {
      setCollectionSavingId(null);
    }
  }

  function followInternalLink(event: MouseEvent<HTMLAnchorElement>, path: string) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigateTo(path);
  }

  return (
    <aside
      ref={drawerRef}
      className={`${
        presentation === 'artifact'
          ? `relative h-svh w-full overflow-y-auto border-l bg-background transition-[transform,opacity] duration-200 ease-out motion-reduce:transition-none ${closing ? 'translate-x-6 opacity-0' : 'animate-in slide-in-from-right-6 fade-in-0 opacity-100'}`
          : `fixed inset-y-0 right-0 z-50 w-full max-w-xl overflow-y-auto border-l bg-background shadow-2xl transition-transform duration-200 ease-out motion-reduce:transition-none ${closing ? 'translate-x-full' : 'animate-in slide-in-from-right-full translate-x-0'}`
      } ${className}`}
      aria-label={ariaLabel}
    >
      <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b bg-background/95 px-5 py-4 backdrop-blur">
        <div className="min-w-0">
          <span className="text-xs text-muted-foreground">{document.source_domain}</span>
          <h3 className="mt-1 text-lg font-semibold leading-snug">{document.title ?? document.url}</h3>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <a
            className="grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            href={`/directory/${encodeURIComponent(document.source_domain)}`}
            onClick={(event) => followInternalLink(event, `/directory/${encodeURIComponent(document.source_domain)}`)}
            aria-label="Open source directory"
            title="Open source directory"
          >
            <Users size={15} />
          </a>
          <a
            className="grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            href={`/explore?document=${document.uuid}`}
            onClick={(event) => followInternalLink(event, `/explore?document=${document.uuid}`)}
            aria-label="Explore from this document"
            title="Explore from this document"
          >
            <Orbit size={15} />
          </a>
          <a
            className="grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            href={document.url}
            target="_blank"
            rel="noreferrer"
            aria-label="Open original document"
            title="Open original document"
          >
            <ArrowUpRight size={15} />
          </a>
          <button className="grid size-8 place-items-center rounded-md text-xl text-muted-foreground hover:bg-accent hover:text-foreground" type="button" onClick={onClose} aria-label="Close details" title="Close details">×</button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-b px-5 py-3 text-xs">
        <DocumentBookshelfActions
          documentUuid={document.uuid}
          status={entry.status}
          favorited={entry.favorited}
          labeled
          onChange={onEntryChange}
        />
        <div className="flex min-w-0 items-center gap-1.5 text-muted-foreground">
          <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
          <DropdownMenu onOpenChange={(open) => {
            if (open) setCollectionError(null);
          }}>
            <DropdownMenuTrigger asChild>
              <button
                className="grid size-7 place-items-center rounded-md transition-colors hover:bg-accent hover:text-foreground"
                type="button"
                aria-label="Add to collection"
                title="Add to collection"
              >
                <Folder size={12} />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56" align="start">
              {collections.length === 0 && <DropdownMenuItem disabled>No collections yet</DropdownMenuItem>}
              {collections.map((collection) => {
                const added = collection.items.some((item) => item.document.uuid === document.uuid);
                const saving = collectionSavingId === collection.id;
                return (
                  <DropdownMenuItem
                    key={collection.id}
                    disabled={collectionSavingId !== null || added}
                    onSelect={() => void addToCollection(collection.id)}
                  >
                    <span className="min-w-0 flex-1 truncate">{collection.name}</span>
                    {saving ? <Loader2 className="animate-spin" /> : added ? <Check className="text-primary" /> : null}
                  </DropdownMenuItem>
                );
              })}
              {collectionError && <DropdownMenuItem className="text-destructive" disabled>{collectionError}</DropdownMenuItem>}
            </DropdownMenuContent>
          </DropdownMenu>
          {containingCollections.length > 0 && (
            <>
            <span>In</span>
            {containingCollections.map((collection, index) => (
              <span className="contents" key={collection.id}>
                {index > 0 && <span aria-hidden="true">·</span>}
                <a
                  className="max-w-40 truncate font-medium text-foreground hover:underline"
                  href={`/bookshelf?collection=${collection.id}`}
                  onClick={(event) => followInternalLink(event, `/bookshelf?collection=${collection.id}`)}
                  title={collection.name}
                >
                  {collection.name}
                </a>
              </span>
            ))}
            </>
          )}
        </div>
      </div>

      {loading && <div className="grid gap-2 p-5" aria-label="Loading document details"><span className="h-4 animate-pulse rounded bg-muted" /><span className="h-4 animate-pulse rounded bg-muted" /><span className="h-24 animate-pulse rounded bg-muted" /></div>}
      {error && <StateMessage className="m-5" tone="error">{error}</StateMessage>}

      <section className="border-b px-5 py-5">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Summary</h4>
        <p className="text-sm leading-6">{document.summary || 'No summary yet.'}</p>
      </section>

      {reason && (
        <section className="border-b bg-primary/5 px-5 py-5">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-primary">Why This Result</h4>
          <p className="text-sm leading-6">{reason}</p>
        </section>
      )}

      {friendHighlights && friendHighlights.quotes.length > 0 && (
        <section className="border-b px-5 py-5">
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {friendHighlights.quotes.length} {friendHighlights.quotes.length === 1 ? 'highlight' : 'highlights'} from @{friendHighlights.username}
          </h4>
          <div className="grid gap-3">
            {friendHighlights.quotes.map((quote, index) => (
              <blockquote className="border-l-2 border-primary/30 pl-3 text-sm leading-6 text-muted-foreground" key={`${index}-${quote}`}>
                “{quote}”
              </blockquote>
            ))}
          </div>
        </section>
      )}

      <section className="border-b px-5 py-5">
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Notes</h4>
          {savingNote && <span className="text-xs text-muted-foreground">Saving</span>}
        </div>
        <textarea
          className="min-h-28 w-full resize-y rounded-md border bg-background p-3 text-sm outline-none focus:ring-2 focus:ring-ring/20"
          value={noteDraft}
          onChange={(event) => setNoteDraft(event.target.value)}
          placeholder="Add a note..."
        />
      </section>

      <section className="border-b px-5 py-5">
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Tags</h4>
          {!tagDraftOpen && (
            <button
              className="grid size-7 place-items-center rounded-md hover:bg-accent"
              type="button"
              onClick={() => setTagDraftOpen(true)}
              aria-label="Add tag"
              data-tooltip="Add tag"
            >
              <Plus size={14} />
            </button>
          )}
        </div>
        <div
          className="flex flex-wrap items-center gap-1.5"
        >
          {[...entry.tags, ...document.topics.filter((topic) => !entry.tags.includes(topic))].map((tag) => (
            <span className="rounded-full border bg-muted px-2 py-0.5 text-xs" key={tag}>{tag}</span>
          ))}
          {tagDraftOpen ? (
            <form onSubmit={addTag} ref={tagFormRef}>
              <input
                className="h-7 w-28 rounded-full border bg-background px-2 text-xs outline-none focus:ring-2 focus:ring-ring/20"
                value={tagDraft}
                onChange={(event) => setTagDraft(event.target.value)}
                placeholder="Add tag..."
                disabled={savingTags}
                autoFocus
              />
            </form>
          ) : null}
        </div>
      </section>

      <div className="grid md:grid-cols-2">
        <section className="border-b px-5 py-5 md:border-r">
          <div className="mb-3 flex items-center justify-between">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">References</h4>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{outgoingDocumentLinks.length}</span>
          </div>
          {outgoingDocumentLinks.length ? (
            <>
              <div className="space-y-1">
                {outgoingDocumentLinks.slice(0, referenceLimit).map((link, index) => (
                  <button className="block w-full rounded-md px-2 py-2 text-left text-sm hover:bg-muted" key={`${link.target_url}-${index}`} type="button" onClick={() => navigateTo(documentPath(link.target_document_uuid!))}>
                    <strong className="block truncate font-medium">{link.anchor_text || link.target_domain || link.target_url}</strong>
                    <small className="block truncate text-muted-foreground">{link.target_domain || link.target_url}</small>
                    {link.context && <span className="mt-1 line-clamp-2 block text-xs text-muted-foreground">{link.context}</span>}
                  </button>
                ))}
              </div>
              {referenceLimit < outgoingDocumentLinks.length && (
                <button className="mt-2 text-xs font-medium text-primary hover:underline" type="button" onClick={() => setReferenceLimit((value) => value + 5)}>
                  More references
                </button>
              )}
            </>
          ) : (
            <p className="py-6 text-center text-muted-foreground" title="No outgoing references indexed.">—</p>
          )}
        </section>

        <section className="border-b px-5 py-5">
          <div className="mb-3 flex items-center justify-between">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Referenced By</h4>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{incomingDocumentLinks.length}</span>
          </div>
          {incomingDocumentLinks.length ? (
            <>
              <div className="space-y-1">
                {incomingDocumentLinks.slice(0, referencedByLimit).map((link, index) => (
                  <button className="block w-full rounded-md px-2 py-2 text-left text-sm hover:bg-muted" key={`${link.source_document_uuid}-${index}`} type="button" onClick={() => navigateTo(documentPath(link.source_document_uuid))}>
                    <strong className="block truncate font-medium">{link.anchor_text || 'Referenced document'}</strong>
                    <small className="block truncate text-muted-foreground">{link.target_url}</small>
                  </button>
                ))}
              </div>
              {referencedByLimit < incomingDocumentLinks.length && (
                <button className="mt-2 text-xs font-medium text-primary hover:underline" type="button" onClick={() => setReferencedByLimit((value) => value + 5)}>
                  More referenced by
                </button>
              )}
            </>
          ) : (
            <p className="py-6 text-center text-muted-foreground" title="No incoming references indexed.">—</p>
          )}
        </section>
      </div>
    </aside>
  );
}
