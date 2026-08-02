import { type MouseEvent, useEffect, useState } from 'react';
import { ArrowUpRight, ChevronRight, MoreHorizontal } from 'lucide-react';
import { addBookshelfCollectionItem, getBookshelfCollections, updateDocumentBookshelf } from '../api';
import { documentPath, navigateTo } from '../app/navigation';
import type { BookshelfCollection, Document } from '../types';
import { Button, Chip, ChipList, IconButton, Panel, PopoverMenu } from './ui';

type DocumentCardProps = {
  document: Document;
  reason: string;
  onOpenProfile?: (sourceId: number, domain: string) => void;
  compact?: boolean;
};

export function DocumentCard({
  document,
  reason,
  onOpenProfile,
  compact = false,
}: DocumentCardProps) {
  const [collections, setCollections] = useState<BookshelfCollection[]>([]);
  const [collectionsLoaded, setCollectionsLoaded] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(document.bookshelf_status === 'saved');
  const [favorited, setFavorited] = useState(Boolean(document.bookshelf_favorited));
  const [addedCollectionIds, setAddedCollectionIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSaved(document.bookshelf_status === 'saved');
    setFavorited(Boolean(document.bookshelf_favorited));
  }, [document.uuid, document.bookshelf_status, document.bookshelf_favorited]);

  async function loadCollections() {
    if (collectionsLoaded) return;
    try {
      setCollections(await getBookshelfCollections());
      setCollectionsLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load collections');
    }
  }

  async function saveToReadNext() {
    setSaving(true);
    setError(null);
    try {
      await updateDocumentBookshelf(document.uuid, { status: 'saved' });
      setSaved(true);
      setActionsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save');
    } finally {
      setSaving(false);
    }
  }

  async function toggleFavorite() {
    setSaving(true);
    setError(null);
    try {
      const nextFavorited = !favorited;
      await updateDocumentBookshelf(document.uuid, { favorited: nextFavorited });
      setFavorited(nextFavorited);
      setActionsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update favorite');
    } finally {
      setSaving(false);
    }
  }

  async function addToCollection(collectionId: number) {
    setSaving(true);
    setError(null);
    try {
      await addBookshelfCollectionItem(collectionId, document.uuid);
      setAddedCollectionIds((current) => new Set(current).add(collectionId));
      setSaved(true);
      setActionsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add');
    } finally {
      setSaving(false);
    }
  }

  function openDocument(event: MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigateTo(documentPath(document.uuid));
  }

  const actionsMenu = (
    <div className="relative">
      <IconButton
        className="size-8 rounded-md hover:bg-accent"
        type="button"
        uiVariant="plainIcon"
        onClick={() => {
          const nextOpen = !actionsOpen;
          setActionsOpen(nextOpen);
          if (nextOpen) loadCollections();
        }}
        aria-label="Document actions"
        aria-expanded={actionsOpen}
        data-tooltip="Actions"
      >
        <MoreHorizontal size={17} />
      </IconButton>
      {actionsOpen && (
        <PopoverMenu className="absolute right-0 top-9 min-w-48">
          <Button uiVariant="rowAction" type="button" onClick={saveToReadNext} disabled={saving}>
            {saved ? 'In read next' : 'Read next'}
          </Button>
          <Button uiVariant="rowAction" type="button" onClick={toggleFavorite} disabled={saving}>
            {favorited ? 'Favorited' : 'Favorite'}
          </Button>
          <div className="group relative" onMouseEnter={loadCollections} onFocus={loadCollections}>
            <Button uiVariant="rowAction" type="button" disabled={saving}>
              <span>Add to collection</span>
              <ChevronRight size={14} />
            </Button>
            <div className="absolute right-full top-0 hidden min-w-44 rounded-lg border bg-popover p-1 shadow-lg group-hover:grid group-focus-within:grid">
              {collections.length === 0 && <span className="px-2 py-1.5 text-xs text-muted-foreground">No collections yet</span>}
              {collections.map((collection) => {
                const added = addedCollectionIds.has(collection.id);
                return (
                  <Button key={collection.id} uiVariant="rowAction" type="button" onClick={() => addToCollection(collection.id)} disabled={saving || added}>
                    {added ? 'Added' : collection.name}
                  </Button>
                );
              })}
            </div>
          </div>
        </PopoverMenu>
      )}
    </div>
  );

  return (
    <Panel as="article" className={compact ? 'p-4' : 'p-5'}>
      {!compact && (
        <div className="flex flex-wrap items-center gap-2 text-xs uppercase text-muted-foreground">
          <button className="hover:text-primary" type="button" onClick={() => onOpenProfile?.(document.source_id, document.source_domain)}>
            {document.source_domain}
          </button>
          <span>{document.document_type}</span>
        </div>
      )}
      <div className={compact ? 'flex items-start justify-between gap-3' : undefined}>
        <h3 className="mb-3 mt-2 text-xl font-semibold leading-tight">
          <a className="hover:text-primary" href={documentPath(document.uuid)} onClick={openDocument}>
            {document.title ?? document.url}
          </a>
          {compact && (
            <a href={document.url} target="_blank" rel="noreferrer" className="ml-2 inline-flex font-semibold text-foreground" aria-label="Open document" title="Open document">
              <ArrowUpRight size={16} />
            </a>
          )}
        </h3>
        {compact && actionsMenu}
      </div>
      {compact && (
        <button className="mb-2 text-xs text-muted-foreground hover:text-primary" type="button" onClick={() => onOpenProfile?.(document.source_id, document.source_domain)}>
          {document.source_domain}
        </button>
      )}
      {document.summary && <p className="mb-3 leading-relaxed text-foreground">{document.summary}</p>}
      {!compact && <p className="mb-4 text-sm leading-relaxed text-muted-foreground">{reason}</p>}
      <ChipList className="topics mb-4">
        {document.topics.map((topic) => (
          <Chip key={topic}>
            {topic}
          </Chip>
        ))}
      </ChipList>
      {!compact && (
        <div>
          <a href={document.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-foreground hover:text-primary">
            <ArrowUpRight size={16} />
            Open
          </a>
        </div>
      )}
      {(!compact || error) && (
        <div className="mt-3 flex items-center justify-between gap-3">
          {!compact && actionsMenu}
          {error && <small>{error}</small>}
        </div>
      )}
    </Panel>
  );
}
