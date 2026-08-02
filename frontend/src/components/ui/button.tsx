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
  'inline-flex h-9 shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md border border-transparent text-sm font-medium transition-colors outline-none select-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        solid: 'bg-primary px-3 text-primary-foreground shadow-xs hover:bg-primary/90',
        outline: 'border-input bg-background px-3 shadow-xs hover:bg-accent hover:text-accent-foreground',
        ghost: 'px-3 hover:bg-accent hover:text-accent-foreground',
        nav: 'w-full justify-start px-2 text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground data-[active=true]:bg-sidebar-accent data-[active=true]:text-sidebar-accent-foreground',
        tab: 'px-3 text-muted-foreground hover:bg-accent hover:text-accent-foreground data-[active=true]:bg-background data-[active=true]:text-foreground data-[active=true]:shadow-xs',
        danger: 'bg-destructive px-3 text-white hover:bg-destructive/90',
        rowAction: 'px-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground',
        plainIcon: 'h-auto min-w-0 p-0 text-foreground hover:text-primary',
      },
      size: {
        default: '',
        sm: 'h-8 gap-1.5 px-2.5 text-xs',
        lg: 'h-10 px-4',
        icon: 'size-9 p-0',
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
