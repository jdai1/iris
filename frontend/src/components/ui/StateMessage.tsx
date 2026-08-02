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
        'rounded-lg border px-4 py-3 text-sm leading-[1.5]',
        tone === 'error'
          ? 'border-destructive/30 bg-destructive/10 text-destructive'
          : 'border-border bg-card text-muted-foreground',
        className,
      )}
      {...props}
    />
  );
}
