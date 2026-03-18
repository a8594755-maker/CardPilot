interface EquityDistributionBarProps {
  buckets: number[]; // 5 buckets: 0-20, 20-40, 40-60, 60-80, 80-100
}

const BUCKET_COLORS = [
  '#ef4444', // 0-20% - red
  '#f97316', // 20-40% - orange
  '#eab308', // 40-60% - yellow
  '#84cc16', // 60-80% - lime
  '#22c55e', // 80-100% - green
];

const BUCKET_LABELS = ['0-20%', '20-40%', '40-60%', '60-80%', '80-100%'];

export function EquityDistributionBar({ buckets }: EquityDistributionBarProps) {
  if (!buckets.length) return null;

  const total = buckets.reduce((sum, v) => sum + v, 0);
  if (total === 0) return null;

  return (
    <div className="space-y-1.5">
      {/* Bar with percentage labels inside */}
      <div className="flex h-6 rounded-md overflow-hidden">
        {buckets.map((count, i) => {
          const pct = (count / total) * 100;
          if (pct < 0.5) return null;
          return (
            <div
              key={i}
              className="h-full flex items-center justify-center text-[8px] font-mono font-medium transition-all relative"
              style={{
                width: `${pct}%`,
                backgroundColor: BUCKET_COLORS[i],
                color: i <= 2 ? '#000' : '#fff',
              }}
              title={`${BUCKET_LABELS[i]}: ${count.toFixed(1)} 組合 (${pct.toFixed(1)}%)`}
            >
              {pct > 8 && `${pct.toFixed(0)}%`}
            </div>
          );
        })}
      </div>

      {/* Detailed numbers per bucket */}
      <div className="grid grid-cols-5 gap-0.5 text-center">
        {buckets.map((count, i) => {
          const pct = (count / total) * 100;
          return (
            <div key={i} className="text-[10px] font-mono" style={{ color: BUCKET_COLORS[i] }}>
              <div className="font-medium">{pct.toFixed(1)}%</div>
              <div className="text-[8px] opacity-70">{count.toFixed(1)}</div>
            </div>
          );
        })}
      </div>

      {/* Labels */}
      <div className="grid grid-cols-5 gap-0.5 text-center text-[8px] text-muted-foreground">
        {BUCKET_LABELS.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
    </div>
  );
}
