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
    <aside ref={drawerRef} className={closing ? `bookshelf-detail-drawer ${className} drawer-closing` : `bookshelf-detail-drawer ${className}`} aria-label={ariaLabel}>
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
        <a href={`/directory/${encodeURIComponent(document.source_domain)}`} onClick={(event) => followInternalLink(event, `/directory/${encodeURIComponent(document.source_domain)}`)}>
          <Users size={12} />
          Directory
        </a>
        <a href={`/graph?document=${document.uuid}`} onClick={(event) => followInternalLink(event, `/graph?document=${document.uuid}`)}>
          <GitFork size={12} />
          Graph
        </a>
        <a href={`/explore?document=${document.uuid}`} onClick={(event) => followInternalLink(event, `/explore?document=${document.uuid}`)}>
          <Orbit size={12} />
          Explore
        </a>
        {containingCollections.map((collection) => (
          <a href={`/bookshelf?collection=${collection.id}`} onClick={(event) => followInternalLink(event, `/bookshelf?collection=${collection.id}`)} key={collection.id}>{collection.name}</a>
        ))}
        {entry.favorited && <span>favorite</span>}
      </div>

      {loading && <div className="skeleton-stack" aria-label="Loading document details"><span className="skeleton-line" /><span className="skeleton-line" /><span className="skeleton-line" /></div>}
      {error && <StateMessage className="error" tone="error">{error}</StateMessage>}

      <section className="bookshelf-detail-section">
        <h4>Summary</h4>
        <p>{document.summary || 'No summary yet.'}</p>
      </section>

      {reason && (
        <section className="bookshelf-detail-section search-result-match">
          <h4>Why This Result</h4>
          <p>{reason}</p>
        </section>
      )}

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
          {!tagDraftOpen && (
            <button
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
          className={tagDraftOpen ? 'bookshelf-detail-tags bookshelf-detail-tags-editing' : 'bookshelf-detail-tags'}
        >
          {[...entry.tags, ...document.topics.filter((topic) => !entry.tags.includes(topic))].map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
          {tagDraftOpen ? (
            <form className="bookshelf-detail-tag-form" onSubmit={addTag} ref={tagFormRef}>
              <input
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

      <div className="bookshelf-detail-reference-grid">
        <section className="bookshelf-detail-section">
          <div className="bookshelf-detail-section-heading bookshelf-detail-reference-heading">
            <h4>References</h4>
            <span>{outgoingDocumentLinks.length}</span>
          </div>
          {outgoingDocumentLinks.length ? (
            <>
              <div className="bookshelf-detail-link-list">
                {outgoingDocumentLinks.slice(0, referenceLimit).map((link, index) => (
                  <button key={`${link.target_url}-${index}`} type="button" onClick={() => navigateTo(documentPath(link.target_document_uuid!))}>
                    <strong>{link.anchor_text || link.target_domain || link.target_url}</strong>
                    <small>{link.target_domain || link.target_url}</small>
                    {link.context && <span>{link.context}</span>}
                  </button>
                ))}
              </div>
              {referenceLimit < outgoingDocumentLinks.length && (
                <button className="bookshelf-detail-more" type="button" onClick={() => setReferenceLimit((value) => value + 5)}>
                  More references
                </button>
              )}
            </>
          ) : (
            <p className="empty-reference-note" data-tooltip="No outgoing references indexed.">—</p>
          )}
        </section>

        <section className="bookshelf-detail-section">
          <div className="bookshelf-detail-section-heading bookshelf-detail-reference-heading">
            <h4>Referenced By</h4>
            <span>{incomingDocumentLinks.length}</span>
          </div>
          {incomingDocumentLinks.length ? (
            <>
              <div className="bookshelf-detail-link-list">
                {incomingDocumentLinks.slice(0, referencedByLimit).map((link, index) => (
                  <button key={`${link.source_document_uuid}-${index}`} type="button" onClick={() => navigateTo(documentPath(link.source_document_uuid))}>
                    <strong>{link.anchor_text || 'Referenced document'}</strong>
                    <small>{link.target_url}</small>
                  </button>
                ))}
              </div>
              {referencedByLimit < incomingDocumentLinks.length && (
                <button className="bookshelf-detail-more" type="button" onClick={() => setReferencedByLimit((value) => value + 5)}>
                  More referenced by
                </button>
              )}
            </>
          ) : (
            <p className="empty-reference-note" data-tooltip="No incoming references indexed.">—</p>
          )}
        </section>
      </div>
    </aside>
  );
}
