import { Text } from '@chakra-ui/react';
import { Panel, type PanelProps } from './Panel';

export function MetricCard({ label, value, ...props }: PanelProps & { label: string; value: number | string }) {
  return (
    <Panel p="4" display="grid" gap="1" {...props}>
      <Text as="span" color="fg.muted" fontSize="xs" textTransform="uppercase">
        {label}
      </Text>
      <Text as="strong" color="fg.default" fontSize="2xl" lineHeight="1.1" fontWeight="600">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </Text>
    </Panel>
  );
}
