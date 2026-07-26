import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';
import { Button, type UiButtonProps } from './button';

export function SideRail({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('grid min-w-0 content-start gap-1', className)} {...props} />;
}

export function SideRailSection({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('px-2 py-1.5 text-xs font-semibold uppercase text-[var(--text-subtle)]', className)} {...props} />;
}

export function SideRailItem({ active = false, className, ...props }: UiButtonProps & { active?: boolean }) {
  return (
    <Button
      uiVariant="nav"
      className={cn('min-h-8 px-2', active && 'bg-[var(--bg-hover)]', className)}
      {...props}
    />
  );
}
