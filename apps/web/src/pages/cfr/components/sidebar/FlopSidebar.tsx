import { memo, useCallback } from 'react';
import type { CfrConfig, FlopEntry } from '../../lib/cfr-api';
import type { TextureFilter, PairingFilter, HighCardFilter } from '../../hooks/useFlopBrowser';
import { FilterChip } from '../shared/FilterChip';
import { PokerCardDisplay } from '../shared/PokerCardDisplay';
import { ConfigDropdown } from '../shared/ConfigDropdown';

interface FlopSidebarProps {
  configs: CfrConfig[];
  selectedConfig: string;
  onSelectConfig: (name: string) => void;
  filteredFlops: FlopEntry[];
  totalFlops: number;
  selectedBoardId: number | null;
  onSelectBoard: (boardId: number) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  textureFilter: TextureFilter;
  onTextureFilter: (f: TextureFilter) => void;
  pairingFilter: PairingFilter;
  onPairingFilter: (f: PairingFilter) => void;
  highCardFilter: HighCardFilter;
  onHighCardFilter: (f: HighCardFilter) => void;
  onResetFilters?: () => void;
  onCollapse?: () => void;
}

const TAG_CLASSES: Record<string, string> = {
  rainbow: 'bg-emerald-500/15 text-emerald-400',
  'two-tone': 'bg-blue-500/15 text-blue-400',
  monotone: 'bg-purple-500/15 text-purple-400',
  paired: 'bg-amber-500/15 text-amber-400',
  trips: 'bg-red-500/15 text-red-400',
  connected: 'bg-sky-500/15 text-sky-400',
};

export const FlopSidebar = memo(function FlopSidebar(props: FlopSidebarProps) {
  const {
    configs,
    selectedConfig,
    onSelectConfig,
    filteredFlops,
    totalFlops,
    selectedBoardId,
    onSelectBoard,
    searchQuery,
    onSearchChange,
    textureFilter,
    onTextureFilter,
    pairingFilter,
    onPairingFilter,
    highCardFilter,
    onHighCardFilter,
    onResetFilters,
    onCollapse,
  } = props;

  const hasActiveFilters =
    textureFilter !== 'all' || pairingFilter !== 'all' || highCardFilter !== 'all';

  // Scroll selected board into view
  const selectedRef = useCallback(
    (el: HTMLButtonElement | null) => {
      if (el) {
        requestAnimationFrame(() => el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
      }
    },
    [selectedBoardId],
  );

  return (
    <aside className="w-[380px] min-w-[380px] bg-[var(--cp-bg-surface)] border-r border-white/10 flex flex-col h-full overflow-hidden max-lg:w-full max-lg:min-w-0 max-lg:h-auto max-lg:max-h-[50vh]">
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/10">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold text-white">GTO Strategy</h1>
          {onCollapse && (
            <button
              onClick={onCollapse}
              className="hidden lg:flex items-center justify-center w-7 h-7 rounded-md text-slate-500 hover:text-white hover:bg-white/10 transition-colors"
              title="Collapse sidebar"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
          )}
        </div>
        {/* Config selector */}
        <ConfigDropdown configs={configs} selected={selectedConfig} onSelect={onSelectConfig} />
      </div>

      {/* Search */}
      {selectedConfig && (
        <div className="px-5 py-3 border-b border-white/10">
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm pointer-events-none">
              &#128269;
            </span>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder='Search... "AK", "rainbow"'
              className="w-full bg-white/5 border border-white/10 rounded-lg pl-9 pr-8 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50"
            />
            {searchQuery && (
              <button
                onClick={() => onSearchChange('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white text-sm transition-colors"
              >
                &#x2715;
              </button>
            )}
          </div>
        </div>
      )}

      {/* Filters */}
      {selectedConfig && (
        <div className="px-5 py-3 border-b border-white/10 space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Filters
            </div>
            {hasActiveFilters && onResetFilters && (
              <button
                onClick={onResetFilters}
                className="text-[10px] text-blue-400 hover:text-blue-300 transition-colors"
              >
                Clear all
              </button>
            )}
          </div>
          <div>
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
              Suit Pattern
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {(['all', 'rainbow', 'two-tone', 'monotone'] as const).map((v) => (
                <FilterChip
                  key={v}
                  label={v === 'all' ? 'All' : v.charAt(0).toUpperCase() + v.slice(1)}
                  active={textureFilter === v}
                  onClick={() => onTextureFilter(v)}
                />
              ))}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
              Board Type
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {(['all', 'unpaired', 'paired'] as const).map((v) => (
                <FilterChip
                  key={v}
                  label={v === 'all' ? 'All' : v.charAt(0).toUpperCase() + v.slice(1)}
                  active={pairingFilter === v}
                  onClick={() => onPairingFilter(v)}
                />
              ))}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
              High Card
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {(['all', 'A', 'K', 'Q', 'J', 'T-'] as const).map((v) => (
                <FilterChip
                  key={v}
                  label={v === 'all' ? 'All' : v}
                  active={highCardFilter === v}
                  onClick={() => onHighCardFilter(v)}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Flop list */}
      {selectedConfig && (
        <div className="flex-1 overflow-y-auto p-2">
          <div className="px-3 py-1 text-xs text-slate-500">
            {filteredFlops.length} of {totalFlops} boards
          </div>
          {filteredFlops.length === 0 ? (
            <div className="p-6 text-center text-slate-500 text-sm">
              No boards match your filters.
            </div>
          ) : (
            filteredFlops.map((flop) => (
              <button
                key={flop.boardId}
                ref={selectedBoardId === flop.boardId ? selectedRef : undefined}
                onClick={() => onSelectBoard(flop.boardId)}
                style={{ contentVisibility: 'auto', containIntrinsicSize: '0 48px' }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all border ${
                  selectedBoardId === flop.boardId
                    ? 'bg-blue-500/10 border-blue-500/40'
                    : 'border-transparent hover:bg-white/5'
                }`}
              >
                <div className="flex gap-1">
                  {flop.flopCards.map((c, i) => (
                    <PokerCardDisplay key={i} cardIndex={c} size="sm" />
                  ))}
                </div>
                <div className="flex gap-1 flex-wrap">
                  {flop.texture && (
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${TAG_CLASSES[flop.texture] || ''}`}
                    >
                      {flop.texture}
                    </span>
                  )}
                  {flop.pairing === 'paired' && (
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${TAG_CLASSES.paired}`}
                    >
                      paired
                    </span>
                  )}
                  {flop.connectivity === 'connected' && (
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${TAG_CLASSES.connected}`}
                    >
                      connected
                    </span>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      )}
    </aside>
  );
});
