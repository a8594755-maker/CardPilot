import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  getHandsByRoom,
  updateHand,
  classifyStartingHandBucket,
  exportHands,
  importHands,
  type HandRecord,
  type LocalRoomSummary,
  type GTOAnalysis,
} from '../lib/hand-history.js';
import type { Socket } from 'socket.io-client';
import { RoomList } from './history/RoomList';
import { HandList2, type HandSort } from './history/HandList2';
import { HandDetail2 } from './history/HandDetail2';
import { HandReplay2 } from './history/HandReplay2';

type DetailTab = 'detail' | 'replay';

/** Quick filter presets for the hands list */
type QuickFilter = 'all' | 'this_week' | 'big_pots' | 'all_in' | 'run_it_twice';

const QUICK_FILTERS: { key: QuickFilter; label: string; icon: string }[] = [
  { key: 'all', label: 'All', icon: '' },
  { key: 'this_week', label: 'This Week', icon: '' },
  { key: 'big_pots', label: 'Big Pots', icon: '' },
  { key: 'all_in', label: 'All-in', icon: '' },
  { key: 'run_it_twice', label: 'RIT', icon: '' },
];

/** Mobile navigation depth: rooms -> hands -> detail */
type MobilePane = 'rooms' | 'hands' | 'detail';

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
  const [detailTab, setDetailTab] = useState<DetailTab>('detail');

  // Filters & sort
  const [quickFilter, setQuickFilter] = useState<QuickFilter>('all');
  const [handSort, setHandSort] = useState<HandSort>('newest');
  const [searchQuery, setSearchQuery] = useState('');
  const [startingHandFilter, setStartingHandFilter] = useState<string>('all');

  // Mobile nav
  const [mobilePane, setMobilePane] = useState<MobilePane>('rooms');

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

  useEffect(() => {
    refresh();
  }, []);

  // Hands for the selected room, with filters applied
  const currentRoomHands = useMemo(() => {
    if (!selectedRoom) return [];
    let hands = handsByRoom[selectedRoom] ?? [];

    // Quick filter
    const now = Date.now();
    const weekAgo = now - 7 * 24 * 60 * 60 * 1000;
    switch (quickFilter) {
      case 'this_week':
        hands = hands.filter((h) => h.createdAt >= weekAgo);
        break;
      case 'big_pots': {
        // Top 20% by pot size within this room
        if (hands.length > 0) {
          const sorted = [...hands].sort((a, b) => b.potSize - a.potSize);
          const cutoff = sorted[Math.floor(sorted.length * 0.2)]?.potSize ?? 0;
          hands = hands.filter((h) => h.potSize >= cutoff);
        }
        break;
      }
      case 'all_in':
        hands = hands.filter((h) => h.tags.includes('all_in'));
        break;
      case 'run_it_twice':
        hands = hands.filter((h) => h.runoutBoards && h.runoutBoards.length > 1);
        break;
    }

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      hands = hands.filter((h) => {
        const haystack = [
          h.heroCards.join(''),
          h.board.join(''),
          h.position,
          h.stakes,
          h.tags.join(' '),
          h.heroName ?? '',
        ]
          .join(' ')
          .toLowerCase();
        return haystack.includes(q);
      });
    }

    if (startingHandFilter !== 'all') {
      hands = hands.filter((h) => {
        const bucket = h.startingHandBucket ?? classifyStartingHandBucket(h.heroCards, h.gameType);
        return bucket === startingHandFilter;
      });
    }

    return hands;
  }, [selectedRoom, handsByRoom, quickFilter, searchQuery, startingHandFilter]);

  const startingHandBuckets = useMemo(() => {
    if (!selectedRoom) return [] as string[];
    const buckets = new Set<string>();
    for (const hand of handsByRoom[selectedRoom] ?? []) {
      buckets.add(
        hand.startingHandBucket ?? classifyStartingHandBucket(hand.heroCards, hand.gameType),
      );
    }
    return [...buckets].sort((a, b) => a.localeCompare(b));
  }, [selectedRoom, handsByRoom]);

  // Session stats
  const sessionStats = useMemo(() => {
    const hands = currentRoomHands;
    if (hands.length === 0) return null;
    const totalNet = hands.reduce((sum, h) => sum + (h.result ?? 0), 0);
    const wins = hands.filter((h) => (h.result ?? 0) > 0).length;
    const losses = hands.filter((h) => (h.result ?? 0) < 0).length;
    const biggestWin = Math.max(...hands.map((h) => h.result ?? 0), 0);
    const biggestLoss = Math.min(...hands.map((h) => h.result ?? 0), 0);
    return { totalNet, wins, losses, biggestWin, biggestLoss, total: hands.length };
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
      navigate('/history', { replace: true });
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
    if (routeHandId) navigate('/history');
    setSelectedRoom(code);
    setSelectedHandId(null);
    setMobilePane('hands');
  };

  const handleSelectHand = (id: string) => {
    setSelectedHandId(id);
    navigate(`/history/${encodeURIComponent(id)}`);
    setMobilePane('detail');
  };

  const onToggleTag = (tag: string) => {
    if (!selectedHand) return;
    const nextTags = selectedHand.tags.includes(tag)
      ? selectedHand.tags.filter((t) => t !== tag)
      : [...selectedHand.tags, tag];
    updateHand(selectedHand.id, { tags: nextTags });
    // Update local state
    setHandsByRoom((prev) => {
      const room = selectedRoom ?? '_local';
      const updated = (prev[room] ?? []).map((h) =>
        h.id === selectedHand.id ? { ...h, tags: nextTags } : h,
      );
      return { ...prev, [room]: updated };
    });
  };

  const onCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* no-op */
    }
  };

  const onDownload = (hand: HandRecord) => {
    const blob = new Blob([JSON.stringify(hand, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cardpilot-hand-${hand.id}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const onSaveAnalysis = useCallback(
    (handId: string, analysis: GTOAnalysis) => {
      updateHand(handId, { gtoAnalysis: analysis });
      setHandsByRoom((prev) => {
        const room = selectedRoom ?? '_local';
        const updated = (prev[room] ?? []).map((h) =>
          h.id === handId ? { ...h, gtoAnalysis: analysis } : h,
        );
        return { ...prev, [room]: updated };
      });
    },
    [selectedRoom],
  );

  // Export all hands as a JSON file download
  const handleExport = useCallback(() => {
    try {
      const json = exportHands();
      const dateStr = new Date().toISOString().slice(0, 10);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `cardpilot-hands-${dateStr}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setStatusMsg({ text: 'Hands exported successfully.', isError: false });
    } catch {
      setStatusMsg({ text: 'Failed to export hands.', isError: true });
    }
  }, []);

  // Import hands from a JSON file
  const handleImportFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const json = reader.result as string;
          const added = importHands(json);
          setStatusMsg({
            text: `Imported ${added} new hand${added !== 1 ? 's' : ''}.`,
            isError: false,
          });
          refresh();
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'Unknown error';
          setStatusMsg({ text: `Import failed: ${msg}`, isError: true });
        }
      };
      reader.onerror = () => {
        setStatusMsg({ text: 'Failed to read file.', isError: true });
      };
      reader.readAsText(file);
      // Reset input so the same file can be re-selected
      e.target.value = '';
    },
    [refresh],
  );

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
    if (mobilePane === 'detail') setMobilePane('hands');
    else if (mobilePane === 'hands') setMobilePane('rooms');
  };

  useEffect(() => {
    if (routeHandId) {
      setMobilePane('detail');
      return;
    }
    setMobilePane(selectedRoom ? 'hands' : 'rooms');
  }, [routeHandId, selectedRoom]);

  const selectedRoomData = rooms.find((r) => r.roomCode === selectedRoom);

  return (
    <main className="cp-history-page flex-1 flex flex-col overflow-hidden max-lg:overflow-y-auto">
      {/* ── Header ── */}
      <div className="cp-history-head shrink-0 px-4 py-2.5 border-b border-white/[0.06] flex items-center justify-between gap-3 bg-[#0a1020]/80 backdrop-blur-md">
        <div className="flex items-center gap-3 min-w-0">
          {/* Mobile back button */}
          {mobilePane !== 'rooms' && (
            <button
              onClick={handleMobileBack}
              className="lg:hidden text-xs px-2.5 py-1.5 rounded-lg bg-white/5 text-slate-300 border border-white/[0.08] hover:bg-white/10 transition-all min-w-[36px] min-h-[32px] flex items-center justify-center"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
          )}
          <div className="min-w-0">
            <h2 className="text-[15px] font-bold text-white truncate leading-tight tracking-tight">
              Hand History
            </h2>
            <p className="text-[11px] text-slate-500 truncate leading-tight mt-0.5">
              {rooms.length} room{rooms.length !== 1 ? 's' : ''}
              {selectedRoomData
                ? ` / ${selectedRoomData.roomName} / ${currentRoomHands.length} hands`
                : ''}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleExport}
            className="cp-history-action-btn text-[10px] px-2.5 py-1.5 rounded-lg bg-white/[0.04] text-slate-400 border border-white/[0.07] hover:bg-white/[0.08] hover:text-slate-200 transition-all min-h-[30px]"
          >
            Export
          </button>
          <button
            onClick={() => importInputRef.current?.click()}
            className="cp-history-action-btn text-[10px] px-2.5 py-1.5 rounded-lg bg-white/[0.04] text-slate-400 border border-white/[0.07] hover:bg-white/[0.08] hover:text-slate-200 transition-all min-h-[30px]"
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
          <button
            onClick={refresh}
            className="cp-history-action-btn text-[10px] px-2.5 py-1.5 rounded-lg bg-white/[0.04] text-slate-400 border border-white/[0.07] hover:bg-white/[0.08] hover:text-slate-200 transition-all min-h-[30px]"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 2v6h-6" />
              <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
              <path d="M3 22v-6h6" />
              <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
            </svg>
          </button>
        </div>
      </div>

      {/* Status message (toast-like) */}
      {statusMsg && (
        <div
          className={`shrink-0 px-4 py-2 text-[11px] font-medium transition-all ${
            statusMsg.isError
              ? 'bg-rose-500/10 text-rose-300 border-b border-rose-500/20'
              : 'bg-emerald-500/10 text-emerald-300 border-b border-emerald-500/20'
          }`}
        >
          {statusMsg.text}
        </div>
      )}

      {/* ── 3-column layout (desktop) / stacked nav (mobile) ── */}
      <div className="flex-1 min-h-0 overflow-hidden max-lg:overflow-y-auto lg:grid lg:grid-cols-[minmax(14rem,clamp(14rem,20vw,17rem))_minmax(18rem,clamp(18rem,28vw,23rem))_minmax(0,1fr)]">
        {/* Column 1: Rooms */}
        <div
          className={`
          min-w-0 border-r border-white/[0.06] flex flex-col overflow-hidden
          ${mobilePane === 'rooms' ? 'max-lg:flex' : 'max-lg:hidden'} lg:flex
        `}
        >
          <div className="shrink-0 px-4 py-2.5 border-b border-white/[0.06]">
            <div className="text-[10px] uppercase tracking-[0.1em] text-slate-500 font-semibold">
              Rooms
            </div>
          </div>
          <RoomList
            rooms={rooms}
            selectedCode={selectedRoom}
            onSelect={handleSelectRoom}
            loading={loading}
          />
        </div>

        {/* Column 2: Hands */}
        <div
          className={`
          min-w-0 border-r border-white/[0.06] flex flex-col overflow-hidden max-lg:overflow-y-auto
          ${mobilePane === 'hands' ? 'max-lg:flex max-lg:flex-1 max-lg:w-full' : 'max-lg:hidden'} lg:flex
        `}
        >
          {/* Filters area */}
          <div className="shrink-0 px-3 py-2 border-b border-white/[0.06] space-y-2">
            {/* Search + Bucket */}
            <div className="flex items-center gap-1.5">
              <div className="relative flex-[1.5] min-w-0">
                <svg
                  className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500"
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.3-4.3" />
                </svg>
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search cards, position..."
                  className="w-full text-[11px] bg-white/[0.04] border border-white/[0.07] rounded-lg pl-7 pr-2.5 py-1.5 text-slate-300 outline-none focus:border-sky-500/40 focus:bg-white/[0.06] placeholder:text-slate-600 transition-all h-[32px]"
                />
              </div>
              <select
                value={startingHandFilter}
                onChange={(e) => setStartingHandFilter(e.target.value)}
                className="flex-1 min-w-0 text-[11px] bg-white/[0.04] border border-white/[0.07] rounded-lg px-2 py-1.5 text-slate-300 outline-none focus:border-sky-500/40 h-[32px] cursor-pointer"
              >
                <option value="all">All Buckets</option>
                {startingHandBuckets.map((bucket) => (
                  <option key={bucket} value={bucket}>
                    {bucket}
                  </option>
                ))}
              </select>
            </div>
            {/* Quick filters */}
            <div className="flex items-center gap-1">
              {QUICK_FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setQuickFilter(f.key)}
                  className={`text-[10px] px-2.5 py-1 rounded-lg transition-all font-medium ${
                    quickFilter === f.key
                      ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30 shadow-sm shadow-sky-500/10'
                      : 'text-slate-500 hover:text-slate-300 border border-transparent hover:border-white/[0.08] hover:bg-white/[0.03]'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Session stats strip */}
          {sessionStats && (
            <div className="shrink-0 px-3 py-2 border-b border-white/[0.06] bg-white/[0.015]">
              <div className="flex items-center gap-3 text-[10px]">
                <span
                  className={`font-bold tabular-nums ${sessionStats.totalNet > 0 ? 'text-emerald-400' : sessionStats.totalNet < 0 ? 'text-red-400' : 'text-slate-400'}`}
                >
                  {sessionStats.totalNet > 0 ? '+' : ''}
                  {sessionStats.totalNet.toLocaleString()}
                </span>
                <span className="text-slate-600">|</span>
                <span className="text-slate-400">
                  <span className="text-emerald-400/70">{sessionStats.wins}W</span>
                  {' / '}
                  <span className="text-red-400/70">{sessionStats.losses}L</span>
                </span>
                <span className="text-slate-600">|</span>
                <span className="text-slate-500">{sessionStats.total} hands</span>
              </div>
            </div>
          )}

          {/* Hands header */}
          <div className="shrink-0 px-4 py-2 border-b border-white/[0.06]">
            <div className="text-[10px] uppercase tracking-[0.1em] text-slate-500 font-semibold">
              Hands{' '}
              {currentRoomHands.length > 0 && (
                <span className="text-slate-600">({currentRoomHands.length})</span>
              )}
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
        <div
          className={`
          flex-1 flex flex-col overflow-hidden min-w-0 max-lg:overflow-y-auto
          ${mobilePane === 'detail' ? 'max-lg:flex' : 'max-lg:hidden'} lg:flex
        `}
        >
          {/* Detail/Replay tabs */}
          <div className="shrink-0 px-4 py-2.5 border-b border-white/[0.06] flex items-center gap-3">
            <div className="inline-flex rounded-lg overflow-hidden border border-white/[0.08]">
              <button
                onClick={() => setDetailTab('detail')}
                className={`text-[11px] font-semibold px-5 py-2 transition-all ${
                  detailTab === 'detail'
                    ? 'bg-gradient-to-r from-cyan-600/70 to-emerald-600/50 text-white shadow-inner'
                    : 'bg-white/[0.03] text-slate-500 hover:text-slate-300 hover:bg-white/[0.06]'
                }`}
              >
                Detail
              </button>
              <button
                onClick={() => setDetailTab('replay')}
                className={`text-[11px] font-semibold px-5 py-2 transition-all ${
                  detailTab === 'replay'
                    ? 'bg-gradient-to-r from-cyan-600/70 to-emerald-600/50 text-white shadow-inner'
                    : 'bg-white/[0.03] text-slate-500 hover:text-slate-300 hover:bg-white/[0.06]'
                }`}
              >
                Replay
              </button>
            </div>
            {selectedHand && (
              <span className="text-[10px] text-slate-500 ml-1 truncate">
                {selectedHand.heroCards.join(' ')} / {selectedHand.position} / {selectedHand.stakes}
              </span>
            )}
          </div>
          {/* Content */}
          {loading ? (
            <div className="flex-1 p-3 space-y-3">
              {Array.from({ length: 6 }).map((_, idx) => (
                <div
                  key={idx}
                  className="animate-pulse min-h-[56px] rounded-xl border border-white/[0.06] bg-white/[0.03]"
                />
              ))}
            </div>
          ) : detailTab === 'detail' ? (
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
