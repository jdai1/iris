import { FormEvent, ReactNode } from 'react';
import { Box, HStack, Input } from '@chakra-ui/react';
import { CornerDownLeft, Search } from 'lucide-react';
import { IconButton } from './components/ui';

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
      <HStack display="contents">
        <Search size={18} />
        <Input unstyled border="0" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} autoFocus={autoFocus} />
        <IconButton type="submit" uiVariant="plainIcon" disabled={disabled} aria-label="Submit search" data-tooltip="Submit" data-tooltip-placement="bottom">
          <CornerDownLeft size={18} />
        </IconButton>
        <Box display="contents">
          {children}
        </Box>
      </HStack>
    </form>
  );
}
