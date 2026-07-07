import type { BadgeProps } from '@chakra-ui/react';
import { Chip } from './Chip';

const statusTone: Record<string, BadgeProps> = {
  failed: { color: 'danger.default', bg: 'danger.subtle', borderColor: 'danger.border' },
  error: { color: 'danger.default', bg: 'danger.subtle', borderColor: 'danger.border' },
  complete: { color: 'var(--status-green-text)', bg: 'var(--status-green-bg)', borderColor: 'var(--status-green-border)' },
  completed: { color: 'var(--status-green-text)', bg: 'var(--status-green-bg)', borderColor: 'var(--status-green-border)' },
  success: { color: 'var(--status-green-text)', bg: 'var(--status-green-bg)', borderColor: 'var(--status-green-border)' },
  running: { color: 'var(--status-blue-text)', bg: 'var(--status-blue-bg)', borderColor: 'var(--status-blue-border)' },
  pending: { color: 'fg.muted', bg: 'bg.subtle', borderColor: 'border.strong' },
};

export function StatusBadge({ value, ...props }: BadgeProps & { value: string }) {
  return (
    <Chip
      textTransform="lowercase"
      {...(statusTone[value.toLowerCase()] ?? statusTone.pending)}
      {...props}
    >
      {value}
    </Chip>
  );
}
