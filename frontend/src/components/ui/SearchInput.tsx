import type { ComponentProps } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';

export type SearchInputProps = ComponentProps<'input'> & {
  icon?: boolean;
  wrapperClassName?: string;
};

export function SearchInput({ className, icon = true, wrapperClassName, ...props }: SearchInputProps) {
  return (
    <label
      className={cn(
        'flex min-h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-foreground shadow-xs focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/30',
        wrapperClassName,
      )}
    >
      {icon && <Search aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />}
      <input
        className={cn('min-h-8 min-w-0 flex-1 border-0 bg-transparent p-0 text-sm outline-none', className)}
        {...props}
      />
    </label>
  );
}
