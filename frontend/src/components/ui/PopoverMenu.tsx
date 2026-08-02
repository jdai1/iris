import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';
import { FloatingPanel } from './Panel';

export function PopoverMenu({ className, ...props }: ComponentProps<'div'>) {
  return <FloatingPanel className={cn('grid min-w-44 animate-in gap-0 p-0 fade-in-0 zoom-in-95 duration-100 motion-reduce:animate-none', className)} {...props} />;
}
