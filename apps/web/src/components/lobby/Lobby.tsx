import { memo, useCallback, useMemo, useRef } from 'react';
import type { LobbyRoomSummary } from '@cardpilot/shared-types';
import { useI18n } from '../../i18n';
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
  const { t } = useI18n();
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
      <div className="relative z-[1] max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-4">
        {/* Header */}
        <header className="mb-3 flex items-end justify-between">
          <div>
            <h1 className="text-3xl font-extrabold text-white tracking-tight">{t('Lobby')}</h1>
            <div className="flex items-center gap-2 mt-1.5">
              <div
                className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-red-500'}`}
              />
              <span className="text-xs text-slate-400">
                {connected ? t('Connected') : t('Disconnected')}
              </span>
            </div>
          </div>
          {openRoomCount > 0 && (
            <span className="hidden sm:inline-flex items-center gap-1.5 text-[11px] font-mono text-slate-500">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/70" />
              {t('{n} open tables available', { n: openRoomCount })}
            </span>
          )}
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

        {/* Hero row: Quick Play + Join with Code side by side on desktop */}
        <div
          className={`grid gap-4 ${!currentRoomCode ? 'lg:grid-cols-[1.5fr_1fr]' : 'lg:grid-cols-1'}`}
        >
          {!currentRoomCode && (
            <LobbyQuickPlayCard
              disabled={disabled}
              openRoomCount={openRoomCount}
              onQuickPlay={onQuickPlay}
              onCustomize={scrollToCreate}
            />
          )}
          <JoinByCodeCard disabled={disabled} onJoin={onJoinByCode} />
        </div>

        {/* Work row: Create a Room + live Open Rooms side by side */}
        <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr] items-start">
          <div ref={createCardRef}>
            <CreateRoomCard
              disabled={disabled}
              settings={createSettings}
              onSettingsChange={onCreateSettingsChange}
              onCreate={onCreateRoom}
            />
          </div>
          <OpenRoomsList
            rooms={lobbyRooms}
            disabled={disabled}
            onJoinRoom={onJoinRoom}
            onRefresh={onRefreshLobby}
            onCreatePublic={handleCreatePublic}
          />
        </div>
      </div>
    </main>
  );
});
