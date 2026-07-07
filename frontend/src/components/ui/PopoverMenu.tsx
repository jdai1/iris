import { type BoxProps } from '@chakra-ui/react';
import { FloatingPanel } from './Panel';

export function PopoverMenu(props: BoxProps) {
  return <FloatingPanel display="grid" gap="0" p="0" minW="44" {...props} />;
}
