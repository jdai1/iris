import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export function DataTable({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      role="table"
      className={cn('overflow-auto rounded-lg border bg-card text-card-foreground', className)}
      {...props}
    />
  );
}

export function DataTableRow({ className, selected = false, ...props }: ComponentProps<'div'> & { selected?: boolean }) {
  return (
    <div
      role="row"
      className={cn(
        'grid items-center border-b bg-transparent transition-colors last:border-b-0 hover:bg-muted/60',
        selected && 'bg-muted',
        className,
      )}
      {...props}
    />
  );
}

export function DataTableHead({ className, ...props }: ComponentProps<'div'>) {
  return (
    <DataTableRow
      className={cn('bg-muted/40 text-xs font-semibold uppercase text-muted-foreground hover:bg-muted/40', className)}
      {...props}
    />
  );
}
