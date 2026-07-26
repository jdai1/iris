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
        'flex min-h-9 items-center gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-raised)] text-[var(--text)] focus-within:border-[var(--accent)] focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--focus-ring)]',
        wrapperClassName,
      )}
    >
      {icon && <Search aria-hidden="true" className="size-3.5 shrink-0 text-[var(--text-muted)]" />}
      <input
        className={cn('min-h-8 min-w-0 flex-1 border-0 bg-transparent p-0 text-sm outline-none', className)}
        {...props}
      />
    </label>
  );
}
