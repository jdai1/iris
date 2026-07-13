import { KeyboardEvent, MouseEvent, useRef, useState } from 'react';
import { ArrowUpRight, MoreVertical, Trash2 } from 'lucide-react';
import { OverflowText } from './OverflowText';
import type { Document } from '../types';

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
  noteHeader = 'Notes',
  emptyNoteLabel = '—',
  onPrimaryClick,
  onModifiedClick,
  onDoubleClick,
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
  noteHeader?: string;
  emptyNoteLabel?: string;
  onPrimaryClick: (row: DenseDocumentTableRow, event: MouseEvent<HTMLDivElement> | KeyboardEvent<HTMLDivElement>) => void;
  onModifiedClick?: (row: DenseDocumentTableRow, event: MouseEvent<HTMLDivElement>) => void;
  onDoubleClick?: (row: DenseDocumentTableRow, event: MouseEvent<HTMLDivElement>) => void;
  onToggleFavorite?: (row: DenseDocumentTableRow) => void;
  onRemove?: (row: DenseDocumentTableRow) => void;
}) {
  const [openActionDocumentId, setOpenActionDocumentId] = useState<number | null>(null);
  const clickTimerRef = useRef<number | null>(null);
  const tableClassName = [
    'bookshelf-table',
    showFavorite || (showActions && showNote) ? '' : showActions ? 'bookshelf-table-actions-only' : showNote ? 'bookshelf-table-simple' : 'bookshelf-table-minimal',
    showSource ? '' : 'bookshelf-table-no-source',
  ].filter(Boolean).join(' ');

  function clearClickTimer() {
    if (clickTimerRef.current !== null) {
      window.clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
    }
  }

  return (
    <div className={tableClassName} role="table" aria-label={ariaLabel}>
      <div className="bookshelf-table-row bookshelf-table-head" role="row">
        <span>Title</span>
        <span>Tags</span>
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
            key={document.id}
            className={row.selected ? 'bookshelf-table-row bookshelf-table-row-selected' : 'bookshelf-table-row'}
            role="row"
            tabIndex={0}
            aria-selected={selectionEnabled ? row.selected : undefined}
            onClick={(event) => {
              const target = event.target as HTMLElement;
              if (target.closest('a, button, select')) return;
              if ((event.metaKey || event.ctrlKey || event.shiftKey) && onModifiedClick) {
                onModifiedClick(row, event);
                return;
              }
              clearClickTimer();
              clickTimerRef.current = window.setTimeout(() => {
                onPrimaryClick(row, event);
                clickTimerRef.current = null;
              }, 180);
            }}
            onMouseDown={(event) => {
              if (event.detail > 1) event.preventDefault();
            }}
            onDoubleClick={(event) => {
              event.preventDefault();
              clearClickTimer();
              onDoubleClick?.(row, event);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onPrimaryClick(row, event);
              }
            }}
          >
            <span
              className="bookshelf-table-title tooltip-overflow-cell"
              data-label="Title"
              aria-label={sourceAsTitle ? `${document.title ?? document.url}, ${document.source_domain}` : undefined}
            >
              <strong>
                <OverflowText>{document.title ?? document.url}</OverflowText>
                <a href={document.url} target="_blank" rel="noreferrer" aria-label="Open document" onClick={(event) => event.stopPropagation()}>
                  <ArrowUpRight size={14} />
                </a>
              </strong>
              {showSource && <OverflowText className="tooltip-overflow-text">{document.source_domain}</OverflowText>}
            </span>
            <span className="bookshelf-table-tags tooltip-overflow-cell" data-label="Tags">
              <OverflowText>{row.tags.join(', ') || '-'}</OverflowText>
            </span>
            {showNote && (
              <span className={row.note ? 'bookshelf-note-preview tooltip-overflow-cell' : 'bookshelf-note-empty tooltip-overflow-cell'} data-label={noteHeader}>
                <OverflowText>{row.note || emptyNoteLabel}</OverflowText>
              </span>
            )}
            <span className="bookshelf-table-date" data-label="Date">{row.date ?? ''}</span>
            {showFavorite && (
              <button
                className={row.favorited ? 'bookshelf-fav bookshelf-fav-on' : 'bookshelf-fav'}
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
              <span className="bookshelf-row-actions">
                <button
                  type="button"
                  aria-label="Document actions"
                  aria-expanded={openActionDocumentId === document.id}
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpenActionDocumentId((current) => (current === document.id ? null : document.id));
                  }}
                >
                  <MoreVertical size={14} />
                </button>
                {openActionDocumentId === document.id && (
                  <div className={menuOpensUp ? 'bookshelf-row-menu bookshelf-row-menu-up' : 'bookshelf-row-menu'}>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onRemove?.(row);
                        setOpenActionDocumentId(null);
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
  );
}
