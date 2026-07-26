import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export function AppShell({ className, ...props }: ComponentProps<'main'>) {
  return <main className={cn('app-shell', className)} {...props} />;
}
