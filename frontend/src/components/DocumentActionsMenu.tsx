import { useEffect, useState } from 'react';
import { Bookmark, Check, FolderPlus, Loader2, MoreHorizontal } from 'lucide-react';
import { addBookshelfCollectionItem, getBookshelfCollections, updateDocumentBookshelf } from '../api';
import { cn } from '../lib/utils';
import type { BookshelfCollection, BookshelfEntry, BookshelfStatus } from '../types';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';

export function DocumentActionsMenu({
  documentUuid,
  status,
  revealOnHover = false,
  onBookshelfChange,
}: {
  documentUuid: string;
  status: BookshelfStatus | null | undefined;
  revealOnHover?: boolean;
  onBookshelfChange?: (entry: BookshelfEntry) => void;
}) {
  const [currentStatus, setCurrentStatus] = useState<BookshelfStatus | null>(status ?? null);
  const [collections, setCollections] = useState<BookshelfCollection[]>([]);
  const [collectionsLoaded, setCollectionsLoaded] = useState(false);
  const [collectionsLoading, setCollectionsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setCurrentStatus(status ?? null), [status]);

  async function loadCollections() {
    if (collectionsLoaded || collectionsLoading) return;
    setCollectionsLoading(true);
    try {
      setCollections(await getBookshelfCollections());
      setCollectionsLoaded(true);
    } catch {
      setError('Could not load collections');
    } finally {
      setCollectionsLoading(false);
    }
  }

  async function toggleReadLater() {
    if (busy) return;
    const previousStatus = currentStatus;
    const nextStatus: BookshelfStatus = currentStatus === 'saved' ? 'archived' : 'saved';
    setCurrentStatus(nextStatus);
    setBusy(true);
    setError(null);
    try {
      const entry = await updateDocumentBookshelf(documentUuid, { status: nextStatus });
      setCurrentStatus(entry.status);
      onBookshelfChange?.(entry);
    } catch {
      setCurrentStatus(previousStatus);
      setError('Could not update Read Later');
    } finally {
      setBusy(false);
    }
  }

  async function addToCollection(collectionId: number) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await addBookshelfCollectionItem(collectionId, documentUuid);
      setCollections((current) => current.map((collection) => collection.id === updated.id ? updated : collection));
      const entry = updated.items.find((item) => item.document.uuid === documentUuid);
      if (entry) {
        setCurrentStatus(entry.status);
        onBookshelfChange?.(entry);
      }
    } catch {
      setError('Could not add to collection');
    } finally {
      setBusy(false);
    }
  }

  const saved = currentStatus === 'saved';

  return (
    <DropdownMenu onOpenChange={(open) => {
      if (open) void loadCollections();
    }}>
      <DropdownMenuTrigger asChild>
        <button
          className={cn(
            'grid size-7 place-items-center rounded-md text-muted-foreground transition-[color,background-color,opacity] hover:bg-accent hover:text-foreground',
            revealOnHover && 'sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100 sm:data-[state=open]:opacity-100',
          )}
          type="button"
          aria-label="Document actions"
          onClick={(event) => event.stopPropagation()}
        >
          <MoreHorizontal size={14} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-52" align="end">
        <DropdownMenuItem disabled={busy} onSelect={() => void toggleReadLater()}>
          {busy ? <Loader2 className="animate-spin" /> : <Bookmark className={saved ? 'fill-current text-primary' : undefined} />}
          {saved ? 'Remove from Read Later' : 'Add to Read Later'}
        </DropdownMenuItem>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger onFocus={() => void loadCollections()} onPointerMove={() => void loadCollections()}>
            <FolderPlus />
            Add to collection
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="min-w-48">
            {collectionsLoading && <DropdownMenuItem disabled><Loader2 className="animate-spin" />Loading</DropdownMenuItem>}
            {!collectionsLoading && collections.length === 0 && <DropdownMenuItem disabled>No collections yet</DropdownMenuItem>}
            {!collectionsLoading && collections.map((collection) => {
              const added = collection.items.some((item) => item.document.uuid === documentUuid);
              return (
                <DropdownMenuItem key={collection.id} disabled={busy || added} onSelect={() => void addToCollection(collection.id)}>
                  <span className="min-w-0 flex-1 truncate">{collection.name}</span>
                  {added && <Check className="text-primary" />}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        {error && <DropdownMenuItem className="text-destructive" disabled>{error}</DropdownMenuItem>}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
