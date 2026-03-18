import { useState } from 'react';
import type { HandCategoryWithActions } from '../../lib/board-aware-categorizer';
import { getActionColor, formatActionLabel } from '../../lib/strategy-utils';
import { useStrategyBrowser } from '../../stores/strategy-browser';

type CategoryMode = 'percentage' | 'absolute';

interface StatisticsPanelProps {
  oopCategories: HandCategoryWithActions[];
  oopTotalCombos: number;
  actions: string[];
  ipCategories?: HandCategoryWithActions[];
  ipTotalCombos?: number;
}

export function StatisticsPanel({
  oopCategories,
  oopTotalCombos,
  actions,
  ipCategories,
  ipTotalCombos,
}: StatisticsPanelProps) {
  const [mode, setMode] = useState<CategoryMode>('percentage');
  const { hoveredCategory, fixedCategory, setHoveredCategory, setFixedCategory } =
    useStrategyBrowser();

  if (!oopCategories.length) return null;

  const hasIp = ipCategories && ipCategories.length > 0;

  // Build lookup for IP categories
  const ipMap = new Map<string, HandCategoryWithActions>();
  if (ipCategories) {
    for (const cat of ipCategories) {
      ipMap.set(cat.key, cat);
    }
  }

  // Separate made hands and draws
  const madeHandKeys = new Set([
    'flush',
    'straight',
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

  function handleCategoryHover(key: string | null) {
    if (!fixedCategory) {
      setHoveredCategory(key);
    }
  }

  function handleCategoryClick(key: string) {
    if (fixedCategory === key) {
      setFixedCategory(null);
      setHoveredCategory(null);
    } else {
      setFixedCategory(key);
      setHoveredCategory(key);
    }
  }

  const activeCategory = fixedCategory || hoveredCategory;

  return (
    <div className="space-y-1">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-medium">牌型分佈</div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setMode('percentage')}
            className={`text-[10px] px-1.5 py-0.5 rounded ${mode === 'percentage' ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
          >
            %
          </button>
          <button
            onClick={() => setMode('absolute')}
            className={`text-[10px] px-1.5 py-0.5 rounded ${mode === 'absolute' ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground'}`}
          >
            #
          </button>
        </div>
      </div>

      {/* Section: 成牌 (Made Hands) */}
      <div className="text-[10px] text-muted-foreground font-medium mb-0.5">成牌</div>
      {madeHands.map((cat) => (
        <CategoryRow
          key={cat.key}
          category={cat}
          ipCategory={ipMap.get(cat.key)}
          totalCombos={oopTotalCombos}
          ipTotalCombos={ipTotalCombos}
          actions={actions}
          mode={mode}
          hasIp={!!hasIp}
          isActive={activeCategory === cat.key}
          isFixed={fixedCategory === cat.key}
          onHover={handleCategoryHover}
          onClick={handleCategoryClick}
        />
      ))}

      {/* Section: 聽牌 (Draws) */}
      {draws.length > 0 && (
        <>
          <div className="border-t border-border my-1.5" />
          <div className="text-[10px] text-muted-foreground font-medium mb-0.5">聽牌</div>
          {draws.map((cat) => (
            <CategoryRow
              key={cat.key}
              category={cat}
              ipCategory={ipMap.get(cat.key)}
              totalCombos={oopTotalCombos}
              ipTotalCombos={ipTotalCombos}
              actions={actions}
              mode={mode}
              hasIp={!!hasIp}
              isActive={activeCategory === cat.key}
              isFixed={fixedCategory === cat.key}
              onHover={handleCategoryHover}
              onClick={handleCategoryClick}
            />
          ))}
        </>
      )}

      {/* Action Legend */}
      <div className="flex items-center gap-2 pt-2 border-t border-border mt-2 text-[10px] text-muted-foreground flex-wrap">
        {actions.map((action) => (
          <div key={action} className="flex items-center gap-0.5">
            <div
              className="w-2 h-2 rounded-sm"
              style={{ backgroundColor: getActionColor(action) }}
            />
            <span>{formatActionLabel(action)}</span>
          </div>
        ))}
      </div>

      {/* Player Legend */}
      {hasIp && (
        <div className="flex items-center gap-3 pt-1 text-[10px] text-muted-foreground">
          <div className="flex items-center gap-1">
            <div className="w-3 h-2 rounded-sm bg-[#3b82f6]" />
            <span>OOP</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-2 rounded-sm bg-[#22c55e]" />
            <span>IP</span>
          </div>
        </div>
      )}
    </div>
  );
}

function CategoryRow({
  category,
  ipCategory,
  totalCombos,
  ipTotalCombos,
  actions,
  mode,
  hasIp,
  isActive,
  isFixed,
  onHover,
  onClick,
}: {
  category: HandCategoryWithActions;
  ipCategory?: HandCategoryWithActions;
  totalCombos: number;
  ipTotalCombos?: number;
  actions: string[];
  mode: CategoryMode;
  hasIp: boolean;
  isActive: boolean;
  isFixed: boolean;
  onHover: (key: string | null) => void;
  onClick: (key: string) => void;
}) {
  const oopPct = category.percentage * 100;
  const ipPct = ipCategory ? ipCategory.percentage * 100 : 0;
  const oopVal = mode === 'percentage' ? oopPct : category.combos;
  const ipVal = ipCategory ? (mode === 'percentage' ? ipPct : ipCategory.combos) : 0;

  const formatVal = (v: number) => {
    if (mode === 'percentage') return `${v.toFixed(1)}%`;
    return v.toFixed(1);
  };

  return (
    <div
      className={`flex items-center gap-1 text-xs py-[3px] cursor-pointer rounded px-1.5 -mx-1 transition-colors ${
        isActive ? 'bg-primary/15 ring-1 ring-primary/30' : 'hover:bg-secondary/40'
      } ${isFixed ? 'ring-2 ring-primary/50' : ''}`}
      onMouseEnter={() => onHover(category.key)}
      onMouseLeave={() => onHover(null)}
      onContextMenu={(e) => {
        e.preventDefault();
        onClick(category.key);
      }}
      onClick={() => onClick(category.key)}
    >
      {/* Category Name (Chinese) */}
      <div
        className="w-[72px] flex-shrink-0 truncate text-[11px] font-medium"
        title={`${category.nameZh} (${category.name})`}
      >
        {category.nameZh}
      </div>

      {/* Values + Action-Segmented Bars */}
      <div className="flex-1 min-w-0">
        {hasIp ? (
          <div className="space-y-[2px]">
            {/* OOP bar */}
            <div className="flex items-center gap-1">
              <div className="w-[36px] text-right font-mono text-[10px] flex-shrink-0 text-blue-400">
                {formatVal(oopVal)}
              </div>
              <ActionSegmentedBar category={category} actions={actions} totalCombos={totalCombos} />
            </div>
            {/* IP bar */}
            <div className="flex items-center gap-1">
              <div className="w-[36px] text-right font-mono text-[10px] flex-shrink-0 text-green-400">
                {formatVal(ipVal)}
              </div>
              {ipCategory ? (
                <ActionSegmentedBar
                  category={ipCategory}
                  actions={actions}
                  totalCombos={ipTotalCombos || 0}
                />
              ) : (
                <div className="flex-1 h-3 bg-secondary/20 rounded-sm" />
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <ActionSegmentedBar category={category} actions={actions} totalCombos={totalCombos} />
            <div className="w-[42px] text-right font-mono text-[10px] flex-shrink-0">
              {formatVal(oopVal)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * GTO+-style action-segmented bar.
 * Each segment's width is proportional to how many combos in this category
 * take that action, relative to the total range.
 */
function ActionSegmentedBar({
  category,
  actions,
  totalCombos,
}: {
  category: HandCategoryWithActions;
  actions: string[];
  totalCombos: number;
}) {
  if (category.combos <= 0 || totalCombos <= 0) {
    return <div className="flex-1 h-[14px] bg-secondary/20 rounded-sm" />;
  }

  // Width of entire bar proportional to this category's share of total range
  const categoryShare = Math.min((category.combos / totalCombos) * 100, 100);

  return (
    <div className="flex-1 h-[14px] bg-secondary/20 rounded-sm overflow-hidden relative">
      <div className="h-full flex" style={{ width: `${categoryShare}%` }}>
        {actions.map((action) => {
          const actionCombos = category.actionDistribution[action] || 0;
          if (actionCombos <= 0) return null;
          const segmentShare = (actionCombos / category.combos) * 100;

          return (
            <div
              key={action}
              className="h-full"
              style={{
                width: `${segmentShare}%`,
                backgroundColor: getActionColor(action),
              }}
              title={`${formatActionLabel(action)}: ${actionCombos.toFixed(1)} 組合`}
            />
          );
        })}
      </div>
    </div>
  );
}
