import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export function Toolbar({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('flex min-h-10 items-center justify-between gap-3', className)} {...props} />;
}
