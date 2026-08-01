import { FormEvent, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { cn } from '../lib/utils';
import { Button } from './ui';
import { Badge } from './ui/badge';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from './ui/dropdown-menu';

export type FilterKind = 'text' | 'tag';
export type FilterValue = { id: string; kind: FilterKind; value: string };
type FilterContext = 'sources' | 'documents' | 'bookshelf';

export function FilterBar({
  context,
  filters,
  onChange,
  className,
}: {
  context: FilterContext;
  filters: FilterValue[];
  onChange: (filters: FilterValue[]) => void;
  className?: string;
}) {
  const [draftKind, setDraftKind] = useState<FilterKind | null>(null);
  const [draftValue, setDraftValue] = useState('');

  function beginFilter(kind: FilterKind) {
    setDraftKind(kind);
    setDraftValue('');
  }

  function cancelDraft() {
    setDraftKind(null);
    setDraftValue('');
  }

  function commitFilter(event: FormEvent) {
    event.preventDefault();
    if (!draftKind) return;
    const value = draftValue.trim().replace(/^#/, '');
    if (!value) {
      cancelDraft();
      return;
    }
    const duplicate = filters.some((filter) => filter.kind === draftKind && filter.value.toLowerCase() === value.toLowerCase());
    if (!duplicate) {
      onChange([...filters, { id: `${draftKind}:${value.toLowerCase()}:${Date.now()}`, kind: draftKind, value }]);
    }
    cancelDraft();
  }

  const labels = filterLabels(context);

  return (
    <div className={cn('flex min-h-7 flex-wrap items-center gap-2', className)} aria-label={`${context} filters`}>
      {filters.map((filter, index) => (
        <div className="contents" key={filter.id}>
          {index > 0 && <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">and</span>}
          <Badge variant="outline" className="h-7 gap-1.5 bg-background px-2 font-normal">
            <span className="text-muted-foreground">{filter.kind === 'text' ? labels.text : 'Tag'}</span>
            <span className="max-w-52 truncate">{filter.value}</span>
            <button
              className="-mr-1 grid size-5 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
              type="button"
              onClick={() => onChange(filters.filter((item) => item.id !== filter.id))}
              aria-label={`Remove ${filter.kind} filter ${filter.value}`}
            >
              <X size={11} />
            </button>
          </Badge>
        </div>
      ))}

      {draftKind && (
        <form className="flex h-7 items-center gap-1.5 rounded-md border bg-background px-2" onSubmit={commitFilter}>
          <span className="text-xs text-muted-foreground">{draftKind === 'text' ? labels.text : 'Tag'}</span>
          <input
            className="w-44 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            value={draftValue}
            onChange={(event) => setDraftValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') cancelDraft();
            }}
            placeholder={draftKind === 'text' ? 'contains…' : 'tag name…'}
            autoFocus
          />
          <button className="grid size-5 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground" type="button" onClick={cancelDraft} aria-label="Cancel filter">
            <X size={11} />
          </button>
        </form>
      )}

      {!draftKind && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button uiVariant="outline" size="sm" type="button" className="h-7 bg-background">
              <Plus size={13} />
              Add filter
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <DropdownMenuItem onSelect={() => beginFilter('text')}>{labels.textMenu}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => beginFilter('tag')}>{labels.tagMenu}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      {filters.length > 0 && (
        <Button className="ml-auto h-7 text-xs" uiVariant="ghost" size="sm" type="button" onClick={() => onChange([])}>
          Clear all
        </Button>
      )}
    </div>
  );
}

function filterLabels(context: FilterContext) {
  if (context === 'sources') {
    return { text: 'Source/about', textMenu: 'Source or about contains', tagMenu: 'Source has document tag' };
  }
  if (context === 'bookshelf') {
    return { text: 'Text', textMenu: 'Title, source, or note contains', tagMenu: 'Document tag is' };
  }
  return { text: 'Text', textMenu: 'Document text contains', tagMenu: 'Document tag is' };
}
