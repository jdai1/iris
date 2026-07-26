import type { ComponentProps, ElementType } from 'react';
import { cn } from '@/lib/utils';

export type PanelProps = ComponentProps<'div'> & {
  as?: ElementType;
  interactive?: boolean;
};

export function Panel({ as: Component = 'div', className, interactive = false, ...props }: PanelProps) {
  return (
    <Component
      className={cn(
        'border border-[var(--border-subtle)] bg-[var(--bg-raised)]',
        interactive && 'shadow-[var(--shadow-panel)]',
        className,
      )}
      {...props}
    />
  );
}

export function FloatingPanel({ className, ...props }: PanelProps) {
  return (
    <Panel
      className={cn('z-50 border-[var(--border-input)] shadow-[var(--shadow-floating)]', className)}
      {...props}
    />
  );
}
