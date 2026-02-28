export function SkeletonRow() {
  return (
    <div className="flex items-center gap-3 p-3 rounded-xl bg-white/5 animate-pulse">
      <div className="h-10 w-10 rounded-xl bg-white/8 shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-3 w-32 rounded-full bg-white/8" />
        <div className="h-2.5 w-48 rounded-full bg-white/5" />
      </div>
      <div className="h-3 w-16 rounded-full bg-white/5 shrink-0" />
    </div>
  );
}

export function TabSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  );
}
