import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { getBookshelf, getBookshelfCollections, getDocument } from '../api';
import { emptyPage } from '../app/paging';
import type { BookshelfCollection, BookshelfEntry, DocumentDetail } from '../types';
import { DocumentDetailDrawer, entryFromDocument } from './DocumentDetailDrawer';

export function DocumentRouteDrawer({ documentUuid, onClose }: { documentUuid: string; onClose: () => void }) {
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

  function closeDrawer() {
    if (closing) return;
    setClosing(true);
    closeTimerRef.current = window.setTimeout(onClose, 190);
  }

  function updateEntry(nextEntry: BookshelfEntry) {
    setEntry(nextEntry);
    setCollections((current) => current.map((collection) => ({
      ...collection,
      items: collection.items.map((item) => (item.document.uuid === nextEntry.document.uuid ? nextEntry : item)),
    })));
  }

  if (!entry) return null;

  return createPortal(
    <>
      <button className={closing ? 'drawer-backdrop drawer-closing' : 'drawer-backdrop'} type="button" aria-label="Close details" onClick={closeDrawer} />
      <DocumentDetailDrawer
        entry={entry}
        detail={detail}
        collections={collections}
        loading={loading}
        error={error}
        closing={closing}
        ariaLabel="Document details"
        onEntryChange={updateEntry}
        onClose={closeDrawer}
      />
    </>,
    document.body,
  );
}
