import type { ComponentProps } from 'react';
import type { View } from '../app/navigation';
import { cn } from '@/lib/utils';

export function Workspace({ view, className, ...props }: ComponentProps<'section'> & { view: View }) {
  const viewClassName = view === 'search'
    ? 'workspace workspace-search'
    : 'workspace';

  return <section className={cn(viewClassName, className)} {...props} />;
}
