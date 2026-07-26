import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export function Chip({ className, ...props }: ComponentProps<'span'>) {
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded-full border border-border bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground',
        className,
      )}
      {...props}
    />
  );
}

export function ChipList({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      className={cn('chip-list-scroll flex max-w-full flex-nowrap items-center gap-1.5 overflow-x-auto', className)}
      {...props}
    />
  );
}
