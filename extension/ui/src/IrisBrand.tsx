import { cn } from './lib/utils';

export function IrisBrand({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground', className)}>
      <img className="size-6 object-contain" src={chrome.runtime.getURL('icons/iris-32.png')} alt="" aria-hidden="true" />
      <span>iris</span>
    </span>
  );
}
