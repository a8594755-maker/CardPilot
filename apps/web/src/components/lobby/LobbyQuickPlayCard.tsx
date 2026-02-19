import { memo, useState, useCallback } from "react";

export interface QuickPlayProps {
  disabled: boolean;
  openRoomCount: number;
  onQuickPlay: () => void;
  onCustomize: () => void;
  /** Last-used settings for the confirmation sheet */
  lastSettings?: { maxPlayers: number; sb: number; bb: number; buyInMin: number; buyInMax: number };
}

export const LobbyQuickPlayCard = memo(function LobbyQuickPlayCard({
  disabled,
  openRoomCount,
  onQuickPlay,
  onCustomize,
  lastSettings,
}: QuickPlayProps) {
  const [showConfirm, setShowConfirm] = useState(false);

  const handleClick = useCallback(() => {
    if (lastSettings) {
      setShowConfirm(true);
    } else {
      onQuickPlay();
    }
  }, [lastSettings, onQuickPlay]);

  const handleStart = useCallback(() => {
    setShowConfirm(false);
    onQuickPlay();
  }, [onQuickPlay]);

  const handleCustomize = useCallback(() => {
    setShowConfirm(false);
    onCustomize();
  }, [onCustomize]);

  return (
    <div className="cp-lobby-card cp-lobby-card--primary">
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
        {/* Text */}
        <div className="flex-1 min-w-0">
          <h2 className="cp-lobby-title">Quick Play</h2>
          <p className="cp-lobby-subtitle mt-1">
            Start a table in one click.
            {openRoomCount > 0 && (
              <span className="ml-1 text-emerald-400/80">
                {openRoomCount} open table{openRoomCount !== 1 ? "s" : ""} available
              </span>
            )}
          </p>
        </div>

        {/* CTA */}
        <button
          disabled={disabled}
          onClick={handleClick}
          className="cp-btn cp-btn-success shrink-0 text-sm font-bold px-5 py-2 shadow-lg"
          style={{ minWidth: 96, minHeight: 32 }}
        >
          Quick Play
        </button>
      </div>

      {/* Confirmation sheet */}
      {showConfirm && lastSettings && (
        <div className="mt-4 pt-4 border-t border-white/5">
          <div className="cp-summary-line">
            {lastSettings.maxPlayers}-max
            <span className="mx-2 text-white/20">·</span>
            Blinds {lastSettings.sb}/{lastSettings.bb}
            <span className="mx-2 text-white/20">·</span>
            Buy-in {lastSettings.buyInMin.toLocaleString()}–{lastSettings.buyInMax.toLocaleString()}
          </div>
          <div className="flex items-center justify-center gap-3 mt-3">
            <button onClick={handleStart} className="cp-btn cp-btn-success px-6">
              Start
            </button>
            <button onClick={handleCustomize} className="cp-btn cp-btn-ghost px-4">
              Customize
            </button>
          </div>
        </div>
      )}
    </div>
  );
});
