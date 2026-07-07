import { HStack, Text } from '@chakra-ui/react';
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
    <HStack className="pagination" gap="2" color="fg.muted" fontSize="sm">
      <Text as="span">{start}-{end} of {page.total}</Text>
      <select value={page.limit} onChange={(event) => setLimit(event.target.value)}>
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
    </HStack>
  );
}

export function ProfilePagination<T>({ page, onChange }: { page: Page<T>; onChange: (next: PageState) => void }) {
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.items.length, page.total);

  return (
    <HStack className="profile-pagination" gap="2" color="fg.muted" fontSize="sm">
      <Button type="button" uiVariant="plainIcon" disabled={!page.has_previous} onClick={() => onChange({ limit: page.limit, offset: Math.max(0, page.offset - page.limit) })} aria-label="Previous profile documents" data-tooltip="Previous">
        ←
      </Button>
      <Text as="span">{start}-{end} of {page.total}</Text>
      <Button type="button" uiVariant="plainIcon" disabled={!page.has_next} onClick={() => onChange({ limit: page.limit, offset: page.offset + page.limit })} aria-label="Next profile documents" data-tooltip="Next">
        →
      </Button>
    </HStack>
  );
}
