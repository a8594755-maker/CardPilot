import { memo, useCallback, useMemo, useRef } from 'react';
import type { LobbyRoomSummary } from '@cardpilot/shared-types';
import { LobbyQuickPlayCard } from './LobbyQuickPlayCard';
import { JoinByCodeCard } from './JoinByCodeCard';
import { CreateRoomCard, type CreateRoomSettings } from './CreateRoomCard';
import { OpenRoomsList } from './OpenRoomsList';
import { CurrentRoomBanner } from './CurrentRoomBanner';

export interface LobbyProps {
  /* Connection */
  connected: boolean;
  /* Room state */
  currentRoomCode: string;
  currentRoomName: string;
  isOwner: boolean;
  lobbyRooms: LobbyRoomSummary[];
  /* Create room settings (lifted state from App) */
  createSettings: CreateRoomSettings;
  onCreateSettingsChange: (s: CreateRoomSettings) => void;
  /* Actions */
  onQuickPlay: () => void;
  onJoinByCode: (code: string) => void;
  onCreateRoom: (settings: CreateRoomSettings) => void;
  onJoinRoom: (roomCode: string) => void;
  onRefreshLobby: () => void;
  onCopyCode: () => void;
  onGoToTable: () => void;
  onLeaveRoom: () => void;
}

export const Lobby = memo(function Lobby({
  connected,
  currentRoomCode,
  currentRoomName,
  isOwner,
  lobbyRooms,
  createSettings,
  onCreateSettingsChange,
  onQuickPlay,
  onJoinByCode,
  onCreateRoom,
  onJoinRoom,
  onRefreshLobby,
  onCopyCode,
  onGoToTable,
  onLeaveRoom,
}: LobbyProps) {
  const disabled = !connected;
  const createCardRef = useRef<HTMLDivElement>(null);

  const openRoomCount = useMemo(
    () => lobbyRooms.filter((r) => r.status === 'OPEN' && r.playerCount < r.maxPlayers).length,
    [lobbyRooms],
  );

  const scrollToCreate = useCallback(() => {
    createCardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  const handleCreatePublic = useCallback(() => {
    onCreateSettingsChange({ ...createSettings, visibility: 'public' });
    scrollToCreate();
  }, [createSettings, onCreateSettingsChange, scrollToCreate]);

  return (
    <main className="flex-1 overflow-y-auto cp-lobby-bg">
      <div className="relative z-[1] max-w-2xl mx-auto px-4 sm:px-6 py-8 space-y-5">
        {/* Header */}
        <header className="mb-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center text-sm font-extrabold text-slate-900 shadow-md">
              C
            </div>
            <div>
              <h1 className="text-2xl font-extrabold text-white tracking-tight leading-tight">
                Lobby
              </h1>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-400 animate-pulse'}`}
                  aria-hidden="true"
                />
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
                  {connected ? 'Online' : 'Offline'}
                </span>
              </div>
            </div>
          </div>
        </header>

        {/* Current room banner (if in a room) */}
        {currentRoomCode && (
          <CurrentRoomBanner
            roomCode={currentRoomCode}
            roomName={currentRoomName}
            isOwner={isOwner}
            onCopyCode={onCopyCode}
            onGoToTable={onGoToTable}
            onLeave={onLeaveRoom}
          />
        )}

        {/* A) Quick Play — primary entry point */}
        {!currentRoomCode && (
          <LobbyQuickPlayCard
            disabled={disabled}
            openRoomCount={openRoomCount}
            onQuickPlay={onQuickPlay}
            onCustomize={scrollToCreate}
          />
        )}

        {/* B) Join with Code */}
        <JoinByCodeCard disabled={disabled} onJoin={onJoinByCode} />

        {/* C) Create a Room */}
        <div ref={createCardRef}>
          <CreateRoomCard
            disabled={disabled}
            settings={createSettings}
            onSettingsChange={onCreateSettingsChange}
            onCreate={onCreateRoom}
          />
        </div>

        {/* D) Open Rooms */}
        <OpenRoomsList
          rooms={lobbyRooms}
          disabled={disabled}
          onJoinRoom={onJoinRoom}
          onRefresh={onRefreshLobby}
          onCreatePublic={handleCreatePublic}
        />
      </div>
    </main>
  );
});
