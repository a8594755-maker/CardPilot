import { useEffect, useMemo, useState, useCallback, useRef, lazy, Suspense } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { ClubListItem, ClubDetailPayload, SessionStatsEntry } from '@cardpilot/shared-types';
import { type AnimationSpeed, loadAnimationSpeed, saveAnimationSpeed } from './lib/chip-animation';
import { debugLog } from './lib/debug';

// Hooks & Contexts
import { useAuth } from './contexts/AuthContext';
import { useSocket } from './contexts/SocketContext';
import { useRoom } from './contexts/RoomContext';
import { useGame } from './contexts/GameContext';
import { useToast } from './contexts/ToastContext';
import { useOverlayManager } from './hooks/useOverlayManager';
import { useIsMobile } from './hooks/useIsMobile';
import { useUserRole } from './hooks/useUserRole';
import { useAuditEvents } from './hooks/useAuditEvents';
import { useFastBattle } from './hooks/useFastBattle';

// Components
import { AuthScreen } from './components/AuthScreen';
import { OnboardingModal } from './components/OnboardingModal';
import { MobileTopBar, MobileMoreMenu } from './components/mobile-nav';
import {
  LeftOptionsRail,
  OptionsDrawer,
  type DrawerSection,
} from './components/ui/LeftOptionsRail';
import { OPTIONS_ITEMS, GROUP_LABELS, type SettingsTab } from './config/optionsMenuItems';
import { ProfilePage } from './pages/ProfilePage';
import { HistoryByRoomPage } from './pages/HistoryByRoomPage';
import { TrainingDashboard } from './pages/TrainingDashboard';
import { FastBattlePage } from './pages/fast-battle/FastBattlePage';
import { FastBattleHUD } from './pages/fast-battle/FastBattleHUD';
import { FastBattleHandResultToast } from './pages/fast-battle/FastBattleHandResultToast';
import { CfrPage } from './pages/cfr/CfrPage';
import { ClubsPage } from './pages/clubs/ClubsPage';
import { Lobby, type CreateRoomSettings } from './components/lobby';
import { TableContainer } from './components/TableContainer';
import { PokerCard } from './components/PokerCard';
import { RoomSettingsPanel } from './components/RoomSettingsPanel';
import { InGameHandHistory } from './components/ui/InGameHandHistory';
import { SessionScoreboard } from './components/ui/SessionScoreboard';
import { FoldConfirmModal } from './components/ui/FoldConfirmModal';
import { BombPotOverlay } from './components/BombPotOverlay';
import { SevenTwoRevealOverlay } from './components/SevenTwoRevealOverlay';
import { BottomActionBar } from './components/ui/BottomActionBar';
import {
  deriveActionBar,
  derivePreActionUI,
  shouldConfirmUnnecessaryFold,
  type PreActionType,
} from './lib/action-derivations';

const SolverWorkspacePage = lazy(() => import('./pages/solver/SolverWorkspacePage'));

const _APP_VERSION = 'v0.4.1';
const _NETLIFY_COMMIT_REF = import.meta.env.VITE_NETLIFY_COMMIT_REF || '';
const _NETLIFY_DEPLOY_ID = import.meta.env.VITE_NETLIFY_DEPLOY_ID || '';
const _BUILD_TIME = new Date().toISOString().slice(0, 16).replace('T', ' ');
const SOUND_PREF_KEY = 'cardpilot_sound_muted';
const RECENT_NON_CLUB_TABLE_KEY = 'cardpilot_recent_non_club_table';

type AppView =
  | 'lobby'
  | 'table'
  | 'profile'
  | 'history'
  | 'clubs'
  | 'training'
  | 'preflop'
  | 'cfr'
  | 'fast-battle'
  | 'solver';

