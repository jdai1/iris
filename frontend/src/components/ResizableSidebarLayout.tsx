import { CSSProperties, PointerEvent, ReactNode, useEffect, useRef, useState } from 'react';
import { cn } from '../lib/utils';

type SidebarWidthStyle = CSSProperties & { '--sidebar-width': string };

function storedWidth(storageKey: string, fallback: number, minWidth: number, maxWidth: number) {
  if (typeof window === 'undefined') return fallback;
  const stored = window.localStorage.getItem(storageKey);
  if (stored === null) return fallback;
  const value = Number(stored);
  return Number.isFinite(value) ? Math.min(maxWidth, Math.max(minWidth, value)) : fallback;
}

export function ResizableSidebarLayout({
  sidebar,
  children,
  storageKey,
  defaultWidth = 176,
  minWidth = 144,
  maxWidth = 360,
  className,
}: {
  sidebar: ReactNode;
  children: ReactNode;
  storageKey: string;
  defaultWidth?: number;
  minWidth?: number;
  maxWidth?: number;
  className?: string;
}) {
  const [width, setWidth] = useState(() => storedWidth(storageKey, defaultWidth, minWidth, maxWidth));
  const [dragging, setDragging] = useState(false);
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);

  useEffect(() => {
    window.localStorage.setItem(storageKey, String(width));
  }, [storageKey, width]);

  useEffect(() => () => setDocumentResizeState(false), []);

  function updateWidth(clientX: number) {
    const left = layoutRef.current?.getBoundingClientRect().left ?? 0;
    setWidth(Math.min(maxWidth, Math.max(minWidth, Math.round(clientX - left))));
  }

  function startResize(event: PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    draggingRef.current = true;
    setDragging(true);
    setDocumentResizeState(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    updateWidth(event.clientX);
  }

  function moveResize(event: PointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    updateWidth(event.clientX);
  }

  function stopResize(event: PointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    setDragging(false);
    setDocumentResizeState(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function resizeWithKeyboard(direction: -1 | 1) {
    setWidth((current) => Math.min(maxWidth, Math.max(minWidth, current + direction * 12)));
  }

  return (
    <div
      ref={layoutRef}
      className={cn('relative grid grid-cols-1 lg:grid-cols-[var(--sidebar-width)_minmax(0,1fr)]', className)}
      style={{ '--sidebar-width': `${width}px` } as SidebarWidthStyle}
    >
      {sidebar}
      {children}
      <div
        className="group/resize absolute inset-y-0 z-30 hidden w-3 -translate-x-1/2 cursor-col-resize touch-none items-stretch justify-center outline-none lg:flex"
        style={{ left: width }}
        role="separator"
        aria-label="Resize sidebar"
        aria-orientation="vertical"
        aria-valuemin={minWidth}
        aria-valuemax={maxWidth}
        aria-valuenow={width}
        tabIndex={0}
        onPointerDown={startResize}
        onPointerMove={moveResize}
        onPointerUp={stopResize}
        onPointerCancel={stopResize}
        onDoubleClick={() => setWidth(defaultWidth)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft') {
            event.preventDefault();
            resizeWithKeyboard(-1);
          } else if (event.key === 'ArrowRight') {
            event.preventDefault();
            resizeWithKeyboard(1);
          }
        }}
      >
        <span className={cn('w-px bg-transparent transition-colors group-hover/resize:bg-primary/60 group-focus/resize:bg-primary/60', dragging && 'bg-primary/70')} />
      </div>
    </div>
  );
}

function setDocumentResizeState(active: boolean) {
  if (typeof document === 'undefined') return;
  document.body.style.cursor = active ? 'col-resize' : '';
  document.body.style.userSelect = active ? 'none' : '';
}
