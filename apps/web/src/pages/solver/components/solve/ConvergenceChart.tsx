interface ConvergenceChartProps {
  data: Array<{ iteration: number; exploitability: number }>;
}

export function ConvergenceChart({ data }: ConvergenceChartProps) {
  if (data.length < 2) return null;

  const maxIter = Math.max(...data.map((d) => d.iteration));
  const maxExpl = Math.max(...data.map((d) => d.exploitability));
  const minExpl = Math.min(
    ...data.filter((d) => d.exploitability > 0).map((d) => d.exploitability),
  );

  const width = 600;
  const height = 200;
  const padding = { top: 10, right: 40, bottom: 30, left: 60 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  // Use log scale for exploitability
  const logMin = Math.log10(Math.max(minExpl, 0.0001));
  const logMax = Math.log10(Math.max(maxExpl, 0.001));

  const scaleX = (iter: number) => padding.left + (iter / maxIter) * plotW;
  const scaleY = (expl: number) => {
    const logVal = Math.log10(Math.max(expl, 0.0001));
    const normalized = (logVal - logMin) / (logMax - logMin || 1);
    return padding.top + plotH - normalized * plotH;
  };

  const pathD = data
    .map((d, i) => `${i === 0 ? 'M' : 'L'} ${scaleX(d.iteration)} ${scaleY(d.exploitability)}`)
    .join(' ');

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full max-w-[600px]">
      {/* Grid lines */}
      {[0.25, 0.5, 0.75].map((frac) => (
        <line
          key={frac}
          x1={padding.left}
          y1={padding.top + plotH * frac}
          x2={padding.left + plotW}
          y2={padding.top + plotH * frac}
          stroke="hsl(var(--border))"
          strokeWidth={0.5}
        />
      ))}

      {/* Axes */}
      <line
        x1={padding.left}
        y1={padding.top + plotH}
        x2={padding.left + plotW}
        y2={padding.top + plotH}
        stroke="hsl(var(--muted-foreground))"
        strokeWidth={1}
      />
      <line
        x1={padding.left}
        y1={padding.top}
        x2={padding.left}
        y2={padding.top + plotH}
        stroke="hsl(var(--muted-foreground))"
        strokeWidth={1}
      />

      {/* Data line */}
      <path d={pathD} fill="none" stroke="hsl(var(--primary))" strokeWidth={2} />

      {/* Latest point */}
      {data.length > 0 && (
        <circle
          cx={scaleX(data[data.length - 1].iteration)}
          cy={scaleY(data[data.length - 1].exploitability)}
          r={4}
          fill="hsl(var(--primary))"
        />
      )}

      {/* X axis label */}
      <text
        x={padding.left + plotW / 2}
        y={height - 5}
        textAnchor="middle"
        fontSize={10}
        fill="hsl(var(--muted-foreground))"
      >
        Iterations
      </text>

      {/* Y axis label */}
      <text
        x={12}
        y={padding.top + plotH / 2}
        textAnchor="middle"
        fontSize={10}
        fill="hsl(var(--muted-foreground))"
        transform={`rotate(-90, 12, ${padding.top + plotH / 2})`}
      >
        Exploitability
      </text>
    </svg>
  );
}
