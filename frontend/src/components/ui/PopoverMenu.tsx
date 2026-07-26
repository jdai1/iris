import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';
import { FloatingPanel } from './Panel';

export function PopoverMenu({ className, ...props }: ComponentProps<'div'>) {
  return <FloatingPanel className={cn('grid min-w-44 gap-0 p-0', className)} {...props} />;
}
