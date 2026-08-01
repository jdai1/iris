import { KeyboardEvent, MouseEvent, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, MoreVertical, Trash2 } from 'lucide-react';
import { OverflowText } from './OverflowText';
import type { Document } from '../types';
import { cn } from '../lib/utils';
import { DenseTableViewport, denseTableHeaderClass, denseTableRowClass } from './ui/dense-table';

export type DenseDocumentTableRow = {
  document: Document;
  tags: string[];
  note?: string;
  date?: string;
  favorited?: boolean;
  selected?: boolean;
};

export function DenseDocumentTable({
  rows,
  ariaLabel,
  selectionEnabled = false,
  showNote = true,
  showFavorite = false,
  showActions = false,
  showSource = true,
  sourceAsTitle = false,
  metadataColumn = 'tags',
  compact = false,
  noteHeader = 'Notes',
  emptyNoteLabel = '—',
  onPrimaryClick,
  onToggleSelection,
  onToggleAll,
  onToggleFavorite,
  onRemove,
}: {
  rows: DenseDocumentTableRow[];
  ariaLabel: string;
  selectionEnabled?: boolean;
  showNote?: boolean;
  showFavorite?: boolean;
  showActions?: boolean;
  showSource?: boolean;
  sourceAsTitle?: boolean;
  metadataColumn?: 'tags' | 'source';
  compact?: boolean;
  noteHeader?: string;
  emptyNoteLabel?: string;
  onPrimaryClick: (row: DenseDocumentTableRow, event: MouseEvent<HTMLDivElement> | KeyboardEvent<HTMLDivElement>) => void;
  onToggleSelection?: (row: DenseDocumentTableRow) => void;
  onToggleAll?: () => void;
  onToggleFavorite?: (row: DenseDocumentTableRow) => void;
  onRemove?: (row: DenseDocumentTableRow) => void;
}) {
  const [openActionDocumentUuid, setOpenActionDocumentUuid] = useState<string | null>(null);
  const allSelected = rows.length > 0 && rows.every((row) => row.selected);
  const someSelected = rows.some((row) => row.selected);
  const selectAllRef = useRef<HTMLInputElement | null>(null);
  const columnClassName = selectionEnabled
    ? showActions
      ? 'grid-cols-[2rem_minmax(14rem,2fr)_minmax(8rem,1fr)_7rem_2.5rem]'
      : showNote && showFavorite
        ? 'grid-cols-[2rem_minmax(14rem,2fr)_minmax(8rem,1fr)_minmax(10rem,1.25fr)_7rem_2.5rem]'
        : showNote
          ? 'grid-cols-[2rem_minmax(14rem,2fr)_minmax(8rem,1fr)_minmax(10rem,1.25fr)_7rem]'
          : 'grid-cols-[2rem_minmax(14rem,2fr)_minmax(8rem,1fr)_7rem]'
    : showNote
      ? 'grid-cols-[minmax(14rem,2fr)_minmax(8rem,1fr)_minmax(10rem,1.25fr)_7rem]'
      : 'grid-cols-[minmax(14rem,2fr)_minmax(8rem,1fr)_7rem]';

  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = someSelected && !allSelected;
  }, [allSelected, someSelected]);

  return (
    <DenseTableViewport>
      <div className="w-full min-w-[760px]" role="table" aria-label={ariaLabel}>
      <div className={cn(denseTableHeaderClass, columnClassName)} role="row">
        {selectionEnabled && (
          <span className="grid place-items-center">
            <input
              ref={selectAllRef}
              type="checkbox"
              checked={allSelected}
              onChange={onToggleAll}
              aria-checked={someSelected && !allSelected ? 'mixed' : allSelected}
              aria-label={allSelected ? 'Deselect all documents' : 'Select all documents'}
            />
          </span>
        )}
        <span>Title</span>
        <span>{metadataColumn === 'source' ? 'Source' : 'Tags'}</span>
        {showNote && <span>{noteHeader}</span>}
        <span>Date</span>
        {showFavorite && <span />}
        {showActions && <span />}
      </div>
      {rows.map((row, index) => {
        const { document } = row;
        const menuOpensUp = rows.length - index <= 2;
        return (
          <div
            key={document.uuid}
            className={cn(
              denseTableRowClass,
              'cursor-pointer hover:bg-muted/50',
              compact && 'py-2',
              columnClassName,
              row.selected && 'bg-accent/60',
            )}
            role="row"
            tabIndex={0}
            aria-selected={selectionEnabled ? row.selected : undefined}
            onClick={(event) => {
              const target = event.target as HTMLElement;
              if (target.closest('a, button, select, input')) return;
              onPrimaryClick(row, event);
            }}
            onKeyDown={(event) => {
              if (event.target !== event.currentTarget) return;
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onPrimaryClick(row, event);
              }
            }}
          >
            {selectionEnabled && (
              <span className="grid place-items-center">
                <input
                  type="checkbox"
                  checked={Boolean(row.selected)}
                  onChange={() => onToggleSelection?.(row)}
                  onClick={(event) => event.stopPropagation()}
                  aria-label={`${row.selected ? 'Deselect' : 'Select'} ${document.title ?? document.url}`}
                />
              </span>
            )}
            <span
              className="min-w-0"
              data-label="Title"
              aria-label={sourceAsTitle ? `${document.title ?? document.url}, ${document.source_domain}` : undefined}
            >
              <strong className="flex min-w-0 items-center gap-1.5 font-medium">
                <OverflowText>{document.title ?? document.url}</OverflowText>
                <a className="shrink-0 text-muted-foreground hover:text-foreground" href={document.url} target="_blank" rel="noreferrer" aria-label="Open document" onClick={(event) => event.stopPropagation()}>
                  <ArrowUpRight size={14} />
                </a>
              </strong>
              {showSource && <OverflowText className="block truncate text-xs text-muted-foreground">{document.source_domain}</OverflowText>}
            </span>
            <span className="min-w-0 text-muted-foreground" data-label={metadataColumn === 'source' ? 'Source' : 'Tags'}>
              <OverflowText>{metadataColumn === 'source' ? document.source_domain : row.tags.join(', ') || '-'}</OverflowText>
            </span>
            {showNote && (
              <span className={`min-w-0 ${row.note ? 'text-foreground' : 'text-muted-foreground'}`} data-label={noteHeader}>
                <OverflowText>{row.note || emptyNoteLabel}</OverflowText>
              </span>
            )}
            <span className="text-xs text-muted-foreground" data-label="Date">{row.date ?? ''}</span>
            {showFavorite && (
              <button
                className={`grid size-8 place-items-center rounded-md text-lg ${row.favorited ? 'text-rose-500' : 'text-muted-foreground hover:bg-accent hover:text-foreground'}`}
                type="button"
                data-label="Favorite"
                aria-label={row.favorited ? 'Remove favorite' : 'Favorite document'}
                aria-pressed={row.favorited}
                onClick={(event) => {
                  event.stopPropagation();
                  onToggleFavorite?.(row);
                }}
              >
                {row.favorited ? '♥' : '♡'}
              </button>
            )}
            {showActions && (
              <span className="relative">
                <button
                  className="grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                  type="button"
                  aria-label="Document actions"
                  aria-expanded={openActionDocumentUuid === document.uuid}
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpenActionDocumentUuid((current) => (current === document.uuid ? null : document.uuid));
                  }}
                >
                  <MoreVertical size={14} />
                </button>
                {openActionDocumentUuid === document.uuid && (
                  <div className={`absolute right-0 z-30 min-w-32 animate-in rounded-lg border bg-popover p-1 shadow-lg fade-in-0 zoom-in-95 duration-100 motion-reduce:animate-none ${menuOpensUp ? 'bottom-9 slide-in-from-bottom-1' : 'top-9 slide-in-from-top-1'}`}>
                    <button
                      className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-destructive hover:bg-destructive/10"
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onRemove?.(row);
                        setOpenActionDocumentUuid(null);
                      }}
                    >
                      <Trash2 size={13} />
                      Remove
                    </button>
                  </div>
                )}
              </span>
            )}
          </div>
        );
      })}
      </div>
    </DenseTableViewport>
  );
}
