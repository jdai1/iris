import { Search } from 'lucide-react';
import { Box, HStack, Input, type InputProps } from '@chakra-ui/react';

export type SearchInputProps = InputProps & {
  icon?: boolean;
};

export function SearchInput({ icon = true, ...props }: SearchInputProps) {
  return (
    <HStack
      borderBottomWidth="1px"
      borderBottomColor="border.subtle"
      bg="bg.surface"
      color="fg.default"
      gap="2"
      minH="9"
      borderRadius="0"
      _focusWithin={{ borderBottomColor: 'accent.default', outline: '2px solid var(--focus-ring)', outlineOffset: '2px' }}
    >
      {icon && (
        <Box as={Search} width="14px" height="14px" color="fg.muted" flexShrink="0" />
      )}
      <Input
        variant="flushed"
        border="0"
        minH="8"
        px="0"
        fontSize="sm"
        _focusVisible={{ boxShadow: 'none', borderColor: 'transparent' }}
        {...props}
      />
    </HStack>
  );
}
