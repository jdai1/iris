import { Box, type BoxProps } from '@chakra-ui/react';

export type PanelProps = BoxProps & {
  interactive?: boolean;
};

export function Panel({ interactive = false, ...props }: PanelProps) {
  return (
    <Box
      bg="bg.surface"
      borderWidth="1px"
      borderColor="border.subtle"
      borderRadius="0"
      boxShadow={interactive ? 'panel' : undefined}
      {...props}
    />
  );
}

export function FloatingPanel(props: BoxProps) {
  return (
    <Panel
      boxShadow="floating"
      borderColor="border.strong"
      zIndex="dropdown"
      {...props}
    />
  );
}
