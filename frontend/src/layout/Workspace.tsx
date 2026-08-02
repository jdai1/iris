import type { ComponentProps } from 'react';
import type { View } from '../app/navigation';
import { cn } from '@/lib/utils';

export function Workspace({ view, className, ...props }: ComponentProps<'section'> & { view: View }) {
  return (
    <section
      data-view={view}
      className={cn('min-h-svh min-w-0 overflow-x-hidden', view === 'search' && 'flex flex-col', className)}
      {...props}
    />
  );
}
