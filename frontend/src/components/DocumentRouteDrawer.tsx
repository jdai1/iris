import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { getBookshelf, getBookshelfCollections, getDocument } from '../api';
import { emptyPage } from '../app/paging';
import type { BookshelfCollection, BookshelfEntry, DocumentDetail } from '../types';
import { DocumentDetailDrawer, entryFromDocument } from './DocumentDetailDrawer';

type DocumentRouteDetailProps = {
  documentUuid: string;
  reason?: string | null;
  friendHighlights?: { username: string; quotes: string[] } | null;
  onClose: () => void;
  className?: string;
};

export function DocumentRouteDrawer(props: DocumentRouteDetailProps) {
  return <DocumentRouteDetail {...props} presentation="drawer" />;
}

export function DocumentRouteArtifact(props: DocumentRouteDetailProps) {
  return <DocumentRouteDetail {...props} presentation="artifact" />;
}

function DocumentRouteDetail({
  documentUuid,
  reason,
  friendHighlights,
  onClose,
  className = '',
  presentation,
}: DocumentRouteDetailProps & { presentation: 'drawer' | 'artifact' }) {
  const [entry, setEntry] = useState<BookshelfEntry | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [collections, setCollections] = useState<BookshelfCollection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);
  const closeTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setEntry(null);
    setDetail(null);
    setCollections([]);
    setLoading(true);
    setError(null);
    setClosing(false);
    Promise.all([
      getDocument(documentUuid),
      getBookshelf({ limit: 500 }).catch(() => emptyPage<BookshelfEntry>()),
      getBookshelfCollections().catch(() => []),
    ])
      .then(([document, bookshelfPage, nextCollections]) => {
        if (cancelled) return;
        const storedEntry = bookshelfPage.items.find((item) => item.document.uuid === document.uuid)
          ?? nextCollections.flatMap((collection) => collection.items).find((item) => item.document.uuid === document.uuid);
        setDetail(document);
        setEntry(storedEntry ?? entryFromDocument(document));
        setCollections(nextCollections);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load document');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [documentUuid]);

  function closeDetail() {
    if (closing) return;
    setClosing(true);
    closeTimerRef.current = window.setTimeout(onClose, 210);
  }

  function updateEntry(nextEntry: BookshelfEntry) {
    setEntry(nextEntry);
    setCollections((current) => current.map((collection) => ({
      ...collection,
      items: collection.items.map((item) => (item.document.uuid === nextEntry.document.uuid ? nextEntry : item)),
    })));
  }

  if (!entry) {
    if (presentation === 'drawer') return null;
    return (
      <aside className={`relative h-svh w-full overflow-y-auto border-l bg-background transition-[transform,opacity] duration-200 ease-out motion-reduce:transition-none ${closing ? 'translate-x-6 opacity-0' : 'animate-in slide-in-from-right-6 fade-in-0'} ${className}`} aria-label="Document artifact">
        <div className="sticky top-0 z-10 flex h-16 items-center justify-between border-b bg-background/95 px-5 backdrop-blur">
          <span className="text-sm font-medium">Document</span>
          <button className="grid size-9 place-items-center rounded-md text-xl text-muted-foreground hover:bg-accent hover:text-foreground" type="button" onClick={closeDetail} aria-label="Close document">×</button>
        </div>
        {error ? (
          <div className="m-5 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
        ) : (
          <div className="grid gap-3 p-5" aria-label="Loading document">
            <span className="h-3 w-1/3 animate-pulse rounded bg-muted" />
            <span className="h-6 w-4/5 animate-pulse rounded bg-muted" />
            <span className="mt-4 h-3 w-full animate-pulse rounded bg-muted" />
            <span className="h-3 w-5/6 animate-pulse rounded bg-muted" />
            <span className="h-24 w-full animate-pulse rounded bg-muted" />
          </div>
        )}
      </aside>
    );
  }

  const detailPanel = (
    <DocumentDetailDrawer
      entry={entry}
      detail={detail}
      collections={collections}
      loading={loading}
      error={error}
      closing={closing}
      className={className}
      presentation={presentation}
      ariaLabel={presentation === 'artifact' ? 'Document artifact' : 'Document details'}
      reason={reason}
      friendHighlights={friendHighlights}
      onEntryChange={updateEntry}
      onCollectionsChange={setCollections}
      onClose={closeDetail}
    />
  );

  if (presentation === 'artifact') return detailPanel;

  return createPortal(
    <>
      <button className={`fixed inset-0 z-40 bg-black/35 backdrop-blur-[1px] transition-opacity duration-200 motion-reduce:transition-none ${closing ? 'opacity-0' : 'animate-in fade-in-0 opacity-100'} ${className}`} type="button" aria-label="Close details" onClick={closeDetail} />
      {detailPanel}
    </>,
    document.body,
  );
}
