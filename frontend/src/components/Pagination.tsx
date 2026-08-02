import type { Page } from '../types';
import { Button } from './ui';

export type PageState = { limit: number; offset: number };

export function Pagination<T>({ page, onChange }: { page: Page<T>; onChange: (next: PageState) => void }) {
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.items.length, page.total);

  function setLimit(value: string) {
    onChange({ limit: Number(value), offset: 0 });
  }

  return (
    <div className="my-3 flex flex-wrap items-center justify-end gap-2 text-xs text-muted-foreground">
      <span className="mr-auto">{start}-{end} of {page.total}</span>
      <select className="h-9 rounded-md border bg-background px-2 text-sm text-foreground" value={page.limit} onChange={(event) => setLimit(event.target.value)}>
        <option value={25}>25 / page</option>
        <option value={50}>50 / page</option>
        <option value={100}>100 / page</option>
        <option value={250}>250 / page</option>
      </select>
      <Button type="button" uiVariant="outline" disabled={!page.has_previous} onClick={() => onChange({ limit: page.limit, offset: Math.max(0, page.offset - page.limit) })}>
        Previous
      </Button>
      <Button type="button" uiVariant="outline" disabled={!page.has_next} onClick={() => onChange({ limit: page.limit, offset: page.offset + page.limit })}>
        Next
      </Button>
    </div>
  );
}

export function ProfilePagination<T>({ page, onChange }: { page: Page<T>; onChange: (next: PageState) => void }) {
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.items.length, page.total);

  return (
    <div className="mt-4 flex items-center justify-end gap-3 text-xs text-muted-foreground">
      <Button type="button" uiVariant="plainIcon" disabled={!page.has_previous} onClick={() => onChange({ limit: page.limit, offset: Math.max(0, page.offset - page.limit) })} aria-label="Previous profile documents" data-tooltip="Previous">
        ←
      </Button>
      <span>{start}-{end} of {page.total}</span>
      <Button type="button" uiVariant="plainIcon" disabled={!page.has_next} onClick={() => onChange({ limit: page.limit, offset: page.offset + page.limit })} aria-label="Next profile documents" data-tooltip="Next">
        →
      </Button>
    </div>
  );
}
