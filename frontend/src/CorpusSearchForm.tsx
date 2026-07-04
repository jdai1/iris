import { FormEvent, ReactNode } from 'react';
import { CornerDownLeft, Search } from 'lucide-react';

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
    <form className={className ? `corpus-search ${className}` : 'corpus-search'} onSubmit={onSubmit}>
      <Search size={18} />
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} autoFocus={autoFocus} />
      <button type="submit" disabled={disabled} aria-label="Submit search" data-tooltip="Submit" data-tooltip-placement="bottom">
        <CornerDownLeft size={18} />
      </button>
      {children}
    </form>
  );
}
