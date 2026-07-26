import { FormEvent, ReactNode } from 'react';
import { CornerDownLeft, Search } from 'lucide-react';
import { IconButton } from './components/ui';
import { cn } from './lib/utils';

type CorpusSearchFormProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  placeholder: string;
  disabled?: boolean;
  autoFocus?: boolean;
  className?: string;
  children?: ReactNode;
};

export function CorpusSearchForm({
  value,
  onChange,
  onSubmit,
  placeholder,
  disabled = false,
  autoFocus = false,
  className,
  children,
}: CorpusSearchFormProps) {
  return (
    <form
      className={cn(
        'flex min-h-12 items-center gap-3 rounded-xl border bg-card px-4 shadow-sm transition-shadow focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20',
        className,
      )}
      onSubmit={onSubmit}
    >
      <Search className="size-4 shrink-0 text-muted-foreground" />
      <input
        className="min-w-0 flex-1 border-0 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
      />
      <IconButton type="submit" uiVariant="plainIcon" disabled={disabled} aria-label="Submit search" data-tooltip="Submit" data-tooltip-placement="bottom">
        <CornerDownLeft size={18} />
      </IconButton>
      {children}
    </form>
  );
}
