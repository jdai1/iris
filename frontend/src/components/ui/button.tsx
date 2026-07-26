import * as React from 'react';
import { Slot } from 'radix-ui';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

export type UiButtonVariant =
  | 'solid'
  | 'outline'
  | 'ghost'
  | 'nav'
  | 'tab'
  | 'danger'
  | 'rowAction'
  | 'plainIcon';

export const buttonVariants = cva(
  'inline-flex h-8 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap border text-sm font-semibold transition-colors outline-none select-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-raised)] disabled:pointer-events-none disabled:opacity-55 [&_svg]:pointer-events-none [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        solid: 'border-[var(--accent)] bg-[var(--accent)] px-3 text-[var(--accent-contrast)] hover:border-[var(--accent-hover)] hover:bg-[var(--accent-hover)]',
        outline: 'border-[var(--border-input)] bg-[var(--bg-raised)] px-3 text-[var(--text)] hover:bg-[var(--bg-hover)]',
        ghost: 'border-transparent bg-transparent px-3 text-[var(--text)] hover:bg-[var(--bg-hover)]',
        nav: 'w-full justify-start border-transparent bg-transparent px-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text)] active:bg-[var(--bg-active)]',
        tab: 'border-transparent bg-transparent px-3 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text)] active:bg-[var(--bg-active)] active:text-[var(--text)]',
        danger: 'border-[var(--status-red-border)] bg-[var(--status-red-bg)] px-3 text-[var(--status-red-text)] hover:bg-[var(--status-red-bg)]',
        rowAction: 'border-transparent bg-transparent px-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text)]',
        plainIcon: 'h-auto min-w-0 border-transparent bg-transparent p-0 text-[var(--text)] hover:bg-transparent hover:text-[var(--text)]',
      },
      size: {
        default: '',
        sm: 'h-7 text-xs',
        lg: 'h-9 px-4',
        icon: 'size-8 p-0',
      },
    },
    defaultVariants: {
      variant: 'outline',
      size: 'default',
    },
  },
);

export type UiButtonProps = React.ComponentProps<'button'> &
  Omit<VariantProps<typeof buttonVariants>, 'variant'> & {
    asChild?: boolean;
    uiVariant?: UiButtonVariant;
    variant?: UiButtonVariant;
  };

export function Button({
  asChild = false,
  className,
  size = 'default',
  uiVariant,
  variant,
  ...props
}: UiButtonProps) {
  const Component = asChild ? Slot.Root : 'button';
  const resolvedVariant = uiVariant ?? variant ?? 'outline';

  return (
    <Component
      data-slot="button"
      data-variant={resolvedVariant}
      data-size={size}
      className={cn(buttonVariants({ variant: resolvedVariant, size, className }))}
      {...props}
    />
  );
}

export type UiIconButtonProps = Omit<UiButtonProps, 'size'>;

export function IconButton({ uiVariant = 'plainIcon', ...props }: UiIconButtonProps) {
  return <Button size="icon" uiVariant={uiVariant} {...props} />;
}
