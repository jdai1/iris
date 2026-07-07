import { StatusBadge } from './ui';

export function StatusPill({ value }: { value: string }) {
  return <StatusBadge className={`status-pill status-${value}`} value={value} />;
}
