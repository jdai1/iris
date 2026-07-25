import { Box, type BoxProps } from '@chakra-ui/react';
import type { View } from '../app/navigation';

export function Workspace({ view, ...props }: BoxProps & { view: View }) {
  const className = view === 'search'
    ? 'workspace workspace-search'
    : 'workspace';

  return <Box className={className} minW="0" {...props} />;
}
