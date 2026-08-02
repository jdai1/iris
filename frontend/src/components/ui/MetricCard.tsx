import { Panel, type PanelProps } from './Panel';
import { cn } from '@/lib/utils';

export function MetricCard({ className, label, value, ...props }: PanelProps & { label: string; value: number | string }) {
  return (
    <Panel className={cn('grid gap-1 p-4', className)} {...props}>
      <span className="text-xs uppercase text-muted-foreground">{label}</span>
      <strong className="text-2xl font-semibold leading-tight text-foreground">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </strong>
    </Panel>
  );
}
