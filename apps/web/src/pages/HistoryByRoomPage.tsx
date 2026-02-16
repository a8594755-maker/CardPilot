import { useEffect, useMemo, useState, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  getHandsByRoom,
  updateHand,
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

  // Mobile nav
  const [mobilePane, setMobilePane] = useState<MobilePane>("rooms");

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

    return hands;
  }, [selectedRoom, handsByRoom, quickFilter, searchQuery]);

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
    <main className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="shrink-0 px-4 py-3 border-b border-white/[0.06] flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {/* Mobile back button */}
          {mobilePane !== "rooms" && (
            <button
              onClick={handleMobileBack}
              className="lg:hidden text-xs px-2 py-1.5 rounded-lg bg-white/5 text-slate-300 border border-white/[0.08] hover:bg-white/10 transition-all min-w-[44px] min-h-[44px] flex items-center justify-center"
            >
              ← Back
            </button>
          )}
          <div>
            <h2 className="text-lg font-bold text-white">Hand History</h2>
            <p className="text-[11px] text-slate-500">
              {rooms.length} room{rooms.length !== 1 ? "s" : ""}
              {selectedRoomData ? ` · ${selectedRoomData.roomName} · ${currentRoomHands.length} hands` : ""}
            </p>
          </div>
        </div>
        <button
          onClick={refresh}
          className="text-[11px] px-3 py-2 rounded-lg bg-white/5 text-slate-400 border border-white/[0.08] hover:bg-white/10 transition-all"
        >
          ↻ Refresh
        </button>
      </div>

      {/* 3-column layout (desktop) / stacked nav (mobile) */}
      <div className="flex-1 min-h-0 overflow-hidden lg:grid lg:grid-cols-[minmax(14rem,clamp(14rem,22vw,18rem))_minmax(18rem,clamp(18rem,30vw,24rem))_minmax(0,1fr)]">
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
          min-w-0 border-r border-white/[0.06] flex flex-col overflow-hidden
          ${mobilePane === "hands" ? "max-lg:flex max-lg:flex-1 max-lg:w-full" : "max-lg:hidden"} lg:flex
        `}>
          {/* Quick filters + search */}
          <div className="shrink-0 px-3 py-2 border-b border-white/[0.06] space-y-2">
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search cards, position, tags..."
              className="w-full text-[11px] bg-slate-800/40 border border-white/[0.08] rounded-lg px-3 py-2 text-slate-300 outline-none focus:border-sky-500/40 placeholder:text-slate-600"
            />
            <div className="flex items-center gap-1 flex-wrap">
              {QUICK_FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setQuickFilter(f.key)}
                  className={`text-[10px] px-2 py-1 rounded-md transition-all ${
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
          flex-1 flex flex-col overflow-hidden min-w-0
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
