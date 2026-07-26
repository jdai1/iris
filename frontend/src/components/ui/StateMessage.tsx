import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export type StateMessageTone = 'neutral' | 'error';

export type StateMessageProps = ComponentProps<'div'> & {
  tone?: StateMessageTone;
};

export function StateMessage({ className, tone = 'neutral', ...props }: StateMessageProps) {
  return (
    <div
      className={cn(
        'border px-4 py-3 text-sm leading-[1.5]',
        tone === 'error'
          ? 'border-[var(--status-red-border)] bg-[var(--status-red-bg)] text-[var(--status-red-text)]'
          : 'border-[var(--border-subtle)] bg-[var(--bg-raised)] text-[var(--text-muted)]',
        className,
      )}
      {...props}
    />
  );
}
