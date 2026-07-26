import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export function DataTable({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      role="table"
      className={cn('overflow-auto border border-[var(--border-subtle)] bg-[var(--bg-raised)]', className)}
      {...props}
    />
  );
}

export function DataTableRow({ className, selected = false, ...props }: ComponentProps<'div'> & { selected?: boolean }) {
  return (
    <div
      role="row"
      className={cn(
        'grid items-center border-b border-[var(--border-subtle)] bg-transparent hover:bg-[var(--bg-hover)]',
        selected && 'bg-[var(--bg-hover)]',
        className,
      )}
      {...props}
    />
  );
}

export function DataTableHead({ className, ...props }: ComponentProps<'div'>) {
  return (
    <DataTableRow
      className={cn('text-xs font-semibold uppercase text-[var(--text-muted)] hover:bg-transparent', className)}
      {...props}
    />
  );
}
