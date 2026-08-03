import type { ButtonHTMLAttributes } from 'react';
import { cn } from '../lib/utils';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'solid' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'default' | 'icon';
};

const variants = {
  solid: 'border-primary bg-primary text-primary-foreground shadow-xs hover:bg-primary/90',
  outline: 'border-input bg-background text-foreground shadow-xs hover:bg-accent hover:text-accent-foreground',
  ghost: 'border-transparent text-muted-foreground hover:bg-accent hover:text-accent-foreground',
  danger: 'border-transparent text-destructive hover:bg-destructive/10',
};

const sizes = {
  sm: 'h-8 px-2.5 text-xs',
  default: 'h-9 px-3 text-sm',
  icon: 'size-8 p-0',
};

export function Button({ className, variant = 'outline', size = 'default', type = 'button', ...props }: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        'inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:shrink-0',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    />
  );
}
