import type { Page } from '../types';

export type PageState = { limit: number; offset: number };

export function Pagination<T>({ page, onChange }: { page: Page<T>; onChange: (next: PageState) => void }) {
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.items.length, page.total);

  function setLimit(value: string) {
    onChange({ limit: Number(value), offset: 0 });
  }

  return (
    <div className="pagination">
      <span>{start}-{end} of {page.total}</span>
      <select value={page.limit} onChange={(event) => setLimit(event.target.value)}>
        <option value={25}>25 / page</option>
        <option value={50}>50 / page</option>
        <option value={100}>100 / page</option>
        <option value={250}>250 / page</option>
      </select>
      <button type="button" disabled={!page.has_previous} onClick={() => onChange({ limit: page.limit, offset: Math.max(0, page.offset - page.limit) })}>
        Previous
      </button>
      <button type="button" disabled={!page.has_next} onClick={() => onChange({ limit: page.limit, offset: page.offset + page.limit })}>
        Next
      </button>
    </div>
  );
}

export function ProfilePagination<T>({ page, onChange }: { page: Page<T>; onChange: (next: PageState) => void }) {
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.items.length, page.total);

  return (
    <div className="profile-pagination">
      <button type="button" disabled={!page.has_previous} onClick={() => onChange({ limit: page.limit, offset: Math.max(0, page.offset - page.limit) })} aria-label="Previous profile documents" data-tooltip="Previous">
        ←
      </button>
      <span>{start}-{end} of {page.total}</span>
      <button type="button" disabled={!page.has_next} onClick={() => onChange({ limit: page.limit, offset: page.offset + page.limit })} aria-label="Next profile documents" data-tooltip="Next">
        →
      </button>
    </div>
  );
}
