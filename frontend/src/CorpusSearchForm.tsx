import { FormEvent, ReactNode, useLayoutEffect, useRef, useState } from 'react';
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
  multiline?: boolean;
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
  multiline = false,
  className,
  children,
}: CorpusSearchFormProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [multilineExpanded, setMultilineExpanded] = useState(false);
  const alignControlsToBottom = multiline && multilineExpanded;

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!multiline || !textarea) {
      setMultilineExpanded(false);
      return;
    }
    const styles = window.getComputedStyle(textarea);
    const lineHeight = Number.parseFloat(styles.lineHeight) || 20;
    const oneLineHeight = lineHeight
      + (Number.parseFloat(styles.paddingTop) || 0)
      + (Number.parseFloat(styles.paddingBottom) || 0);
    setMultilineExpanded(textarea.scrollHeight > oneLineHeight + 1);
  }, [multiline, value]);

  return (
    <form
      className={cn(
        'flex min-h-12 gap-3 rounded-xl border bg-card px-4 shadow-sm transition-shadow focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20',
        alignControlsToBottom ? 'items-end' : 'items-center',
        className,
      )}
      onSubmit={onSubmit}
    >
      <Search className={cn('size-4 shrink-0 text-muted-foreground', alignControlsToBottom && 'mb-3')} />
      {multiline ? (
        <textarea
          ref={textareaRef}
          className="field-sizing-content max-h-40 min-h-5 min-w-0 flex-1 resize-none border-0 bg-transparent py-3 text-sm leading-5 outline-none placeholder:text-muted-foreground"
          rows={1}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }}
          placeholder={placeholder}
          autoFocus={autoFocus}
        />
      ) : (
        <input
          className="min-w-0 flex-1 border-0 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          autoFocus={autoFocus}
        />
      )}
      <IconButton className={alignControlsToBottom ? 'mb-3' : undefined} type="submit" uiVariant="plainIcon" disabled={disabled} aria-label="Submit search" data-tooltip="Submit" data-tooltip-placement="bottom">
        <CornerDownLeft size={18} />
      </IconButton>
      {children}
    </form>
  );
}
