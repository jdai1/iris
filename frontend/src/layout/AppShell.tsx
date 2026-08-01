import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export function AppShell({ className, ...props }: ComponentProps<'main'>) {
  return (
    <main
      className={cn('grid min-h-svh grid-cols-1 bg-background transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none md:grid-cols-[13rem_minmax(0,1fr)]', className)}
      {...props}
    />
  );
}
