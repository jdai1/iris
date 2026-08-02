import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';
import { Chip } from './Chip';

const statusTone: Record<string, string> = {
  failed: 'border-destructive/30 bg-destructive/10 text-destructive',
  error: 'border-destructive/30 bg-destructive/10 text-destructive',
  complete: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  completed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  running: 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400',
  pending: 'border-border bg-secondary text-muted-foreground',
};

export function StatusBadge({ className, value, ...props }: ComponentProps<'span'> & { value: string }) {
  return (
    <Chip className={cn('lowercase', statusTone[value.toLowerCase()] ?? statusTone.pending, className)} {...props}>
      {value}
    </Chip>
  );
}
