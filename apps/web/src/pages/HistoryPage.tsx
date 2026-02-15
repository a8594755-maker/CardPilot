import { useEffect, useMemo, useState } from "react";
import { getHands, updateHand, type HandRecord } from "../lib/hand-history.js";
import { FiltersBar } from "./history/FiltersBar";
import { HandList } from "./history/HandList";
import { HandDetail } from "./history/HandDetail";
import { HandReplay } from "./history/HandReplay";

type HistoryTab = "detail" | "replay";

function normalizeCardQuery(input: string): string[] {
  const cleaned = input.replace(/\s+/g, "").trim();
  if (cleaned.length < 4) return [];
  const chunks: string[] = [];
  for (let i = 0; i + 1 < cleaned.length; i += 2) {
    chunks.push(cleaned.slice(i, i + 2));
  }
  return chunks;
}

export function HistoryPage() {
  const [hands, setHands] = useState<HandRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<HistoryTab>("detail");
  const [filters, setFilters] = useState({
    tags: [] as string[],
    position: "ALL",
    outcome: "ALL" as "ALL" | "WON" | "LOST",
    dateFrom: "",
    dateTo: "",
    query: "",
  });

  const refresh = () => {
    setLoading(true);
    const records = getHands();
    setHands(records);
    setLoading(false);
  };

  useEffect(() => {
    refresh();
  }, []);

  const filteredHands = useMemo(() => {
    const q = filters.query.trim().toLowerCase();
    let next = hands.filter((h) => {
      if (filters.position !== "ALL" && h.position !== filters.position) return false;
      if (filters.tags.length > 0 && !filters.tags.every((t) => h.tags.includes(t))) return false;
      if (filters.outcome === "WON" && (h.result ?? 0) <= 0) return false;
      if (filters.outcome === "LOST" && (h.result ?? 0) >= 0) return false;
      if (filters.dateFrom) {
        const fromTs = new Date(`${filters.dateFrom}T00:00:00`).getTime();
        if (h.createdAt < fromTs) return false;
      }
      if (filters.dateTo) {
        const toTs = new Date(`${filters.dateTo}T23:59:59`).getTime();
        if (h.createdAt > toTs) return false;
      }

      if (!q) return true;

      if (q.startsWith("board:")) {
        const cards = normalizeCardQuery(q.slice("board:".length));
        if (cards.length === 0) return false;
        return cards.every((c) => h.board.join("").toLowerCase().includes(c));
      }

      const cardQuery = normalizeCardQuery(q);
      if (cardQuery.length >= 2) {
        const heroJoined = h.heroCards.join("").toLowerCase();
        return cardQuery.every((c) => heroJoined.includes(c));
      }

      const haystack = [h.stakes, h.position, h.heroCards.join(" "), h.board.join(" "), h.tags.join(" ")].join(" ").toLowerCase();
      return haystack.includes(q);
    });

    next = next.sort((a, b) => b.createdAt - a.createdAt);
    return next;
  }, [filters, hands]);

  useEffect(() => {
    if (!filteredHands.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filteredHands.some((h) => h.id === selectedId)) {
      setSelectedId(filteredHands[0].id);
    }
  }, [filteredHands, selectedId]);

  const selectedHand = useMemo(() => filteredHands.find((h) => h.id === selectedId) ?? null, [filteredHands, selectedId]);
  const positions = useMemo(() => Array.from(new Set(hands.map((h) => h.position).filter(Boolean))), [hands]);

  const onToggleTag = (tag: string) => {
    if (!selectedHand) return;
    const nextTags = selectedHand.tags.includes(tag)
      ? selectedHand.tags.filter((t) => t !== tag)
      : [...selectedHand.tags, tag];
    updateHand(selectedHand.id, { tags: nextTags });
    setHands((curr) => curr.map((h) => (h.id === selectedHand.id ? { ...h, tags: nextTags } : h)));
  };

  const onCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // no-op fallback
    }
  };

  const onDownload = (hand: HandRecord) => {
    const blob = new Blob([JSON.stringify(hand, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `cardpilot-hand-${hand.id}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="flex-1 p-2 sm:p-4 overflow-hidden">
      <div className="history-layout glass-card h-full p-3 sm:p-4 gap-3">
        <div className="history-header">
          <div>
            <h2 className="text-xl font-bold text-white">Hand History</h2>
            <p className="text-xs text-slate-500">Poker-client style review with filters, detail, and replay.</p>
          </div>
        </div>

        <FiltersBar
          value={filters}
          onChange={(patch) => setFilters((curr) => ({ ...curr, ...patch }))}
          positions={positions}
          totalCount={hands.length}
          filteredCount={filteredHands.length}
          onRefresh={refresh}
        />

        <div className="history-three-pane">
          <section className="history-pane history-pane-list">
            <div className="history-pane-title">Hands</div>
            <HandList hands={filteredHands} selectedId={selectedId} loading={loading} onSelect={setSelectedId} />
          </section>

          <section className="history-pane history-pane-detail">
            <div className="history-detail-tabs">
              <button className={`history-tab ${tab === "detail" ? "history-tab-active" : ""}`} onClick={() => setTab("detail")}>Detail</button>
              <button className={`history-tab ${tab === "replay" ? "history-tab-active" : ""}`} onClick={() => setTab("replay")}>Replay</button>
            </div>
            {tab === "detail" ? (
              <HandDetail hand={selectedHand} onCopy={onCopy} onDownload={onDownload} onToggleTag={onToggleTag} />
            ) : (
              <HandReplay hand={selectedHand} />
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
