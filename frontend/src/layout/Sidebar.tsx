import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export function Sidebar({ className, ...props }: ComponentProps<'aside'>) {
  return (
    <aside
      className={cn(
        'sticky top-0 z-30 flex h-auto border-b bg-sidebar text-sidebar-foreground md:h-svh md:flex-col md:border-r md:border-b-0',
        className,
      )}
      {...props}
    />
  );
}
