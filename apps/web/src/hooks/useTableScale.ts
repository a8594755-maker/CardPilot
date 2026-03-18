import { useEffect, useState } from 'react';

export type TableScaleLimiter = 'width' | 'height' | 'none';

interface UseTableScaleOptions {
  container: HTMLElement | null;
  baseWidth: number;
  baseHeight: number;
  minScale: number;
  maxScale: number;
  enabled?: boolean;
}

interface TableScaleState {
  scale: number;
  availableWidth: number;
  availableHeight: number;
  scaledWidth: number;
  scaledHeight: number;
  limiter: TableScaleLimiter;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function useTableScale({
  container,
  baseWidth,
  baseHeight,
  minScale,
  maxScale,
  enabled = true,
}: UseTableScaleOptions): TableScaleState {
  const [state, setState] = useState<TableScaleState>({
    scale: 1,
    availableWidth: 0,
    availableHeight: 0,
    scaledWidth: baseWidth,
    scaledHeight: baseHeight,
    limiter: 'none',
  });

  useEffect(() => {
    if (!enabled || !container) {
      setState({
        scale: 1,
        availableWidth: 0,
        availableHeight: 0,
        scaledWidth: baseWidth,
        scaledHeight: baseHeight,
        limiter: 'none',
      });
      return;
    }

    const compute = () => {
      const rect = container.getBoundingClientRect();
      const availableWidth = Math.max(0, rect.width);
      const availableHeight = Math.max(0, rect.height);

      if (availableWidth <= 0 || availableHeight <= 0 || baseWidth <= 0 || baseHeight <= 0) {
        return;
      }

      const widthScale = availableWidth / baseWidth;
      const heightScale = availableHeight / baseHeight;
      const rawScale = Math.min(widthScale, heightScale);
      const scale = clamp(rawScale, minScale, maxScale);
      const limiter: TableScaleLimiter = widthScale <= heightScale ? 'width' : 'height';

      setState((prev) => {
        const scaledWidth = baseWidth * scale;
        const scaledHeight = baseHeight * scale;
        if (
          Math.abs(prev.scale - scale) < 0.001 &&
          Math.abs(prev.availableWidth - availableWidth) < 0.5 &&
          Math.abs(prev.availableHeight - availableHeight) < 0.5
        ) {
          return prev;
        }
        return {
          scale,
          availableWidth,
          availableHeight,
          scaledWidth,
          scaledHeight,
          limiter,
        };
      });
    };

    compute();

    // Only recompute on window/screen resize — NOT on container content changes.
    // A ResizeObserver on the container would fire when sibling elements
    // (cp-below-table-tray) change height, causing the table to jitter.
    window.addEventListener('resize', compute);

    return () => {
      window.removeEventListener('resize', compute);
    };
  }, [container, baseWidth, baseHeight, minScale, maxScale, enabled]);

  return state;
}

export default useTableScale;
