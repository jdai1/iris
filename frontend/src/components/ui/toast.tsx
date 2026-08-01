import { CircleAlert, CircleCheck, X } from 'lucide-react';
import { Toast as ToastPrimitive } from 'radix-ui';
import { cn } from '@/lib/utils';

export type ToastNotice = {
  id: number;
  title: string;
  description?: string;
  tone?: 'success' | 'error';
};

export function ToastRegion({ notice, onDismiss }: { notice: ToastNotice | null; onDismiss: () => void }) {
  return (
    <ToastPrimitive.Provider swipeDirection="right" duration={3500}>
      {notice && (
        <ToastPrimitive.Root
          key={notice.id}
          open
          onOpenChange={(open) => {
            if (!open) onDismiss();
          }}
          className={cn(
            'grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 rounded-lg border bg-popover p-4 text-popover-foreground shadow-lg',
            'data-[state=open]:animate-in data-[state=open]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0',
            notice.tone === 'error' ? 'border-destructive/35' : 'border-primary/25',
          )}
        >
          {notice.tone === 'error' ? (
            <CircleAlert className="mt-0.5 size-4 text-destructive" aria-hidden="true" />
          ) : (
            <CircleCheck className="mt-0.5 size-4 text-primary" aria-hidden="true" />
          )}
          <div className="min-w-0">
            <ToastPrimitive.Title className="text-sm font-medium">{notice.title}</ToastPrimitive.Title>
            {notice.description && (
              <ToastPrimitive.Description className="mt-1 text-sm text-muted-foreground">
                {notice.description}
              </ToastPrimitive.Description>
            )}
          </div>
          <ToastPrimitive.Close className="grid size-6 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground" aria-label="Dismiss notification">
            <X size={14} />
          </ToastPrimitive.Close>
        </ToastPrimitive.Root>
      )}
      <ToastPrimitive.Viewport className="fixed right-4 bottom-4 z-[100] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2 outline-none" />
    </ToastPrimitive.Provider>
  );
}
