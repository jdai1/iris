import * as React from 'react';
import { Slot } from 'radix-ui';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

export type UiButtonVariant = 'solid' | 'outline' | 'ghost' | 'nav' | 'tab' | 'rowAction' | 'plainIcon';

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
        rowAction: 'px-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground',
        plainIcon: 'h-auto min-w-0 p-0 text-foreground hover:text-primary',
      },
      size: { default: '', sm: 'h-8 gap-1.5 px-2.5 text-xs', icon: 'size-9 p-0' },
    },
    defaultVariants: { variant: 'outline', size: 'default' },
  },
);

type ButtonProps = React.ComponentProps<'button'> & Omit<VariantProps<typeof buttonVariants>, 'variant'> & {
  asChild?: boolean;
  uiVariant?: UiButtonVariant;
};

export function Button({ asChild = false, className, size = 'default', uiVariant = 'outline', ...props }: ButtonProps) {
  const Component = asChild ? Slot.Root : 'button';
  return <Component className={cn(buttonVariants({ variant: uiVariant, size, className }))} {...props} />;
}
