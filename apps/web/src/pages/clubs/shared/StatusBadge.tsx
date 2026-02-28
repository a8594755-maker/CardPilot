const STATUS_COLORS: Record<string, string> = {
  online: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  open: "bg-cyan-500/15 text-cyan-400 border-cyan-500/25",
  active: "bg-cyan-500/15 text-cyan-400 border-cyan-500/25",
  pending: "bg-amber-500/15 text-amber-300 border-amber-500/25",
  banned: "bg-red-500/15 text-red-400 border-red-500/25",
  closed: "bg-slate-500/10 text-slate-500 border-slate-500/20",
  finished: "bg-slate-500/10 text-slate-500 border-slate-500/20",
  paused: "bg-amber-500/15 text-amber-300 border-amber-500/25",
  success: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  failed: "bg-red-500/20 text-red-300 border-red-500/30",
};

export function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? STATUS_COLORS.closed;
  return (
    <span className={`inline-block text-[9px] px-1.5 py-0.5 rounded border font-semibold uppercase ${cls}`}>
      {status}
    </span>
  );
}
