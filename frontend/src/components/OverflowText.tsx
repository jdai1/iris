import { useEffect, useRef, useState } from 'react';

export function OverflowText({
  children,
  className = 'tooltip-overflow-text',
  tooltip,
}: {
  children: string;
  className?: string;
  tooltip?: string;
}) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const [overflowing, setOverflowing] = useState(false);
  const label = tooltip ?? children;

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    function measure() {
      const current = ref.current;
      if (!current) return;
      setOverflowing(current.scrollWidth > current.clientWidth + 1 || current.scrollHeight > current.clientHeight + 1);
    }
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [children]);

  return (
    <span className="overflow-tooltip" data-tooltip={overflowing ? label : undefined}>
      <span ref={ref} className={className}>
        {children}
      </span>
    </span>
  );
}
