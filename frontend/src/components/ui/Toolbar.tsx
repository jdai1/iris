import { Flex, type FlexProps } from '@chakra-ui/react';

export function Toolbar(props: FlexProps) {
  return (
    <Flex
      align="center"
      justify="space-between"
      gap="3"
      minH="10"
      {...props}
    />
  );
}
