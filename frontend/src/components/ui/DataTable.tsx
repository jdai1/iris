import { Box, type BoxProps } from '@chakra-ui/react';

export function DataTable(props: BoxProps) {
  return <Box role="table" borderWidth="1px" borderColor="border.subtle" bg="bg.surface" overflow="auto" {...props} />;
}

export function DataTableRow({ selected = false, ...props }: BoxProps & { selected?: boolean }) {
  return (
    <Box
      role="row"
      display="grid"
      alignItems="center"
      borderBottomWidth="1px"
      borderBottomColor="border.subtle"
      bg={selected ? 'bg.subtle' : 'transparent'}
      _hover={{ bg: 'bg.subtle' }}
      {...props}
    />
  );
}

export function DataTableHead(props: BoxProps) {
  return (
    <DataTableRow
      color="fg.muted"
      fontSize="xs"
      fontWeight="600"
      textTransform="uppercase"
      _hover={{ bg: 'transparent' }}
      {...props}
    />
  );
}
