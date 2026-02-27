import { useState, useEffect, useCallback } from "react";

// ═══════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════

interface CfrConfig {
  name: string;
  label: string;
  positions: string;
  potType: string;
  stack: string;
  players: number;
  sizes: number;
  solvedFlops: number;
  totalFlops: number;
  progress: number;
  available: boolean;
}

interface FlopEntry {
  boardId: number;
  flopCards: number[];
  flopLabel: string;
  infoSets: number;
  iterations: number;
}

interface StrategyEntry {
  bucket: number;
  probs: number[];
  actions?: string[];
}

const RANKS = "23456789TJQKA";
const SUITS = "cdhs";
const SUIT_SYMBOLS: Record<string, string> = { c: "\u2663", d: "\u2666", h: "\u2665", s: "\u2660" };
const SUIT_COLORS: Record<string, string> = { c: "text-green-400", d: "text-blue-400", h: "text-red-400", s: "text-slate-300" };

function cardLabel(index: number): string {
  const rank = Math.floor(index / 4);
  const suit = index % 4;
  return `${RANKS[rank]}${SUIT_SYMBOLS[SUITS[suit]]}`;
}

function cardColorClass(index: number): string {
  const suit = index % 4;
  return SUIT_COLORS[SUITS[suit]] ?? "text-white";
}

// ═══════════════════════════════════════════════════════════
// API helpers
// ═══════════════════════════════════════════════════════════

const API_BASE = import.meta.env.DEV ? "/api/cfr" : `${import.meta.env.VITE_SERVER_URL || ""}/api/cfr`;

async function fetchConfigs(): Promise<CfrConfig[]> {
  const res = await fetch(`${API_BASE}/configs`);
  const data = await res.json();
  return data.configs ?? [];
}

async function fetchFlops(config: string): Promise<FlopEntry[]> {
  const res = await fetch(`${API_BASE}/flops?config=${encodeURIComponent(config)}`);
  const data = await res.json();
  return data.flops ?? [];
}

async function fetchBoardStrategy(
  config: string, boardId: number, player: number, street: string, history: string
): Promise<StrategyEntry[]> {
  const params = new URLSearchParams({
    config, boardId: String(boardId), player: String(player), street, history,
  });
  const res = await fetch(`${API_BASE}/board-strategy?${params}`);
  const data = await res.json();
  return data.strategies ?? [];
}

// ═══════════════════════════════════════════════════════════
// Components
// ═══════════════════════════════════════════════════════════

function ActionBar({ actions, probs }: { actions: string[]; probs: number[] }) {
  const colors: Record<string, string> = {
    check: "bg-emerald-500",
    call: "bg-emerald-500",
    fold: "bg-slate-500",
    bet_0: "bg-amber-500",
    bet_1: "bg-orange-500",
    bet_2: "bg-red-500",
    raise_0: "bg-amber-500",
    raise_1: "bg-orange-500",
    allin: "bg-red-600",
  };

  const labels: Record<string, string> = {
    check: "Check",
    call: "Call",
    fold: "Fold",
    bet_0: "Bet S",
    bet_1: "Bet M",
    bet_2: "Bet L",
    raise_0: "Raise S",
    raise_1: "Raise L",
    allin: "All-in",
  };

  const total = probs.reduce((a, b) => a + b, 0);
  if (total < 0.001) return <div className="text-slate-500 text-xs">No data</div>;

  return (
    <div className="flex h-5 rounded overflow-hidden gap-px">
      {actions.map((action, i) => {
        const pct = (probs[i] / total) * 100;
        if (pct < 1) return null;
        return (
          <div
            key={action}
            className={`${colors[action] ?? "bg-slate-600"} flex items-center justify-center text-[10px] font-bold text-white`}
            style={{ width: `${pct}%`, minWidth: pct > 5 ? "20px" : "4px" }}
            title={`${labels[action] ?? action}: ${pct.toFixed(1)}%`}
          >
            {pct > 12 ? `${Math.round(pct)}%` : ""}
          </div>
        );
      })}
    </div>
  );
}

