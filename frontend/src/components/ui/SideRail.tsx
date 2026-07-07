import { Box, type BoxProps } from '@chakra-ui/react';
import { Button, type UiButtonProps } from './Button';

export function SideRail(props: BoxProps) {
  return <Box display="grid" alignContent="start" gap="1" minW="0" {...props} />;
}

export function SideRailSection(props: BoxProps) {
  return <Box color="fg.subtle" fontSize="xs" fontWeight="600" textTransform="uppercase" px="2" py="1.5" {...props} />;
}

export function SideRailItem({ active = false, ...props }: UiButtonProps & { active?: boolean }) {
  return (
    <Button
      uiVariant="nav"
      minH="8"
      px="2"
      bg={active ? 'bg.subtle' : undefined}
      {...props}
    />
  );
}
