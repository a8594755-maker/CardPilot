import { useState } from 'react';
import type { HandCategory } from '../../lib/hand-categorizer';

type CategoryMode = 'percentage' | 'absolute';

interface StrategyPanelProps {
  oopCategories: HandCategory[];
  ipCategories?: HandCategory[];
}

export function StrategyPanel({ oopCategories, ipCategories }: StrategyPanelProps) {
  const [mode, setMode] = useState<CategoryMode>('absolute');

  if (!oopCategories.length) return null;

  const hasIp = ipCategories && ipCategories.length > 0;

  // Build lookup for IP categories
  const ipMap = new Map<string, HandCategory>();
  if (ipCategories) {
    for (const cat of ipCategories) {
      ipMap.set(cat.key, cat);
    }
  }

  // Find max for bar scaling
  const allCombos = [
    ...oopCategories.map((c) => (mode === 'percentage' ? c.percentage * 100 : c.combos)),
    ...(ipCategories || []).map((c) => (mode === 'percentage' ? c.percentage * 100 : c.combos)),
  ];
  const maxVal = Math.max(...allCombos, 0.01);

  // Separate made hands and draws
  const madeHandKeys = new Set([
    'straights',
    'sets',
    'two_pair',
    'overpair',
    'top_pair',
    'pp_below_top',
    'middle_pair',
    'weak_pair',
    'ace_high',
    'no_made_hand',
  ]);

  const madeHands = oopCategories.filter((c) => madeHandKeys.has(c.key));
  const draws = oopCategories.filter((c) => !madeHandKeys.has(c.key));

  return (
    <div className="space-y-1">
      {/* Mode Toggle */}
      <div className="flex items-center gap-2 mb-2">
        <button
          onClick={() => setMode('percentage')}
          className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded ${mode === 'percentage' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}
        >
          <span className="w-2 h-2 rounded-full border border-current inline-flex items-center justify-center">
            {mode === 'percentage' && <span className="w-1 h-1 rounded-full bg-current" />}
          </span>
          Percentage
        </button>
        <button
          onClick={() => setMode('absolute')}
          className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded ${mode === 'absolute' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}
        >
          <span className="w-2 h-2 rounded-full border border-current inline-flex items-center justify-center">
            {mode === 'absolute' && <span className="w-1 h-1 rounded-full bg-current" />}
          </span>
          Absolute
        </button>
      </div>

      {/* Made Hands */}
      {madeHands.map((cat) => (
        <DualCategoryRow
          key={cat.key}
          oopCategory={cat}
          ipCategory={ipMap.get(cat.key)}
          maxVal={maxVal}
          mode={mode}
          hasIp={!!hasIp}
        />
      ))}

      {/* Draws separator */}
      {draws.length > 0 && (
        <>
          <div className="border-t border-border my-2" />
          {draws.map((cat) => (
            <DualCategoryRow
              key={cat.key}
              oopCategory={cat}
              ipCategory={ipMap.get(cat.key)}
              maxVal={maxVal}
              mode={mode}
              hasIp={!!hasIp}
            />
          ))}
        </>
      )}

      {/* Player Legend */}
      {hasIp && (
        <div className="flex items-center gap-3 pt-2 border-t border-border mt-2 text-[10px] text-muted-foreground">
          <div className="flex items-center gap-1">
            <div className="w-3 h-2 rounded-sm bg-[#3b82f6]" />
            <span>OOP</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-2 rounded-sm bg-[#22c55e]" />
            <span>IP</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-2 rounded-sm bg-[#6b7280]/40" />
            <span>Diff OOP/IP</span>
          </div>
        </div>
      )}
    </div>
  );
}

function DualCategoryRow({
  oopCategory,
  ipCategory,
  maxVal,
  mode,
  hasIp,
}: {
  oopCategory: HandCategory;
  ipCategory?: HandCategory;
  maxVal: number;
  mode: CategoryMode;
  hasIp: boolean;
}) {
  const oopVal = mode === 'percentage' ? oopCategory.percentage * 100 : oopCategory.combos;
  const ipVal = ipCategory
    ? mode === 'percentage'
      ? ipCategory.percentage * 100
      : ipCategory.combos
    : 0;
  const oopWidth = maxVal > 0 ? (oopVal / maxVal) * 100 : 0;
  const ipWidth = maxVal > 0 ? (ipVal / maxVal) * 100 : 0;

  const formatVal = (v: number) => {
    if (mode === 'percentage') return v.toFixed(1);
    return v.toFixed(v >= 10 ? 1 : 1);
  };

  return (
    <div className="flex items-center gap-1.5 text-xs py-0.5 cursor-pointer hover:bg-secondary/50 rounded px-1 -mx-1">
      {/* Checkmark */}
      <span className="w-3 text-[10px] text-green-500 flex-shrink-0">&#10003;</span>

      {/* Category Name */}
      <div
        className="w-[80px] flex-shrink-0 truncate text-muted-foreground text-[11px]"
        title={oopCategory.name}
      >
        {oopCategory.name}
      </div>

      {/* Values + Bars */}
      <div className="flex-1 min-w-0">
        {hasIp ? (
          <div className="space-y-0.5">
            {/* OOP bar */}
            <div className="flex items-center gap-1">
              <div className="w-[32px] text-right font-mono text-[10px] flex-shrink-0">
                {formatVal(oopVal)}
              </div>
              <div className="flex-1 h-3 bg-secondary/30 rounded-sm overflow-hidden">
                <div
                  className="h-full rounded-sm"
                  style={{ width: `${oopWidth}%`, backgroundColor: '#3b82f6' }}
                />
              </div>
            </div>
            {/* IP bar */}
            <div className="flex items-center gap-1">
              <div className="w-[32px] text-right font-mono text-[10px] flex-shrink-0">
                {formatVal(ipVal)}
              </div>
              <div className="flex-1 h-3 bg-secondary/30 rounded-sm overflow-hidden">
                <div
                  className="h-full rounded-sm"
                  style={{ width: `${ipWidth}%`, backgroundColor: '#22c55e' }}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <div className="flex-1 h-4 bg-secondary/30 rounded-sm overflow-hidden">
              <div
                className="h-full rounded-sm"
                style={{ width: `${oopWidth}%`, backgroundColor: '#3b82f6' }}
              />
            </div>
            <div className="w-[40px] text-right font-mono text-[10px] flex-shrink-0">
              {formatVal(oopVal)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
