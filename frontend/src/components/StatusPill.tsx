import { Badge } from '@chakra-ui/react';

export function StatusPill({ value }: { value: string }) {
  return <Badge className={`status-pill status-${value}`} variant="outline" borderRadius="0">{value}</Badge>;
}
