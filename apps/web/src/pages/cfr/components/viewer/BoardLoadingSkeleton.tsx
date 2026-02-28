import { memo } from 'react';

export const BoardLoadingSkeleton = memo(function BoardLoadingSkeleton() {
  return (
    <div className="flex flex-col h-full min-h-0 animate-pulse">
      {/* Top bar */}
      <div className="flex items-center gap-4 pb-3 border-b border-white/10 shrink-0">
        <div className="flex gap-1.5">
          {[0, 1, 2].map(i => (
            <div key={i} className="w-8 h-10 rounded bg-white/10" />
          ))}
        </div>
        <div className="flex gap-3">
          <div className="w-16 h-3 rounded bg-white/5" />
          <div className="w-16 h-3 rounded bg-white/5" />
          <div className="w-12 h-3 rounded bg-white/5" />
        </div>
        <div className="ml-auto flex gap-3">
          <div className="w-24 h-7 rounded-lg bg-white/5" />
          <div className="w-28 h-7 rounded-lg bg-white/5" />
        </div>
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-2 py-2 border-b border-white/10 shrink-0">
        <div className="w-20 h-4 rounded bg-white/5" />
        <div className="ml-auto flex gap-1.5">
          {[0, 1, 2].map(i => (
            <div key={i} className="w-16 h-6 rounded-lg bg-white/5" />
          ))}
        </div>
      </div>

      {/* Two-panel: matrix + detail */}
      <div className="flex gap-5 mt-3 flex-1 min-h-0">
        {/* Matrix skeleton */}
        <div className="shrink-0 max-lg:w-full" style={{ width: 'clamp(400px, calc(100vh - 240px), 900px)' }}>
          <div className="grid gap-0.5" style={{ gridTemplateColumns: 'repeat(13, minmax(0, 1fr))' }}>
            {Array.from({ length: 169 }).map((_, i) => (
              <div key={i} className="aspect-square rounded-sm bg-white/[0.03]" />
            ))}
          </div>
        </div>

        {/* Detail panel skeleton */}
        <div className="flex-1 min-w-[220px] flex flex-col gap-3 max-lg:hidden">
          <div className="w-48 h-7 rounded-lg bg-white/5" />
          <div className="bg-white/[0.03] border border-white/5 rounded-xl p-4 space-y-3">
            <div className="w-28 h-3 rounded bg-white/5" />
            <div className="h-6 rounded-md bg-white/5" />
            <div className="space-y-2">
              {[0, 1, 2].map(i => (
                <div key={i} className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded bg-white/5" />
                  <div className="w-16 h-3 rounded bg-white/5" />
                  <div className="ml-auto w-10 h-3 rounded bg-white/5" />
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white/[0.02] border border-white/5 rounded-xl p-4 h-20" />
        </div>
      </div>
    </div>
  );
});
