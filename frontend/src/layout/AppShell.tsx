import { Box, type BoxProps } from '@chakra-ui/react';

export function AppShell(props: BoxProps) {
  return <Box as="main" className="app-shell" bg="bg.canvas" {...props} />;
}
