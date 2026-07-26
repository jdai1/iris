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
        'rounded-xl border bg-card text-card-foreground',
        interactive && 'shadow-sm',
        className,
      )}
      {...props}
    />
  );
}

export function FloatingPanel({ className, ...props }: PanelProps) {
  return (
    <Panel
      className={cn('z-50 border-border shadow-lg', className)}
      {...props}
    />
  );
}
