import { Box, type BoxProps } from '@chakra-ui/react';

export function Sidebar(props: BoxProps) {
  return <Box as="aside" className="sidebar" bg="bg.surface" borderColor="border.subtle" {...props} />;
}
