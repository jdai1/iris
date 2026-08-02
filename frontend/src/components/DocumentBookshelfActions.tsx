import { useEffect, useState } from 'react';
import { Bookmark, Star } from 'lucide-react';
import { updateDocumentBookshelf } from '../api';
import { cn } from '../lib/utils';
import type { BookshelfEntry, BookshelfStatus } from '../types';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './ui/tooltip';

export function DocumentBookshelfActions({
  documentUuid,
  status,
  favorited,
  labeled = false,
  showFavorite = true,
  revealReadLaterOnHover = false,
  onChange,
}: {
  documentUuid: string;
  status: BookshelfStatus | null | undefined;
  favorited: boolean | null | undefined;
  labeled?: boolean;
  showFavorite?: boolean;
  revealReadLaterOnHover?: boolean;
  onChange: (entry: BookshelfEntry) => void;
}) {
  const [currentStatus, setCurrentStatus] = useState(status ?? null);
  const [currentFavorited, setCurrentFavorited] = useState(Boolean(favorited));
  const [saving, setSaving] = useState<'status' | 'favorite' | null>(null);

  useEffect(() => setCurrentStatus(status ?? null), [status]);
  useEffect(() => setCurrentFavorited(Boolean(favorited)), [favorited]);

  const readLater = currentStatus === 'saved';

  async function toggleReadLater() {
    if (saving) return;
    const previousStatus = currentStatus;
    const nextStatus: BookshelfStatus = readLater ? 'archived' : 'saved';
    setCurrentStatus(nextStatus);
    setSaving('status');
    try {
      const entry = await updateDocumentBookshelf(documentUuid, { status: nextStatus });
      setCurrentStatus(entry.status);
      setCurrentFavorited(entry.favorited);
      onChange(entry);
    } catch {
      setCurrentStatus(previousStatus);
    } finally {
      setSaving(null);
    }
  }

  async function toggleFavorite() {
    if (saving) return;
    const previousFavorited = currentFavorited;
    const nextFavorited = !currentFavorited;
    setCurrentFavorited(nextFavorited);
    setSaving('favorite');
    try {
      const entry = await updateDocumentBookshelf(documentUuid, { favorited: nextFavorited });
      setCurrentStatus(entry.status);
      setCurrentFavorited(entry.favorited);
      onChange(entry);
    } catch {
      setCurrentFavorited(previousFavorited);
    } finally {
      setSaving(null);
    }
  }

  return (
    <TooltipProvider delayDuration={250}>
      <div className="flex items-center gap-1.5" aria-label="Bookshelf actions">
      <Tooltip>
        <TooltipTrigger asChild>
          <button
        className={cn(
          'inline-flex h-7 items-center justify-center gap-1.5 rounded-md border px-2 text-xs transition-[color,background-color,border-color,opacity]',
          !labeled && 'w-7 px-0',
          revealReadLaterOnHover && !readLater && 'sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100',
          readLater
            ? 'border-primary/30 bg-primary/10 text-primary hover:bg-primary/15'
            : 'text-muted-foreground hover:bg-accent hover:text-foreground',
        )}
        type="button"
        aria-label={readLater ? 'Remove from Read Later' : 'Add to Read Later'}
        aria-pressed={readLater}
        disabled={saving !== null}
        onClick={(event) => {
          event.stopPropagation();
          void toggleReadLater();
        }}
      >
        <Bookmark className={readLater ? 'fill-current' : undefined} size={12} />
        {labeled && (readLater ? 'Read Later' : 'Read Later')}
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" sideOffset={6}>
          {readLater ? 'Remove from Read Later' : 'Add to Read Later'}
        </TooltipContent>
      </Tooltip>
      {showFavorite && <Tooltip>
        <TooltipTrigger asChild>
          <button
        className={cn(
          'inline-flex h-7 items-center justify-center gap-1.5 rounded-md border px-2 text-xs transition-colors',
          !labeled && 'w-7 px-0',
          currentFavorited
            ? 'border-primary/30 bg-primary/10 text-primary hover:bg-primary/15'
            : 'text-muted-foreground hover:bg-accent hover:text-foreground',
        )}
        type="button"
        aria-label={currentFavorited ? 'Remove from Favorites' : 'Add to Favorites'}
        aria-pressed={currentFavorited}
        disabled={saving !== null}
        onClick={(event) => {
          event.stopPropagation();
          void toggleFavorite();
        }}
      >
        <Star className={currentFavorited ? 'fill-current' : undefined} size={12} />
        {labeled && 'Favorite'}
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" sideOffset={6}>
          {currentFavorited ? 'Remove from Favorites' : 'Add to Favorites'}
        </TooltipContent>
      </Tooltip>}
      </div>
    </TooltipProvider>
  );
}
