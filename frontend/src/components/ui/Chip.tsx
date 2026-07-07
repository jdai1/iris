import { Badge, HStack, type BadgeProps, type StackProps } from '@chakra-ui/react';

export function Chip(props: BadgeProps) {
  return (
    <Badge
      variant="outline"
      borderColor="border.strong"
      color="fg.default"
      bg="bg.subtle"
      borderRadius="0"
      fontWeight="500"
      px="2"
      py="0.5"
      {...props}
    />
  );
}

export function ChipList(props: StackProps) {
  const className = props.className ? `chip-list-scroll ${props.className}` : 'chip-list-scroll';
  return <HStack gap="1.5" flexWrap="nowrap" overflowX="auto" maxW="100%" {...props} className={className} />;
}
