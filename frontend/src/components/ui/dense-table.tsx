import type { ComponentProps } from 'react';
import { cn } from '../../lib/utils';

export const denseTableHeaderClass =
  'grid items-center gap-3 border-b bg-muted/40 px-4 py-2 text-xs font-semibold uppercase text-muted-foreground';

export const denseTableRowClass =
  'grid items-center gap-3 border-b px-4 py-3 text-sm last:border-0';

export function DenseTableViewport({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('overflow-x-auto border-y', className)} {...props} />;
}
