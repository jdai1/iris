import { FormEvent, MouseEvent, RefObject, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, GitFork, Orbit, Plus, Users } from 'lucide-react';
import { updateDocumentBookshelf } from '../api';
import { documentPath, navigateTo } from '../app/navigation';
import type { BookshelfCollection, BookshelfEntry, Document, DocumentDetail } from '../types';
import { StateMessage } from './ui';

export function entryFromDocument(document: Document): BookshelfEntry {
  return {
    document,
    status: document.bookshelf_status ?? 'saved',
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
  reason,
  onEntryChange,
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
  reason?: string | null;
  onEntryChange: (entry: BookshelfEntry) => void;
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

  function followInternalLink(event: MouseEvent<HTMLAnchorElement>, path: string) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigateTo(path);
  }

  return (
    <aside ref={drawerRef} className={`fixed inset-y-0 right-0 z-50 w-full max-w-xl overflow-y-auto border-l bg-background shadow-2xl transition-transform duration-200 ${closing ? 'translate-x-full' : 'translate-x-0'} ${className}`} aria-label={ariaLabel}>
      <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b bg-background/95 px-5 py-4 backdrop-blur">
        <div className="min-w-0">
          <span className="text-xs text-muted-foreground">{document.source_domain}</span>
          <h3 className="mt-1 flex items-start gap-2 text-lg font-semibold leading-snug">
            {document.title ?? document.url}
            <a className="mt-1 shrink-0 text-muted-foreground hover:text-foreground" href={document.url} target="_blank" rel="noreferrer" aria-label="Open document">
              <ArrowUpRight size={15} />
            </a>
          </h3>
        </div>
        <button className="grid size-9 shrink-0 place-items-center rounded-md text-xl text-muted-foreground hover:bg-accent hover:text-foreground" type="button" onClick={onClose} aria-label="Close details">×</button>
      </div>

      <div className="flex flex-wrap gap-2 border-b px-5 py-3 text-xs [&_a]:inline-flex [&_a]:h-7 [&_a]:items-center [&_a]:gap-1.5 [&_a]:rounded-md [&_a]:border [&_a]:px-2 [&_a]:hover:bg-accent [&>span]:inline-flex [&>span]:h-7 [&>span]:items-center [&>span]:rounded-md [&>span]:bg-muted [&>span]:px-2">
        <a href={`/directory/${encodeURIComponent(document.source_domain)}`} onClick={(event) => followInternalLink(event, `/directory/${encodeURIComponent(document.source_domain)}`)}>
          <Users size={12} />
          Directory
        </a>
        <a
          href={`/directory?mode=graph&document=${document.uuid}`}
          onClick={(event) => followInternalLink(event, `/directory?mode=graph&document=${document.uuid}`)}
        >
          <GitFork size={12} />
          Graph
        </a>
        <a
          href={`/directory?mode=explore&document=${document.uuid}`}
          onClick={(event) => followInternalLink(event, `/directory?mode=explore&document=${document.uuid}`)}
        >
          <Orbit size={12} />
          Explore
        </a>
        {containingCollections.map((collection) => (
          <a href={`/bookshelf?collection=${collection.id}`} onClick={(event) => followInternalLink(event, `/bookshelf?collection=${collection.id}`)} key={collection.id}>{collection.name}</a>
        ))}
        {entry.favorited && <span>favorite</span>}
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