function ConfigSelector({
  configs, selected, onSelect
}: { configs: CfrConfig[]; selected: string; onSelect: (name: string) => void }) {
  const grouped = configs.reduce((acc, cfg) => {
    const key = cfg.players > 2 ? "Multi-way (3-player)" : "Heads-Up (2-player)";
    (acc[key] ??= []).push(cfg);
    return acc;
  }, {} as Record<string, CfrConfig[]>);

  return (
    <div className="space-y-3">
      {Object.entries(grouped).map(([group, cfgs]) => (
        <div key={group}>
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">{group}</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {cfgs.map(cfg => (
              <button
                key={cfg.name}
                onClick={() => cfg.available && onSelect(cfg.name)}
                className={`text-left px-3 py-2 rounded-lg text-sm transition-all ${
                  selected === cfg.name
                    ? "bg-amber-500/20 border border-amber-500/40 text-amber-300"
                    : cfg.available
                      ? "bg-white/5 border border-white/10 text-slate-300 hover:bg-white/10"
                      : "bg-white/[0.02] border border-white/5 text-slate-600 cursor-not-allowed"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{cfg.positions} {cfg.potType} {cfg.stack}</span>
                  <span className={`text-xs ${cfg.available ? "text-emerald-400" : "text-slate-600"}`}>
                    {cfg.solvedFlops}/{cfg.totalFlops}
                  </span>
                </div>
                <div className="text-xs text-slate-500 mt-0.5">{cfg.sizes} size{cfg.sizes > 1 ? "s" : ""}/street</div>
                {cfg.available && (
                  <div className="mt-1 h-1 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${cfg.progress}%` }} />
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function FlopGrid({
  flops, selectedBoardId, onSelect
}: { flops: FlopEntry[]; selectedBoardId: number | null; onSelect: (boardId: number) => void }) {
  if (flops.length === 0) {
    return <div className="text-slate-500 text-sm py-4 text-center">No solved flops yet</div>;
  }

  return (
    <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-1 max-h-[300px] overflow-y-auto">
      {flops.map(flop => (
        <button
          key={flop.boardId}
          onClick={() => onSelect(flop.boardId)}
          className={`px-1.5 py-1 rounded text-xs font-mono transition-all ${
            selectedBoardId === flop.boardId
              ? "bg-amber-500/20 border border-amber-500/40 text-white"
              : "bg-white/5 border border-white/10 text-slate-400 hover:bg-white/10"
          }`}
          title={`Board #${flop.boardId} — ${flop.infoSets?.toLocaleString()} info sets`}
        >
          {flop.flopCards.map((c, i) => (
            <span key={i} className={cardColorClass(c)}>{cardLabel(c)}</span>
          ))}
        </button>
      ))}
    </div>
  );
}

function StrategyTable({ strategies, street, history }: {
  strategies: StrategyEntry[];
  street: string;
  history: string;
}) {
  if (strategies.length === 0) {
    return <div className="text-slate-500 text-sm py-4 text-center">No strategies found for this position</div>;
  }

  const actions = strategies[0].actions ?? strategies[0].probs.map((_, i) => `action_${i}`);

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 text-xs text-slate-400 mb-2">
        <span className="font-semibold text-white">{street}</span>
        <span className="text-slate-600">|</span>
        <span>History: <code className="bg-white/10 px-1 rounded">{history || "(root)"}</code></span>
        <span className="text-slate-600">|</span>
        <span>{strategies.length} buckets</span>
      </div>

      {/* Legend */}
      <div className="flex gap-3 text-[10px] text-slate-400 mb-2">
        {actions.map(a => {
          const colors: Record<string, string> = {
            check: "bg-emerald-500", call: "bg-emerald-500", fold: "bg-slate-500",
            bet_0: "bg-amber-500", bet_1: "bg-orange-500", bet_2: "bg-red-500",
            raise_0: "bg-amber-500", raise_1: "bg-orange-500", allin: "bg-red-600",
          };
          return (
            <span key={a} className="flex items-center gap-1">
              <span className={`w-2.5 h-2.5 rounded-sm ${colors[a] ?? "bg-slate-600"}`} />
              {a}
            </span>
          );
        })}
      </div>

      {/* Bucket rows */}
      <div className="space-y-0.5">
        {strategies.map(s => (
          <div key={s.bucket} className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500 w-8 text-right shrink-0">B{s.bucket}</span>
            <div className="flex-1">
              <ActionBar actions={actions} probs={s.probs} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════════════════

export function CfrLookupPage() {
  const [configs, setConfigs] = useState<CfrConfig[]>([]);
  const [selectedConfig, setSelectedConfig] = useState("");
  const [flops, setFlops] = useState<FlopEntry[]>([]);
  const [selectedBoardId, setSelectedBoardId] = useState<number | null>(null);
  const [player, setPlayer] = useState(0);
  const [street, setStreet] = useState("FLOP");
  const [history, setHistory] = useState("");
  const [strategies, setStrategies] = useState<StrategyEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load configs on mount
  useEffect(() => {
    fetchConfigs()
      .then(setConfigs)
      .catch(e => setError(`Failed to load configs: ${e.message}`));
  }, []);

  // Load flops when config changes
  useEffect(() => {
    if (!selectedConfig) { setFlops([]); return; }
    setLoading(true);
    fetchFlops(selectedConfig)
      .then(f => { setFlops(f); setSelectedBoardId(null); setStrategies([]); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedConfig]);

  // Load strategy when board/player/street/history changes
  const loadStrategy = useCallback(() => {
    if (!selectedConfig || selectedBoardId === null) return;
    setLoading(true);
    fetchBoardStrategy(selectedConfig, selectedBoardId, player, street, history)
      .then(setStrategies)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedConfig, selectedBoardId, player, street, history]);

  useEffect(() => { loadStrategy(); }, [loadStrategy]);

  const selectedFlop = flops.find(f => f.boardId === selectedBoardId);
  const numPlayers = configs.find(c => c.name === selectedConfig)?.players ?? 2;

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">CFR Solver Lookup</h1>
        <p className="text-sm text-slate-400 mt-1">
          Browse solved GTO strategies by config, board, and position
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2 text-red-300 text-sm">
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-300 underline">dismiss</button>
        </div>
      )}

      {/* Config Selection */}
      <section>
        <h2 className="text-sm font-semibold text-slate-300 mb-2">Select Config</h2>
        <ConfigSelector configs={configs} selected={selectedConfig} onSelect={setSelectedConfig} />
      </section>

      {/* Flop Selection */}
      {selectedConfig && (
        <section>
          <h2 className="text-sm font-semibold text-slate-300 mb-2">
            Select Flop
            {flops.length > 0 && <span className="text-slate-500 font-normal ml-2">({flops.length} solved)</span>}
          </h2>
          {loading && flops.length === 0 ? (
            <div className="text-slate-500 text-sm">Loading flops...</div>
          ) : (
            <FlopGrid flops={flops} selectedBoardId={selectedBoardId} onSelect={setSelectedBoardId} />
          )}
        </section>
      )}

      {/* Query Controls */}
      {selectedBoardId !== null && selectedFlop && (
        <section className="bg-white/5 rounded-xl p-4 border border-white/10">
          <div className="flex items-center gap-4 flex-wrap">
            {/* Selected board display */}
            <div className="text-lg font-mono">
              {selectedFlop.flopCards.map((c, i) => (
                <span key={i} className={`${cardColorClass(c)} mr-1`}>{cardLabel(c)}</span>
              ))}
            </div>

            {/* Player selector */}
            <div className="flex items-center gap-1">
              <span className="text-xs text-slate-400">Player:</span>
              {Array.from({ length: numPlayers }, (_, i) => (
                <button
                  key={i}
                  onClick={() => setPlayer(i)}
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    player === i ? "bg-amber-500/20 text-amber-300" : "bg-white/5 text-slate-400 hover:text-white"
                  }`}
                >
                  P{i} {i === 0 ? "(OOP)" : i === numPlayers - 1 ? "(IP)" : ""}
                </button>
              ))}
            </div>

            {/* Street selector */}
            <div className="flex items-center gap-1">
              <span className="text-xs text-slate-400">Street:</span>
              {["FLOP", "TURN", "RIVER"].map(s => (
                <button
                  key={s}
                  onClick={() => setStreet(s)}
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    street === s ? "bg-amber-500/20 text-amber-300" : "bg-white/5 text-slate-400 hover:text-white"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>

            {/* History input */}
            <div className="flex items-center gap-1">
              <span className="text-xs text-slate-400">History:</span>
              <input
                type="text"
                value={history}
                onChange={e => setHistory(e.target.value)}
                placeholder="e.g. xb or x1/c"
                className="bg-white/5 border border-white/10 rounded px-2 py-1 text-sm text-white w-32 placeholder:text-slate-600 focus:outline-none focus:border-amber-500/50"
              />
            </div>
          </div>
        </section>
      )}

      {/* Strategy Display */}
      {selectedBoardId !== null && (
        <section>
          <h2 className="text-sm font-semibold text-slate-300 mb-2">Strategy</h2>
          {loading ? (
            <div className="text-slate-500 text-sm">Loading strategies...</div>
          ) : (
            <StrategyTable strategies={strategies} street={street} history={history} />
          )}
        </section>
      )}
    </div>
  );
}
