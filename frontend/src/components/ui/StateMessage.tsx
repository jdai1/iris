import { Box, type BoxProps } from '@chakra-ui/react';

export type StateMessageTone = 'neutral' | 'error';

export type StateMessageProps = BoxProps & {
  tone?: StateMessageTone;
};

export function StateMessage({ tone = 'neutral', ...props }: StateMessageProps) {
  return (
    <Box
      borderWidth="1px"
      borderColor={tone === 'error' ? 'danger.border' : 'border.subtle'}
      bg={tone === 'error' ? 'danger.subtle' : 'bg.surface'}
      color={tone === 'error' ? 'danger.default' : 'fg.muted'}
      px="4"
      py="3"
      fontSize="sm"
      lineHeight="1.5"
      {...props}
    />
  );
}