export function AppContent() {
  const navigate = useNavigate();
  const location = useLocation();
  const isMobile = useIsMobile();
  const [isMobilePortrait, setIsMobilePortrait] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(max-width: 768px) and (orientation: portrait) and (pointer: coarse)')
      .matches;
  });

  useEffect(() => {
    const mq = window.matchMedia(
      '(max-width: 768px) and (orientation: portrait) and (pointer: coarse)',
    );
    const handler = (e: MediaQueryListEvent) => setIsMobilePortrait(e.matches);
    setIsMobilePortrait(mq.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // ── Context State ──
  const {
    authSession,
    authLoading,
    displayName,
    userEmail,
    setDisplayName,
    handleLogout: authLogout,
    acceptSession,
    socketAuthUserId: _socketAuthUserId,
  } = useAuth();
  const { socket, connected: socketConnected, reconnecting: socketReconnecting } = useSocket();
  const { lobbyRooms, tableId, setTableId, currentRoomCode, currentRoomName } = useRoom();
  const {
    snapshot,
    roomState,
    seat,
    setSeat: _setSeat,
    holeCards,
    advice,
    deviation: _deviation,
    actionPending: _actionPending,
    setActionPending: _setActionPending,
    winners: _winners,
    settlement: _settlement,
    allInLock: _allInLock,
    myRunPreference: _myRunPreference,
    setMyRunPreference: _setMyRunPreference,
    boardReveal: _boardReveal,
    lastActionBySeat: _lastActionBySeat,
    postHandShowAvailable: _postHandShowAvailable,
    sevenTwoBountyPrompt: _sevenTwoBountyPrompt,
    sevenTwoBountyResult: _sevenTwoBountyResult,
    sevenTwoRevealActive,
    postHandRevealedCards: _postHandRevealedCards,
    bombPotOverlayActive,
    preAction,
    setPreAction,
    snapshotRef: _snapshotRef,
    seatRef: _seatRef,
    holeCardsRef: _holeCardsRef,
  } = useGame();
  const { showToast, toast, toastExiting } = useToast();

  // ── Local State ──
  const [showMoreMenu, setShowMoreMenu] = useState(false);

  // Clubs State
  const [clubList, _setClubList] = useState<ClubListItem[]>([]);
  const [clubDetail, _setClubDetail] = useState<ClubDetailPayload | null>(null);
  const [selectedClubId, setSelectedClubId] = useState<string>('');
  const [clubsLoading, _setClubsLoading] = useState(false);
  const selectedClubIdRef = useRef(selectedClubId);
  useEffect(() => {
    selectedClubIdRef.current = selectedClubId;
  }, [selectedClubId]);

  // Room Management / UI State
  const [createSettings, setCreateSettings] = useState<CreateRoomSettings>({
    sb: 1,
    bb: 3,
    buyInMin: 40,
    buyInMax: 300,
    maxPlayers: 6,
    visibility: 'public',
  });
  const [settingsTab, setSettingsTab] = useState<SettingsTab>('game');
  const [_seatRequests, _setSeatRequests] = useState<
    Array<{ orderId: string; userId: string; userName: string; seat: number; buyIn: number }>
  >([]);
  const [showRoomLog, setShowRoomLog] = useState(false);
  const [showSessionStats, setShowSessionStats] = useState(false);
  const [showInGameHistory, setShowInGameHistory] = useState(false);
  const [sessionStatsData, _setSessionStatsData] = useState<SessionStatsEntry[]>([]);
  const [showRebuyModal, setShowRebuyModal] = useState(false);
  const [rebuyAmount, setRebuyAmount] = useState(0);
  const [_rebuyRequests, _setRebuyRequests] = useState<
    Array<{ orderId: string; userId: string; userName: string; seat: number; amount: number }>
  >([]);
  const [_rejoinStackInfo, _setRejoinStackInfo] = useState<{
    tableId: string;
    stack: number | null;
    loading: boolean;
  } | null>(null);
  const [_revealedZoom, _setRevealedZoom] = useState<{
    seat: number;
    name: string;
    cards: [string, string];
    handName?: string;
  } | null>(null);
  const [_disconnectedSeats, _setDisconnectedSeats] = useState<
    Map<number, { userId: string; graceSeconds: number; disconnectedAt: number }>
  >(new Map());
  const [supabaseEnabled, _setSupabaseEnabled] = useState(true);
  const [showGtoSidebar, setShowGtoSidebar] = useState(() => {
    try {
      return localStorage.getItem('cardpilot_show_gto') !== 'false';
    } catch {
      return true;
    }
  });
  const [_showMobileGto, _setShowMobileGto] = useState(false);
  const [displayBB, setDisplayBB] = useState(false);
  const [showBuyInModal, setShowBuyInModal] = useState(false);
  const [pendingSitSeat, setPendingSitSeat] = useState(1);
  const [buyInAmount, setBuyInAmount] = useState(10000);
  const [clubRoomHintCode, setClubRoomHintCode] = useState('');
  const [raiseTo, setRaiseTo] = useState(0);

  const handleSeatClick = useCallback(
    (seatNum: number) => {
      setPendingSitSeat(seatNum);
      // Default to max buy-in from room settings
      const max = roomState?.settings?.buyInMax ?? 300;
      const min = roomState?.settings?.buyInMin ?? 40;
      setBuyInAmount(Math.min(max, Math.max(min, buyInAmount)));
      setShowBuyInModal(true);
    },
    [roomState?.settings?.buyInMax, roomState?.settings?.buyInMin, buyInAmount],
  );

  // UI Redesign State
  const [showFoldConfirm, setShowFoldConfirm] = useState(false);
  const [suppressFoldConfirm, setSuppressFoldConfirm] = useState(false);

  // Linger State
  const [_lingerActive, _setLingerActive] = useState(false);
  const [_lingerWinnerSeats, _setLingerWinnerSeats] = useState<Set<number>>(new Set());
  const [_lingerSeatDeltas, _setLingerSeatDeltas] = useState<Record<number, number>>({});
  const [_lingerIsAllIn, _setLingerIsAllIn] = useState(false);
  const [_showHandSummaryDrawer, _setShowHandSummaryDrawer] = useState(false);
  const _lingerTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const _resultRunTimersRef = useRef<Array<ReturnType<typeof setTimeout>>>([]);
  const [_winnerSeatPulse, _setWinnerSeatPulse] = useState<number | null>(null);
  const [_resultRunFocus, _setResultRunFocus] = useState<{
    run: 1 | 2 | 3;
    seats: number[];
  } | null>(null);

  // Theme & Sound
  const [tableTheme, setTableTheme] = useState<'green' | 'blue'>(() => {
    try {
      return localStorage.getItem('cardpilot_table_theme') === 'blue' ? 'blue' : 'green';
    } catch {
      return 'green';
    }
  });
  const [soundMuted, setSoundMuted] = useState(() => {
    try {
      return localStorage.getItem(SOUND_PREF_KEY) === 'true';
    } catch {
      return false;
    }
  });
  const [chipAnimSpeed, setChipAnimSpeed] = useState<AnimationSpeed>(loadAnimationSpeed);

  // Refs
  const recentNonClubTableRef = useRef<{
    tableId: string;
    roomCode: string;
    roomName?: string;
  } | null>(null);
  const pathnameRef = useRef(location.pathname);
  useEffect(() => {
    pathnameRef.current = location.pathname;
  }, [location.pathname]);
  const currentRoomCodeRef = useRef(currentRoomCode);
  useEffect(() => {
    currentRoomCodeRef.current = currentRoomCode;
  }, [currentRoomCode]);
  const currentRoomNameRef = useRef(currentRoomName);
  useEffect(() => {
    currentRoomNameRef.current = currentRoomName;
  }, [currentRoomName]);
  const tableIdRef = useRef(tableId);
  useEffect(() => {
    tableIdRef.current = tableId;
  }, [tableId]);

  // Ensure socket joins the room when navigating to a table (e.g. direct URL, reconnect)
  useEffect(() => {
    if (!socket || !tableId || !socketConnected) return;
    // Skip fast-battle tables (handled separately)
    if (tableId.startsWith('fb_')) return;
    socket.emit('join_table', { tableId });
  }, [socket, tableId, socketConnected]);

  // Overlays
  const overlays = useOverlayManager();
  const showOptionsDrawer = overlays.isOpen('optionsDrawer');
  const setShowOptionsDrawer = useCallback(
    (open: boolean) => (open ? overlays.open('optionsDrawer') : overlays.close('optionsDrawer')),
    [overlays],
  );
  const showSettings = overlays.isOpen('roomSettings');
  const setShowSettings = useCallback(
    (open: boolean) => (open ? overlays.open('roomSettings') : overlays.close('roomSettings')),
    [overlays],
  );

  // Hooks
  const auditState = useAuditEvents(socket, authSession?.userId ?? null);
  const fastBattle = useFastBattle(socket, authSession?.userId ?? null);
  const userRole = useUserRole(roomState, authSession?.userId, seat);

  // Derived View
  const view = useMemo<AppView>(() => {
    const path = location.pathname;
    if (path === '/' || path.startsWith('/lobby')) return 'lobby';
    if (path.startsWith('/fast-battle')) return 'fast-battle';
    if (path.startsWith('/solver')) return 'solver';
    if (path.startsWith('/table')) return 'table';
    if (path.startsWith('/history')) return 'history';
    if (path.startsWith('/clubs')) return 'clubs';
    if (path.startsWith('/training')) return 'training';
    if (path.startsWith('/preflop')) return 'preflop';
    if (path.startsWith('/cfr')) return 'cfr';
    if (path.startsWith('/profile')) return 'profile';
    return 'lobby';
  }, [location.pathname]);

  const canAccessClubs = Boolean(authSession && !authSession.isGuest);
  const isFastBattlePlaying = fastBattle.phase === 'playing' || fastBattle.phase === 'switching';
  const isConnected = socketConnected;

  // Nav Helpers
  const goToTable = useCallback(
    (nextTableId?: string, replace = false) => {
      const resolvedTableId = (nextTableId ?? tableId ?? 'table-1').trim() || 'table-1';
      navigate(`/table/${encodeURIComponent(resolvedTableId)}`, { replace });
    },
    [navigate, tableId],
  );

  const quickJoinNonClub = useCallback(
    (trigger: 'table_tab' | 'quick_play') => {
      if (!socket) {
        showToast('Not connected to server');
        return;
      }
      const openRoom = lobbyRooms.find(
        (r) => r.status === 'OPEN' && r.playerCount < r.maxPlayers && !r.isClubTable,
      );
      if (openRoom) {
        setClubRoomHintCode('');
        goToTable(openRoom.tableId || 'table-1');
        socket.emit('join_room_code', { roomCode: openRoom.roomCode });
        showToast(
          trigger === 'table_tab' ? 'Joining quick table...' : 'Quick-matching into room...',
        );
        return;
      }
      // Fallback create
      debugLog('[CREATE_ROOM] table-tab fallback create_room', {
        clientUserId: authSession?.userId,
      });
      goToTable('table-1');
      socket.emit('create_room', {
        roomName: `${createSettings.sb}/${createSettings.bb} NLH`,
        maxPlayers: createSettings.maxPlayers,
        smallBlind: createSettings.sb,
        bigBlind: createSettings.bb,
        buyInMin: createSettings.buyInMin,
        buyInMax: createSettings.buyInMax,
        visibility: 'public',
      });
      showToast('Creating new table...');
    },
    [socket, lobbyRooms, createSettings, authSession?.userId, goToTable, showToast],
  );

  const setView = useCallback(
    (nextView: AppView) => {
      if (nextView === 'table') {
        const isCurrentRoomClub = Boolean(currentRoomCode && currentRoomCode === clubRoomHintCode);
        const hasActiveNonClubRoom = Boolean(tableId && currentRoomCode && !isCurrentRoomClub);
        if (hasActiveNonClubRoom) {
          goToTable(tableId ?? undefined);
          return;
        }
        const recent = recentNonClubTableRef.current;
        if (recent?.roomCode) {
          setClubRoomHintCode('');
          goToTable(recent.tableId || 'table-1');
          if (socket) {
            socket.emit('join_room_code', { roomCode: recent.roomCode });
            showToast(`Returning to ${recent.roomName || recent.roomCode}...`);
          }
          return;
        }
        quickJoinNonClub('table_tab');
        return;
      }
      if (nextView === 'lobby') {
        navigate('/lobby');
        return;
      }
      navigate(`/${nextView}`);
    },
    [
      goToTable,
      navigate,
      location.pathname,
      tableId,
      currentRoomCode,
      clubRoomHintCode,
      socket,
      quickJoinNonClub,
      showToast,
    ],
  );

  // Effects
  useEffect(() => {
    try {
      const raw = localStorage.getItem(RECENT_NON_CLUB_TABLE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.tableId) recentNonClubTableRef.current = parsed;
      }
    } catch {}
  }, []);

  useEffect(() => {
    if (location.pathname === '/') {
      navigate('/lobby', { replace: true });
      return;
    }
    if (location.pathname.startsWith('/clubs/')) {
      navigate('/clubs', { replace: true });
      return;
    }
    if (location.pathname === '/table') {
      goToTable(undefined, true);
      return;
    }
    const tableMatch = location.pathname.match(/^\/table\/([^/]+)$/);
    if (tableMatch) {
      const routeTableId = decodeURIComponent(tableMatch[1]);
      if (routeTableId && routeTableId !== tableId && pathnameRef.current.startsWith('/table')) {
        setTableId(routeTableId);
      }
      return;
    }
    const supportedPaths = [
      '/lobby',
      '/history',
      '/profile',
      '/training',
      '/preflop',
      '/cfr',
      '/fast-battle',
      '/solver',
    ];
    if (
      !(
        location.pathname.startsWith('/clubs') ||
        location.pathname.startsWith('/history/') ||
        supportedPaths.includes(location.pathname)
      )
    ) {
      navigate('/lobby', { replace: true });
    }
  }, [goToTable, location.pathname, navigate, tableId]);

  useEffect(() => {
    if (!tableId || !currentRoomCode) return;
    if (roomState?.isClubTable) return;
    if (tableId.startsWith('fb_')) return;
    const recent = { tableId, roomCode: currentRoomCode, roomName: currentRoomName || undefined };
    recentNonClubTableRef.current = recent;
    try {
      localStorage.setItem(RECENT_NON_CLUB_TABLE_KEY, JSON.stringify(recent));
    } catch {}
  }, [tableId, currentRoomCode, currentRoomName, roomState?.isClubTable]);

  useEffect(() => {
    if (fastBattle.phase === 'report' && location.pathname.startsWith('/table')) {
      tableIdRef.current = '';
      currentRoomCodeRef.current = '';
      setTableId('');
      navigate('/fast-battle', { replace: true });
    }
  }, [fastBattle.phase, navigate, location.pathname]);

  // Derived State helpers
  const myPlayer = useMemo(
    () => snapshot?.players.find((p) => p.seat === seat) ?? null,
    [snapshot?.players, seat],
  );
  const handInProgress = useMemo(
    () =>
      roomState?.status === 'PLAYING' ||
      Boolean(
        snapshot?.handId && (snapshot.actorSeat != null || snapshot.showdownPhase === 'decision'),
      ),
    [roomState?.status, snapshot?.handId, snapshot?.actorSeat, snapshot?.showdownPhase],
  );

  const dealDisabledReason = useMemo(() => {
    if (!isConnected) return 'Server disconnected';
    if (!userRole.isHostOrCoHost && seat == null) return 'Sit down to deal';
    if (roomState?.status === 'PAUSED') return 'Game is paused';
    if (handInProgress) return 'Hand in progress';
    const active =
      snapshot?.players.filter((p) => p.status === 'active' && p.stack > 0).length ?? 0;
    const min = Math.max(2, roomState?.settings.minPlayersToStart ?? 2);
    if (active < min) return `Need ${min} players`;
    return null;
  }, [
    isConnected,
    userRole.isHostOrCoHost,
    seat,
    roomState?.status,
    handInProgress,
    snapshot?.players,
    roomState?.settings.minPlayersToStart,
  ]);

  const playerId = authSession?.userId ?? null;

  const derivedActionBarValue = useMemo(
    () => deriveActionBar(snapshot ?? null, playerId),
    [snapshot, playerId],
  );

  const derivedPreActionUIValue = useMemo(
    () => derivePreActionUI(snapshot ?? null, playerId),
    [snapshot, playerId],
  );

  // Actions
  function copyCode() {
    if (!currentRoomCode) return;
    navigator.clipboard.writeText(currentRoomCode);
    showToast(`Copied room code: ${currentRoomCode}`);
  }

  function leaveRoom() {
    debugLog('[nav] leaveRoom()', { tableId, currentRoomCode, seat });
    if (socket && tableId) {
      socket.emit('stand_up', { tableId, seat });
      socket.emit('leave_table', { tableId });
    }
    // Clear refs handled in hook/context, just reset local state
    setTableId('');
    navigate('/lobby');
    showToast('Left room');
    socket?.emit('request_lobby');
  }

  async function handleLogout() {
    overlays.closeAll();
    socket?.disconnect();
    await authLogout();
    // setSnapshot(null); // handled via hook/context reset
    // setHoleCards([]); // handled via hook/context reset
    navigate('/lobby');
    showToast('Signed out');
  }

  const handleAuthSuccess = useCallback(
    (s: any) => {
      acceptSession(s);
      showToast('Signed in');
    },
    [acceptSession, showToast],
  );

  const handleSetPreAction = useCallback(
    (action: PreActionType | null) => {
      if (!action) {
        setPreAction(null);
        return;
      }
      if (!snapshot?.handId || !authSession?.userId) return;
      setPreAction({
        handId: snapshot.handId,
        playerId: authSession.userId,
        actionType: action,
        createdAt: Date.now(),
      });
    },
    [authSession?.userId, setPreAction, snapshot?.handId],
  );

  const [showOnboarding, setShowOnboarding] = useState(() => {
    try {
      return !localStorage.getItem('cardpilot_onboarded');
    } catch {
      return true;
    }
  });
  function completeOnboarding() {
    try {
      localStorage.setItem('cardpilot_onboarded', '1');
    } catch {}
    setShowOnboarding(false);
  }

  // ── Render ──
  if (authLoading)
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-400">Loading...</div>
    );
  if (!authSession) {
    return (
      <AuthScreen
        onAuth={handleAuthSuccess}
        disableGuest={location.pathname.startsWith('/clubs')}
        gateMessage={
          location.pathname.startsWith('/clubs') ? 'Club access requires login.' : undefined
        }
      />
    );
  }
  if (view === 'clubs' && !canAccessClubs) {
    return (
      <AuthScreen
        onAuth={handleAuthSuccess}
        disableGuest
        gateMessage="Club access requires login."
      />
    );
  }

  const PAGE_TITLES: Record<string, string> = {
    lobby: 'Lobby',
    table: 'Table',
    profile: 'Profile',
    history: 'History',
    clubs: 'Clubs',
    training: 'Training',
    cfr: 'GTO Strategy',
    'fast-battle': 'Fast Battle',
  };
  const mobilePageTitle = PAGE_TITLES[view] ?? 'CardPilot';
  const connectionLabel = isConnected
    ? 'Online'
    : socketReconnecting
      ? 'Reconnecting...'
      : 'Offline';

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {showOnboarding && authSession && <OnboardingModal onComplete={completeOnboarding} />}

      {/* Desktop Nav */}
      {view !== 'table' ? (
        <header className="flex items-center justify-between px-4 py-1.5 border-b border-white/5 shrink-0 cp-desktop-only">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-sm font-extrabold text-slate-900 shadow-lg">
              C
            </div>
            <h1 className="text-base font-bold tracking-tight text-white">
              Card<span className="text-amber-400">Pilot</span>
            </h1>
          </div>
          <nav className="flex items-center gap-1 bg-white/5 rounded-xl p-1">
            {(
              [
                'lobby',
                'clubs',
                'table',
                'history',
                'training',
                'fast-battle',
                // 'cfr', // hidden for now
                'profile',
              ] as const
            ).map((v) => (
              <button
                key={v}
                onClick={() => {
                  setView(v);
                  if (v === 'clubs' && socket && canAccessClubs) socket.emit('club_list_my_clubs');
                }}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${view === v ? 'bg-white/10 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'}`}
              >
                {PAGE_TITLES[v] ?? v}
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-medium ${isConnected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-red-400'}`}
              />{' '}
              {connectionLabel}
            </span>
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-[11px] font-bold text-white uppercase">
              {displayName[0]}
            </div>
            <span className="text-xs text-slate-200 font-medium max-w-[140px] truncate">
              Hi, {displayName}
            </span>
            <button
              onClick={handleLogout}
              className="text-xs text-slate-500 hover:text-red-400 transition-colors px-2 py-1 rounded-lg hover:bg-white/5"
            >
              Sign Out
            </button>
          </div>
        </header>
      ) : !isMobilePortrait && !isFastBattlePlaying ? (
        /* Table Top Bar */
        <header className="cp-table-topbar">
          <div className="flex items-center gap-2.5 min-w-0">
            <button onClick={leaveRoom} className="cp-topbar-btn group" title="Exit to Lobby">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-slate-400 group-hover:text-white transition-colors"
              >
                <path d="M15 18l-6-6 6-6" />
              </svg>
              <span className="text-[11px] text-slate-400 group-hover:text-slate-200 transition-colors font-medium">
                Lobby
              </span>
            </button>
            <div className="w-px h-5 bg-white/[0.08]" />
            {currentRoomName && (
              <span className="text-[12px] font-semibold text-white truncate max-w-[200px]">
                {currentRoomName}
              </span>
            )}
            {currentRoomCode && (
              <button
                onClick={copyCode}
                className="cp-topbar-code-btn text-[10px] font-mono text-amber-400/80 tracking-wider hover:text-amber-300 transition-all px-2 py-0.5 rounded-md hover:bg-amber-500/10 border border-transparent hover:border-amber-500/20"
                title="Copy room code"
              >
                {currentRoomCode}
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="inline ml-1 opacity-50"
                >
                  <rect x="9" y="9" width="13" height="13" rx="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              </button>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {roomState && (
              <span className="text-[10px] text-slate-500 font-medium tabular-nums mr-1">
                {roomState.settings.smallBlind}/{roomState.settings.bigBlind}
                <span className="text-slate-600 mx-1">/</span>
                {roomState.settings.maxPlayers}-max
              </span>
            )}
            <div
              className={`cp-topbar-status inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] font-medium ${isConnected ? 'bg-emerald-500/[0.08] text-emerald-400/80 border border-emerald-500/15' : 'bg-red-500/[0.08] text-red-400/80 border border-red-500/15'}`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-red-400 animate-pulse'}`}
              />
              {connectionLabel}
            </div>
            <button
              onClick={() => setShowInGameHistory(true)}
              className="cp-topbar-icon-btn"
              title="Hand History"
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 8v4l3 3" />
                <circle cx="12" cy="12" r="10" />
              </svg>
            </button>
            <button
              onClick={() => setShowOptionsDrawer(!showOptionsDrawer)}
              className="cp-topbar-icon-btn"
              title="Options"
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>
          </div>
        </header>
      ) : null}

      {/* Mobile Top Bar */}
      {isMobile && view !== 'table' && (
        <MobileTopBar
          title={mobilePageTitle}
          isConnected={isConnected}
          onMenuOpen={() => setShowMoreMenu(true)}
          displayName={displayName}
        />
      )}

      {/* Toast */}
      {toast && (
        <div
          className={`fixed z-[100] pointer-events-none ${isMobile ? 'top-[calc(52px+env(safe-area-inset-top,0px))] left-1/2 -translate-x-1/2' : 'bottom-4 left-4'}`}
          role="status"
        >
          <div
            className={`toast ${toast.isError ? 'toast-error' : 'toast-info'} ${toastExiting ? 'toast-exit' : ''}`}
          >
            {toast.text}
          </div>
        </div>
      )}

      {/* Content */}
      <div
        className={`flex-1 flex flex-col overflow-hidden ${isMobile && view !== 'table' ? 'pt-[calc(48px+env(safe-area-inset-top,0px))] pb-[calc(56px+env(safe-area-inset-bottom,0px))]' : ''}`}
      >
        <div className="flex-1 flex overflow-hidden">
          {view === 'profile' ? (
            <ProfilePage
              displayName={displayName}
              setDisplayName={setDisplayName}
              email={userEmail}
              authSession={authSession}
            />
          ) : view === 'history' ? (
            <HistoryByRoomPage
              socket={socket}
              isConnected={isConnected}
              userId={authSession?.userId ?? ''}
              supabaseEnabled={supabaseEnabled}
            />
          ) : view === 'training' ? (
            <TrainingDashboard
              handAudits={auditState.handAudits}
              sessionLeak={auditState.sessionLeak}
              hasData={auditState.hasData}
            />
          ) : view === 'fast-battle' ? (
            <FastBattlePage
              fastBattle={fastBattle}
              onExit={() => {
                fastBattle.resetToSetup();
                navigate('/lobby');
              }}
            />
          ) : view === 'solver' ? (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-screen text-gray-400">
                  Loading Solver...
                </div>
              }
            >
              <SolverWorkspacePage />
            </Suspense>
          ) : view === 'preflop' ? (
            <CfrPage initialMode="preflop" />
          ) : view === 'cfr' ? (
            <CfrPage />
          ) : view === 'clubs' ? (
            <ClubsPage
              socket={socket}
              isConnected={isConnected}
              userId={authSession?.userId ?? ''}
              clubs={clubList}
              clubsLoading={clubsLoading}
              clubDetail={selectedClubId ? clubDetail : null}
              onSelectClub={setSelectedClubId}
              onRefreshClubs={() => socket?.emit('club_list_my_clubs')}
              onJoinClubTable={(clubId, tableId) => {
                if (socket) {
                  setClubRoomHintCode(tableId);
                  socket.emit('club_table_join', { clubId, tableId });
                  setView('table');
                }
              }}
              showToast={showToast}
            />
          ) : view === 'lobby' ? (
            <Lobby
              connected={socketConnected}
              currentRoomCode={tableId?.startsWith('fb_') ? '' : currentRoomCode}
              currentRoomName={tableId?.startsWith('fb_') ? '' : currentRoomName}
              isOwner={roomState?.ownership.ownerId === authSession?.userId}
              lobbyRooms={lobbyRooms}
              createSettings={createSettings}
              onCreateSettingsChange={setCreateSettings}
              onQuickPlay={() => quickJoinNonClub('quick_play')}
              onJoinByCode={(code) => {
                setClubRoomHintCode('');
                socket?.emit('join_room_code', { roomCode: code });
                showToast('Joining room...');
              }}
              onCreateRoom={(s) => {
                if (!socket) {
                  showToast('Not connected');
                  return;
                }
                goToTable('table-1');
                socket.emit('create_room', {
                  roomName: `${s.sb}/${s.bb} NLH`,
                  maxPlayers: s.maxPlayers,
                  smallBlind: s.sb,
                  bigBlind: s.bb,
                  buyInMin: s.buyInMin,
                  buyInMax: s.buyInMax,
                  visibility: s.visibility,
                });
                showToast('Creating room...');
              }}
              onJoinRoom={(code) => {
                setClubRoomHintCode('');
                socket?.emit('join_room_code', { roomCode: code });
                showToast('Joining room...');
              }}
              onRefreshLobby={() => socket?.emit('request_lobby')}
              onCopyCode={copyCode}
              onGoToTable={() => setView('table')}
              onLeaveRoom={leaveRoom}
            />
          ) : (
            /* TABLE VIEW */
            <>
              {isFastBattlePlaying && (
                <FastBattleHUD
                  handsPlayed={fastBattle.handsPlayed}
                  cumulativeResult={fastBattle.cumulativeResult}
                  onEnd={() => fastBattle.endSession()}
                />
              )}
              {isFastBattlePlaying && (
                <FastBattleHandResultToast result={fastBattle.lastHandResult} />
              )}

              {!isMobilePortrait && !isFastBattlePlaying && (
                <LeftOptionsRail
                  drawerOpen={showOptionsDrawer}
                  onOpenDrawer={() => setShowOptionsDrawer(true)}
                  actions={[
                    ...(myPlayer
                      ? [
                          {
                            id: 'away',
                            icon: '💤',
                            label: 'Away',
                            onClick: () =>
                              socket?.emit(
                                myPlayer.status === 'sitting_out' ? 'sit_in' : 'sit_out',
                                { tableId },
                              ),
                            active: myPlayer.status === 'sitting_out',
                          },
                        ]
                      : []),
                    {
                      id: 'leave',
                      icon: '🚪',
                      label: 'Leave',
                      onClick: () => {
                        if (handInProgress && !confirm('Hand in progress. Leave?')) return;
                        leaveRoom();
                      },
                      danger: true,
                      hidden: !myPlayer,
                    },
                    {
                      id: 'theme',
                      icon: tableTheme === 'green' ? '🟢' : '🔵',
                      label: 'Theme',
                      onClick: () => {
                        const next = tableTheme === 'green' ? 'blue' : 'green';
                        setTableTheme(next);
                        localStorage.setItem('cardpilot_table_theme', next);
                      },
                    },
                    {
                      id: 'bb',
                      icon: displayBB ? 'BB' : '$',
                      label: displayBB ? 'Chips' : 'BB',
                      onClick: () => setDisplayBB(!displayBB),
                    },
                  ]}
                />
              )}

              {!isFastBattlePlaying && (
                <OptionsDrawer
                  open={showOptionsDrawer}
                  onClose={() => setShowOptionsDrawer(false)}
                  roomName={currentRoomName || undefined}
                  roomCode={currentRoomCode || undefined}
                  blinds={
                    roomState
                      ? `${roomState.settings.smallBlind}/${roomState.settings.bigBlind}`
                      : undefined
                  }
                  isHost={!!(roomState?.ownership.ownerId === authSession?.userId)}
                  onCopyCode={copyCode}
                  sections={OPTIONS_ITEMS.map((item): DrawerSection => {
                    const isHostOnly = item.requiresHost && !userRole.isHostOrCoHost;
                    const isSeatedOnly = item.requiresSeated && !userRole.isSeated;
                    const isDisabled = isHostOnly || isSeatedOnly;
                    return {
                      id: item.id,
                      icon: item.icon,
                      label: item.label,
                      group: item.group,
                      groupLabel: GROUP_LABELS[item.group],
                      disabled: isDisabled,
                      disabledLabel: isHostOnly
                        ? 'Host only'
                        : isSeatedOnly
                          ? 'Sit down first'
                          : undefined,
                      onClick: () => {
                        if (item.settingsTab) {
                          setSettingsTab(item.settingsTab);
                          setShowSettings(true);
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'deal_hand') {
                          if (dealDisabledReason) {
                            showToast(dealDisabledReason);
                            return;
                          }
                          socket?.emit('start_hand', { tableId });
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'stand_up') {
                          socket?.emit('stand_up', { tableId, seat });
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'sit_toggle') {
                          if (myPlayer?.status === 'sitting_out')
                            socket?.emit('sit_in', { tableId });
                          else socket?.emit('sit_out', { tableId });
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'rebuy') {
                          const bb = roomState?.settings.bigBlind ?? 100;
                          setRebuyAmount(bb * 100);
                          setShowRebuyModal(true);
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'queue_bomb_pot') {
                          socket?.emit('queue_bomb_pot', { tableId });
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'toggle_display_bb') {
                          setDisplayBB(!displayBB);
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'cycle_anim_speed') {
                          const next: AnimationSpeed =
                            chipAnimSpeed === 'normal'
                              ? 'slow'
                              : chipAnimSpeed === 'slow'
                                ? 'off'
                                : 'normal';
                          setChipAnimSpeed(next);
                          saveAnimationSpeed(next);
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'toggle_sound') {
                          setSoundMuted((m) => !m);
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'cycle_theme') {
                          const next = tableTheme === 'green' ? 'blue' : 'green';
                          setTableTheme(next);
                          try {
                            localStorage.setItem('cardpilot_table_theme', next);
                          } catch {}
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'pause_resume') {
                          socket?.emit('game_control', {
                            tableId,
                            action: roomState?.status === 'PAUSED' ? 'resume' : 'pause',
                          });
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'end_game') {
                          socket?.emit('game_control', { tableId, action: 'end' });
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'close_room') {
                          if (
                            !confirm(
                              'Are you sure you want to close the room? All players will be returned to the lobby.',
                            )
                          )
                            return;
                          if (!socket || !isConnected) {
                            showToast('Cannot close room — not connected');
                            return;
                          }
                          socket.emit('close_room', { tableId });
                          const closeTimeout = setTimeout(() => {
                            showToast('Close room timed out');
                          }, 5000);
                          socket.once('room_closed', () => clearTimeout(closeTimeout));
                          socket.once('error_event', (err: { message: string }) => {
                            clearTimeout(closeTimeout);
                            showToast(`Error: ${err.message}`);
                          });
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'toggle_gto') {
                          setShowGtoSidebar(!showGtoSidebar);
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'toggle_hand_history') {
                          setShowInGameHistory(!showInGameHistory);
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'toggle_stats') {
                          setShowSessionStats(!showSessionStats);
                          if (!showSessionStats) socket?.emit('request_session_stats', { tableId });
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'toggle_log') {
                          setShowRoomLog(!showRoomLog);
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'open_profile') {
                          navigate('/profile');
                          setShowOptionsDrawer(false);
                        } else if (item.action === 'back_to_lobby') {
                          if (handInProgress && !confirm('A hand is in progress. Leave the table?'))
                            return;
                          leaveRoom();
                          setShowOptionsDrawer(false);
                        }
                      },
                    };
                  })}
                />
              )}

              {/* Room Settings Panel */}
              {showSettings && roomState && (
                <div
                  className="fixed inset-0 z-50 flex items-center justify-center bg-black/65"
                  onClick={() => setShowSettings(false)}
                >
                  <div
                    className="w-[480px] max-h-[80vh] overflow-y-auto"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <RoomSettingsPanel
                      roomState={roomState}
                      isHost={userRole.isHostOrCoHost}
                      initialTab={settingsTab}
                      players={snapshot?.players ?? []}
                      authUserId={authSession?.userId ?? ''}
                      onUpdateSettings={(settings) => {
                        socket?.emit('update_settings', { tableId, settings });
                      }}
                      onKick={(targetUserId, reason, ban) => {
                        socket?.emit('kick_player', { tableId, targetUserId, reason, ban });
                      }}
                      onTransfer={(newOwnerId) => {
                        socket?.emit('transfer_ownership', { tableId, newOwnerId });
                      }}
                      onSetCoHost={(userId, add) => {
                        socket?.emit('set_cohost', { tableId, userId, add });
                      }}
                      onBotAddChips={(botSeat, amount) => {
                        socket?.emit('bot_add_chips', { tableId, seat: botSeat, amount });
                      }}
                      onClose={() => setShowSettings(false)}
                    />
                  </div>
                </div>
              )}

              <main className="flex-1 flex flex-col overflow-hidden relative">
                <div className="cp-table-float-panels">
                  {/* Kicked / Disconnected overlays... */}
                </div>

                {/* BuyIn Modal */}
                {showBuyInModal && !isFastBattlePlaying && (
                  <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/65"
                    onClick={() => setShowBuyInModal(false)}
                  >
                    <div
                      className="glass-card p-6 w-80 space-y-4"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <h3 className="text-sm font-bold text-white text-center">Buy In</h3>

                      {/* Amount display */}
                      <div className="text-center">
                        <span className="text-3xl font-bold text-amber-400 cp-num">
                          {buyInAmount.toLocaleString()}
                        </span>
                        <span className="text-xs text-slate-500 ml-1">chips</span>
                      </div>

                      {/* Slider */}
                      {(() => {
                        const min = roomState?.settings?.buyInMin ?? 40;
                        const max = roomState?.settings?.buyInMax ?? 300;
                        const bb = roomState?.settings?.bigBlind ?? 3;
                        return (
                          <>
                            <input
                              type="range"
                              min={min}
                              max={max}
                              step={bb}
                              value={buyInAmount}
                              onChange={(e) => setBuyInAmount(Number(e.target.value))}
                              className="w-full accent-amber-400"
                            />
                            <div className="flex justify-between text-xs text-slate-500">
                              <span>{min.toLocaleString()}</span>
                              <span>{max.toLocaleString()}</span>
                            </div>

                            {/* Quick-pick buttons */}
                            <div className="flex gap-2">
                              {[...new Set([min, Math.round((min + max) / 2 / bb) * bb, max])].map(
                                (v) => (
                                  <button
                                    key={v}
                                    onClick={() => setBuyInAmount(v)}
                                    className={`flex-1 py-1.5 rounded text-xs font-medium transition-colors ${
                                      buyInAmount === v
                                        ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                                        : 'bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10'
                                    }`}
                                  >
                                    {v.toLocaleString()}
                                  </button>
                                ),
                              )}
                            </div>
                          </>
                        );
                      })()}

                      <button
                        onClick={() => {
                          socket?.emit('sit_down', {
                            tableId,
                            seat: pendingSitSeat,
                            buyIn: buyInAmount,
                          });
                          setShowBuyInModal(false);
                        }}
                        className="w-full btn-primary py-3"
                      >
                        Sit Down
                      </button>
                    </div>
                  </div>
                )}

                <TableContainer onSeatClick={handleSeatClick} />

                {/* Overlays */}
                {bombPotOverlayActive && (
                  <BombPotOverlay
                    anteAmount={bombPotOverlayActive.anteAmount}
                    onDismiss={() => {
                      /* no-op or handled by effect */
                    }}
                  />
                )}
                {sevenTwoRevealActive && (
                  <SevenTwoRevealOverlay
                    winnerName={`Seat ${sevenTwoRevealActive.winnerSeat}`}
                    winnerCards={sevenTwoRevealActive.winnerCards}
                    totalBounty={sevenTwoRevealActive.totalBounty}
                    onDismiss={() => {
                      /* no-op */
                    }}
                  />
                )}
                {showInGameHistory && (
                  <InGameHandHistory
                    open={showInGameHistory}
                    onClose={() => setShowInGameHistory(false)}
                    tableId={tableId}
                    currentRoomCode={currentRoomCode}
                    socket={socket}
                  />
                )}
                {showSessionStats && (
                  <SessionScoreboard
                    open={showSessionStats}
                    onClose={() => setShowSessionStats(false)}
                    entries={sessionStatsData}
                    currentUserId={authSession?.userId}
                    displayBB={displayBB}
                    bigBlind={roomState?.settings.bigBlind ?? 100}
                    onRefresh={() => socket?.emit('request_session_stats', { tableId })}
                  />
                )}
                {showFoldConfirm && (
                  <FoldConfirmModal
                    open={showFoldConfirm}
                    onConfirmFold={() => {
                      setShowFoldConfirm(false);
                      socket?.emit('action_submit', {
                        tableId,
                        handId: snapshot?.handId,
                        action: 'fold',
                      });
                    }}
                    onCancel={() => setShowFoldConfirm(false)}
                    suppressedThisSession={suppressFoldConfirm}
                    onSuppressChange={setSuppressFoldConfirm}
                  />
                )}
                {/* HandSummaryDrawer */}
                {showRoomLog && (
                  <div className="absolute top-0 right-0 bottom-0 w-80 bg-slate-900/95 border-l border-white/10 p-4 overflow-y-auto z-50">
                    <h3>Room Log</h3>
                    {/* ... */}
                  </div>
                )}

                {/* Bottom Bar — floats over table */}
                {!isMobilePortrait && !isFastBattlePlaying && (
                  <div className="cp-action-float">
                    <BottomActionBar
                      canAct={snapshot?.actorSeat === seat}
                      legal={snapshot?.legalActions ?? null}
                      pot={snapshot?.pot ?? 0}
                      bigBlind={roomState?.settings.bigBlind ?? 100}
                      currentBet={snapshot?.currentBet ?? 0}
                      raiseTo={raiseTo}
                      setRaiseTo={setRaiseTo}
                      onAction={(action, amount) => {
                        if (!snapshot?.handId) return;
                        socket?.emit('action_submit', {
                          tableId,
                          handId: snapshot.handId,
                          action,
                          amount,
                        });
                      }}
                      street={snapshot?.street ?? 'PREFLOP'}
                      board={snapshot?.board ?? []}
                      heroStack={myPlayer?.stack ?? 0}
                      numPlayers={snapshot?.players.length ?? 0}
                      advice={advice}
                      preAction={preAction}
                      onSetPreAction={handleSetPreAction}
                      derivedActionBar={derivedActionBarValue}
                      derivedPreActionUI={derivedPreActionUIValue}
                      isMyTurn={snapshot?.actorSeat === seat}
                      onFoldAttempt={() => {
                        if (
                          shouldConfirmUnnecessaryFold(snapshot?.legalActions, suppressFoldConfirm)
                        ) {
                          setShowFoldConfirm(true);
                        } else {
                          socket?.emit('action_submit', {
                            tableId,
                            handId: snapshot?.handId,
                            action: 'fold',
                          });
                        }
                      }}
                    />
                  </div>
                )}
              </main>
            </>
          )}
        </div>
      </div>

      {/* Mobile Bottom Tabs */}
      {isMobile && view !== 'table' && <div className="cp-mobile-nav-spacer" />}
      {isMobile && (
        <MobileMoreMenu
          open={showMoreMenu}
          onClose={() => setShowMoreMenu(false)}
          onSignOut={handleLogout}
          activeView={view}
          onNavigate={setView}
        />
      )}
    </div>
  );
}
