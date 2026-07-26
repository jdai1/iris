import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';
import { Chip } from './Chip';

const statusTone: Record<string, string> = {
  failed: 'border-[var(--status-red-border)] bg-[var(--status-red-bg)] text-[var(--status-red-text)]',
  error: 'border-[var(--status-red-border)] bg-[var(--status-red-bg)] text-[var(--status-red-text)]',
  complete: 'border-[var(--status-green-border)] bg-[var(--status-green-bg)] text-[var(--status-green-text)]',
  completed: 'border-[var(--status-green-border)] bg-[var(--status-green-bg)] text-[var(--status-green-text)]',
  success: 'border-[var(--status-green-border)] bg-[var(--status-green-bg)] text-[var(--status-green-text)]',
  running: 'border-[var(--status-blue-border)] bg-[var(--status-blue-bg)] text-[var(--status-blue-text)]',
  pending: 'border-[var(--border-input)] bg-[var(--bg-sunken)] text-[var(--text-muted)]',
};

export function StatusBadge({ className, value, ...props }: ComponentProps<'span'> & { value: string }) {
  return (
    <Chip className={cn('lowercase', statusTone[value.toLowerCase()] ?? statusTone.pending, className)} {...props}>
      {value}
    </Chip>
  );
}
