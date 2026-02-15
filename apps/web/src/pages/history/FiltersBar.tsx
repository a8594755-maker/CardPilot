import { useMemo } from "react";

const TAG_OPTIONS = ["SRP", "3bet_pot", "4bet_pot", "all_in"];

interface FiltersValue {
  tags: string[];
  position: string;
  outcome: "ALL" | "WON" | "LOST";
  dateFrom: string;
  dateTo: string;
  query: string;
}

export function FiltersBar({
  value,
  onChange,
  positions,
  totalCount,
  filteredCount,
  onRefresh,
}: {
  value: FiltersValue;
  onChange: (next: Partial<FiltersValue>) => void;
  positions: string[];
  totalCount: number;
  filteredCount: number;
  onRefresh: () => void;
}) {
  const sortedPositions = useMemo(() => [...positions].sort(), [positions]);

  const toggleTag = (tag: string) => {
    const has = value.tags.includes(tag);
    onChange({ tags: has ? value.tags.filter((t) => t !== tag) : [...value.tags, tag] });
  };

  const clearAll = () => {
    onChange({
      tags: [],
      position: "ALL",
      outcome: "ALL",
      dateFrom: "",
      dateTo: "",
      query: "",
    });
  };

  return (
    <div className="history-filters">
      <div className="history-filters-top">
        <input
          value={value.query}
          onChange={(e) => onChange({ query: e.target.value })}
          className="input-field history-search"
          placeholder="Search AsKs, AhKd, board:As9s5h, 3bet_pot..."
        />
        <select className="input-field" value={value.position} onChange={(e) => onChange({ position: e.target.value })}>
          <option value="ALL">All positions</option>
          {sortedPositions.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <select className="input-field" value={value.outcome} onChange={(e) => onChange({ outcome: e.target.value as FiltersValue["outcome"] })}>
          <option value="ALL">W/L: All</option>
          <option value="WON">Won</option>
          <option value="LOST">Lost</option>
        </select>
        <input type="date" className="input-field" value={value.dateFrom} onChange={(e) => onChange({ dateFrom: e.target.value })} />
        <input type="date" className="input-field" value={value.dateTo} onChange={(e) => onChange({ dateTo: e.target.value })} />
        <button className="btn-ghost text-xs !py-2 !px-3" onClick={onRefresh}>Refresh</button>
        <button className="btn-ghost text-xs !py-2 !px-3" onClick={clearAll}>Clear</button>
      </div>
      <div className="history-filters-bottom">
        <div className="history-tag-row">
          {TAG_OPTIONS.map((tag) => (
            <button
              key={tag}
              onClick={() => toggleTag(tag)}
              className={`history-tag-chip ${value.tags.includes(tag) ? "history-tag-chip-active" : ""}`}
            >
              {tag}
            </button>
          ))}
        </div>
        <div className="text-[11px] text-slate-500">
          Showing {filteredCount} / {totalCount}
        </div>
      </div>
    </div>
  );
}
