import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  getHandsByRoom,
  updateHand,
  classifyStartingHandBucket,
  exportHands,
  importHands,
  type HandRecord,
  type LocalRoomSummary,
  type GTOAnalysis,
} from "../lib/hand-history.js";
import type { Socket } from "socket.io-client";
import { RoomList } from "./history/RoomList";
import { HandList2, type HandSort } from "./history/HandList2";
import { HandDetail2 } from "./history/HandDetail2";
import { HandReplay2 } from "./history/HandReplay2";

type DetailTab = "detail" | "replay";

/** Quick filter presets for the hands list */
type QuickFilter = "all" | "this_week" | "big_pots" | "all_in" | "run_it_twice";

const QUICK_FILTERS: { key: QuickFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "this_week", label: "This Week" },
  { key: "big_pots", label: "Big Pots" },
  { key: "all_in", label: "All-in" },
  { key: "run_it_twice", label: "Run It Twice" },
];

/** Mobile navigation depth: rooms -> hands -> detail */
type MobilePane = "rooms" | "hands" | "detail";

export function HistoryByRoomPage(_props: {
  socket?: Socket | null;
  isConnected?: boolean;
  userId?: string;
  supabaseEnabled?: boolean;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const routeHandId = useMemo(() => {
    const match = location.pathname.match(/^\/history\/([^/]+)$/);
    return match ? decodeURIComponent(match[1]) : null;
  }, [location.pathname]);

  // Data
  const [rooms, setRooms] = useState<LocalRoomSummary[]>([]);
  const [handsByRoom, setHandsByRoom] = useState<Record<string, HandRecord[]>>({});
  const [loading, setLoading] = useState(true);

  // Selection
  const [selectedRoom, setSelectedRoom] = useState<string | null>(null);
  const [selectedHandId, setSelectedHandId] = useState<string | null>(routeHandId ?? null);
  const [detailTab, setDetailTab] = useState<DetailTab>("detail");

  // Filters & sort
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("all");
  const [handSort, setHandSort] = useState<HandSort>("newest");
  const [searchQuery, setSearchQuery] = useState("");
  const [startingHandFilter, setStartingHandFilter] = useState<string>("all");

  // Mobile nav
  const [mobilePane, setMobilePane] = useState<MobilePane>("rooms");

  // Import / export
  const importInputRef = useRef<HTMLInputElement>(null);
  const [statusMsg, setStatusMsg] = useState<{ text: string; isError: boolean } | null>(null);

  // Load data from localStorage
  const refresh = useCallback(() => {
    setLoading(true);
    try {
      const data = getHandsByRoom();
      setRooms(data.rooms);
      setHandsByRoom(data.handsByRoom);
      // Auto-select first room if none selected
      if (!selectedRoom && data.rooms.length > 0) {
        setSelectedRoom(data.rooms[0].roomCode);
      }
    } catch {
      // localStorage read failure — show empty state
      setRooms([]);
      setHandsByRoom({});
    }
    setLoading(false);
  }, [selectedRoom]);

  useEffect(() => { refresh(); }, []);

  // Hands for the selected room, with filters applied
  const currentRoomHands = useMemo(() => {
    if (!selectedRoom) return [];
    let hands = handsByRoom[selectedRoom] ?? [];

    // Quick filter
    const now = Date.now();
    const weekAgo = now - 7 * 24 * 60 * 60 * 1000;
    switch (quickFilter) {
      case "this_week":
        hands = hands.filter((h) => h.createdAt >= weekAgo);
        break;
      case "big_pots": {
        // Top 20% by pot size within this room
        if (hands.length > 0) {
          const sorted = [...hands].sort((a, b) => b.potSize - a.potSize);
          const cutoff = sorted[Math.floor(sorted.length * 0.2)]?.potSize ?? 0;
          hands = hands.filter((h) => h.potSize >= cutoff);
        }
        break;
      }
      case "all_in":
        hands = hands.filter((h) => h.tags.includes("all_in"));
        break;
      case "run_it_twice":
        hands = hands.filter((h) => h.runoutBoards && h.runoutBoards.length > 1);
        break;
    }

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      hands = hands.filter((h) => {
        const haystack = [
          h.heroCards.join(""),
          h.board.join(""),
          h.position,
          h.stakes,
          h.tags.join(" "),
          h.heroName ?? "",
        ].join(" ").toLowerCase();
        return haystack.includes(q);
      });
    }

    if (startingHandFilter !== "all") {
      hands = hands.filter((h) => {
        const bucket = h.startingHandBucket
          ?? classifyStartingHandBucket(h.heroCards, h.gameType);
        return bucket === startingHandFilter;
      });
    }

    return hands;
  }, [selectedRoom, handsByRoom, quickFilter, searchQuery, startingHandFilter]);

  const startingHandBuckets = useMemo(() => {
    if (!selectedRoom) return [] as string[];
    const buckets = new Set<string>();
    for (const hand of handsByRoom[selectedRoom] ?? []) {
      buckets.add(hand.startingHandBucket ?? classifyStartingHandBucket(hand.heroCards, hand.gameType));
    }
    return [...buckets].sort((a, b) => a.localeCompare(b));
  }, [selectedRoom, handsByRoom]);

  const positionSummary = useMemo(() => {
    const totals = new Map<string, number>();
    for (const hand of currentRoomHands) {
      const position = hand.position || "Unknown";
      totals.set(position, (totals.get(position) ?? 0) + (hand.result ?? 0));
    }
    return [...totals.entries()]
      .map(([position, net]) => ({ position, net }))
      .sort((a, b) => b.net - a.net);
  }, [currentRoomHands]);

  // Selected hand object
  const selectedHand = useMemo(() => {
    if (!selectedHandId) return null;
    return currentRoomHands.find((h) => h.id === selectedHandId) ?? null;
  }, [currentRoomHands, selectedHandId]);

  // Auto-select first hand when room changes
  useEffect(() => {
    if (!routeHandId) {
      setSelectedHandId(null);
      return;
    }

    if (currentRoomHands.length > 0 && !currentRoomHands.some((h) => h.id === routeHandId)) {
      navigate("/history", { replace: true });
    }
  }, [currentRoomHands, routeHandId, navigate]);

  useEffect(() => {
    setSelectedHandId(routeHandId ?? null);
  }, [routeHandId]);

  useEffect(() => {
    if (!routeHandId) return;
    if (selectedRoom && (handsByRoom[selectedRoom] ?? []).some((h) => h.id === routeHandId)) return;

    for (const [roomCode, hands] of Object.entries(handsByRoom)) {
      if (hands.some((h) => h.id === routeHandId)) {
        setSelectedRoom(roomCode);
        return;
      }
    }
  }, [routeHandId, handsByRoom, selectedRoom]);

  // Handlers
  const handleSelectRoom = (code: string) => {
    if (routeHandId) navigate("/history");
    setSelectedRoom(code);
    setSelectedHandId(null);
    setMobilePane("hands");
  };

  const handleSelectHand = (id: string) => {
    setSelectedHandId(id);
    navigate(`/history/${encodeURIComponent(id)}`);
    setMobilePane("detail");
  };

  const onToggleTag = (tag: string) => {
    if (!selectedHand) return;
    const nextTags = selectedHand.tags.includes(tag)
      ? selectedHand.tags.filter((t) => t !== tag)
      : [...selectedHand.tags, tag];
    updateHand(selectedHand.id, { tags: nextTags });
    // Update local state
    setHandsByRoom((prev) => {
      const room = selectedRoom ?? "_local";
      const updated = (prev[room] ?? []).map((h) =>
        h.id === selectedHand.id ? { ...h, tags: nextTags } : h
      );
      return { ...prev, [room]: updated };
    });
  };

  const onCopy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); } catch { /* no-op */ }
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

  const onSaveAnalysis = useCallback((handId: string, analysis: GTOAnalysis) => {
    updateHand(handId, { gtoAnalysis: analysis });
    setHandsByRoom((prev) => {
      const room = selectedRoom ?? "_local";
      const updated = (prev[room] ?? []).map((h) =>
        h.id === handId ? { ...h, gtoAnalysis: analysis } : h
      );
      return { ...prev, [room]: updated };
    });
  }, [selectedRoom]);

  // Export all hands as a JSON file download
  const handleExport = useCallback(() => {
    try {
      const json = exportHands();
      const dateStr = new Date().toISOString().slice(0, 10);
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cardpilot-hands-${dateStr}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setStatusMsg({ text: "Hands exported successfully.", isError: false });
    } catch {
      setStatusMsg({ text: "Failed to export hands.", isError: true });
    }
  }, []);

  // Import hands from a JSON file
  const handleImportFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const json = reader.result as string;
        const added = importHands(json);
        setStatusMsg({ text: `Imported ${added} new hand${added !== 1 ? "s" : ""}.`, isError: false });
        refresh();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setStatusMsg({ text: `Import failed: ${msg}`, isError: true });
      }
    };
    reader.onerror = () => {
      setStatusMsg({ text: "Failed to read file.", isError: true });
    };
    reader.readAsText(file);
    // Reset input so the same file can be re-selected
    e.target.value = "";
  }, [refresh]);

  // Auto-dismiss status message after 5 seconds
  useEffect(() => {
    if (!statusMsg) return;
    const timer = setTimeout(() => setStatusMsg(null), 5000);
    return () => clearTimeout(timer);
  }, [statusMsg]);

  // Mobile back handler
  const handleMobileBack = () => {
    if (routeHandId) {
      navigate(-1);
      return;
    }
    if (mobilePane === "detail") setMobilePane("hands");
    else if (mobilePane === "hands") setMobilePane("rooms");
  };

  useEffect(() => {
    if (routeHandId) {
      setMobilePane("detail");
      return;
    }
    setMobilePane(selectedRoom ? "hands" : "rooms");
  }, [routeHandId, selectedRoom]);

  const selectedRoomData = rooms.find((r) => r.roomCode === selectedRoom);

  return (
    <main className="history-page flex-1 flex flex-col overflow-hidden max-lg:overflow-y-auto">
      {/* Header */}
      <div className="history-head shrink-0 px-2.5 py-1.5 border-b border-white/[0.06] flex items-center justify-between gap-1.5">
        <div className="flex items-center gap-1.5 min-w-0">
          {/* Mobile back button */}
          {mobilePane !== "rooms" && (
            <button
              onClick={handleMobileBack}
              className="history-back-btn lg:hidden text-[9px] px-1.5 py-1 rounded-md bg-white/5 text-slate-300 border border-white/[0.08] hover:bg-white/10 transition-all min-w-[32px] min-h-[30px] flex items-center justify-center"
            >
              ← Back
            </button>
          )}
          <div className="min-w-0">
            <h2 className="text-[14px] font-bold text-white truncate leading-tight">Hand History</h2>
            <p className="text-[10px] text-slate-500 truncate leading-tight">
              {rooms.length} room{rooms.length !== 1 ? "s" : ""}
              {selectedRoomData ? ` · ${selectedRoomData.roomName} · ${currentRoomHands.length} hands` : ""}
            </p>
          </div>
        </div>
        <button
          onClick={refresh}
          className="history-refresh-btn text-[9px] px-2 py-1 rounded-md bg-white/5 text-slate-400 border border-white/[0.08] hover:bg-white/10 transition-all shrink-0 min-h-[30px]"
        >
          ↻ Refresh
        </button>
      </div>

      {/* Info banner — local storage notice + export/import */}
      <div className="shrink-0 px-2.5 py-1.5 border-b border-white/[0.06] bg-slate-800/30 flex items-center justify-between gap-2 flex-wrap">
        <span className="text-[10px] text-slate-400 leading-tight">
          Stored locally on this device. 30-day retention, max 500 hands.
        </span>
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleExport}
            className="text-[9px] px-2 py-1 rounded-md bg-white/5 text-slate-400 border border-white/[0.08] hover:bg-white/10 transition-all min-h-[26px]"
          >
            Export All
          </button>
          <button
            onClick={() => importInputRef.current?.click()}
            className="text-[9px] px-2 py-1 rounded-md bg-white/5 text-slate-400 border border-white/[0.08] hover:bg-white/10 transition-all min-h-[26px]"
          >
            Import
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept=".json,application/json"
            onChange={handleImportFile}
            className="hidden"
          />
        </div>
      </div>

      {/* Status message (toast-like) */}
      {statusMsg && (
        <div className={`shrink-0 px-2.5 py-1 border-b border-white/[0.06] text-[10px] ${
          statusMsg.isError
            ? "bg-rose-500/10 text-rose-300 border-rose-500/20"
            : "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
        }`}>
          {statusMsg.text}
        </div>
      )}

      {/* 3-column layout (desktop) / stacked nav (mobile) */}
      <div className="flex-1 min-h-0 overflow-hidden max-lg:overflow-y-auto lg:grid lg:grid-cols-[minmax(14rem,clamp(14rem,22vw,18rem))_minmax(18rem,clamp(18rem,30vw,24rem))_minmax(0,1fr)]">
        {/* Column 1: Rooms */}
        <div className={`
          min-w-0 border-r border-white/[0.06] flex flex-col overflow-hidden
          ${mobilePane === "rooms" ? "max-lg:flex" : "max-lg:hidden"} lg:flex
        `}>
          <div className="shrink-0 px-3 py-2 border-b border-white/[0.06]">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Rooms</div>
          </div>
          <RoomList
            rooms={rooms}
            selectedCode={selectedRoom}
            onSelect={handleSelectRoom}
            loading={loading}
          />
        </div>

        {/* Column 2: Hands */}
        <div className={`
          min-w-0 border-r border-white/[0.06] flex flex-col overflow-hidden max-lg:overflow-y-auto
          ${mobilePane === "hands" ? "max-lg:flex max-lg:flex-1 max-lg:w-full" : "max-lg:hidden"} lg:flex
        `}>
          {/* Quick filters + search */}
          <div className="shrink-0 px-2.5 py-1.5 border-b border-white/[0.06] space-y-1.5">
            <div className="history-search-bucket-row flex items-center gap-1">
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search cards, position, tags..."
                className="history-search-input flex-[1.45] min-w-0 text-[10px] bg-slate-800/40 border border-white/[0.08] rounded-md px-2 py-1 text-slate-300 outline-none focus:border-sky-500/40 placeholder:text-slate-600 placeholder:text-[10px] h-[34px]"
              />
              <label className="text-[9px] uppercase tracking-wider text-slate-500 font-semibold shrink-0">Bucket</label>
              <select
                value={startingHandFilter}
                onChange={(e) => setStartingHandFilter(e.target.value)}
                className="history-bucket-select flex-1 min-w-0 text-[10px] bg-slate-800/40 border border-white/[0.08] rounded-md px-2 py-1 text-slate-300 outline-none focus:border-sky-500/40 h-[34px]"
              >
                <option value="all" className="history-bucket-option">All buckets</option>
                {startingHandBuckets.map((bucket) => (
                  <option key={bucket} value={bucket} className="history-bucket-option">{bucket}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-1 flex-wrap">
              {QUICK_FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setQuickFilter(f.key)}
                  className={`text-[10px] px-2 py-0.5 rounded-md transition-all ${
                    quickFilter === f.key
                      ? "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                      : "text-slate-500 hover:text-slate-300 border border-transparent hover:border-white/[0.08]"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div className="shrink-0 px-3 py-1.5 border-b border-white/[0.06]">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
              Hands {currentRoomHands.length > 0 && <span className="text-slate-600">({currentRoomHands.length})</span>}
            </div>
            {positionSummary.length > 0 && (
              <div className="mt-1 flex items-center gap-1.5 flex-wrap">
                {positionSummary.slice(0, 5).map((entry) => (
                  <span
                    key={entry.position}
                    className={`text-[9px] px-1.5 py-0.5 rounded-full border ${
                      entry.net > 0
                        ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                        : entry.net < 0
                          ? "bg-rose-500/10 text-rose-300 border-rose-500/30"
                          : "bg-slate-700/40 text-slate-400 border-white/[0.08]"
                    }`}
                  >
                    {entry.position} {entry.net > 0 ? "+" : ""}{entry.net.toLocaleString()}
                  </span>
                ))}
              </div>
            )}
          </div>
          <HandList2
            hands={currentRoomHands}
            selectedId={selectedHandId}
            loading={loading}
            onSelect={handleSelectHand}
            sort={handSort}
            onSortChange={setHandSort}
          />
        </div>

        {/* Column 3: Detail / Replay */}
        <div className={`
          flex-1 flex flex-col overflow-hidden min-w-0 max-lg:overflow-y-auto
          ${mobilePane === "detail" ? "max-lg:flex" : "max-lg:hidden"} lg:flex
        `}>
          {/* Detail/Replay tabs */}
          <div className="shrink-0 px-3 py-2 border-b border-white/[0.06] flex items-center gap-2">
            <div className="inline-flex rounded-lg border border-white/[0.08] overflow-hidden">
              <button
                onClick={() => setDetailTab("detail")}
                className={`text-[11px] font-semibold px-4 py-2 transition-all ${
                  detailTab === "detail"
                    ? "bg-gradient-to-r from-cyan-600/80 to-emerald-600/60 text-white"
                    : "bg-slate-800/40 text-slate-400 hover:text-slate-200"
                }`}
              >
                Detail
              </button>
              <button
                onClick={() => setDetailTab("replay")}
                className={`text-[11px] font-semibold px-4 py-2 transition-all ${
                  detailTab === "replay"
                    ? "bg-gradient-to-r from-cyan-600/80 to-emerald-600/60 text-white"
                    : "bg-slate-800/40 text-slate-400 hover:text-slate-200"
                }`}
              >
                Replay
              </button>
            </div>
            {selectedHand && (
              <span className="text-[10px] text-slate-500 ml-2 truncate">
                {selectedHand.heroCards.join(" ")} · {selectedHand.position} · {selectedHand.stakes}
              </span>
            )}
          </div>
          {/* Content */}
          {loading ? (
            <div className="flex-1 p-3 space-y-3">
              {Array.from({ length: 6 }).map((_, idx) => (
                <div key={idx} className="animate-pulse min-h-[56px] rounded-lg border border-white/[0.06] bg-white/[0.03]" />
              ))}
            </div>
          ) : detailTab === "detail" ? (
            <HandDetail2
              hand={selectedHand}
              onCopy={onCopy}
              onDownload={onDownload}
              onToggleTag={onToggleTag}
              socket={_props.socket}
              onSaveAnalysis={onSaveAnalysis}
            />
          ) : (
            <HandReplay2 hand={selectedHand} />
          )}
        </div>
      </div>
    </main>
  );
}
