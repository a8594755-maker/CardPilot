import { useState } from "react";
import type { RoomFullState, TablePlayer } from "@cardpilot/shared-types";

function SettingRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs text-slate-400 shrink-0">{label}</span>
      {children}
    </div>
  );
}

export function ToggleSetting({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`text-[11px] px-3 py-1.5 rounded-lg border transition-all ${
        checked ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-white/5 border-white/10 text-slate-500"
      }`}
    >
      {checked ? "✓ " : ""}{label}
    </button>
  );
}

export function RoomSettingsPanel({ roomState, isHost, readOnly = false, initialTab, players, authUserId, onUpdateSettings, onKick, onTransfer, onSetCoHost, onBotAddChips, onClose }: {
  roomState: RoomFullState;
  isHost: boolean;
  readOnly?: boolean;
  initialTab?: string;
  players: TablePlayer[];
  authUserId: string;
  onUpdateSettings: (settings: Record<string, unknown>) => void;
  onKick: (targetUserId: string, reason: string, ban: boolean) => void;
  onTransfer: (newOwnerId: string) => void;
  onSetCoHost: (userId: string, add: boolean) => void;
  onBotAddChips?: (seat: number, amount: number) => void;
  onClose: () => void;
}) {
  const tabMap: Record<string, "game" | "rules" | "special" | "players" | "moderation" | "bots"> = {
    game: "game", rules: "rules", special: "special", players: "players",
    moderation: "moderation", bots: "bots", preferences: "game",
  };
  const [tab, setTab] = useState<"game" | "rules" | "special" | "players" | "moderation" | "bots">(tabMap[initialTab ?? ""] ?? "game");
  const [kickReason, setKickReason] = useState("");

  const s = roomState.settings;

  function updateField(key: string, value: unknown) {
    if (readOnly) return;
    onUpdateSettings({ [key]: value });
  }

  /* ── Blind structure helpers ── */
  const [blindLevels, setBlindLevels] = useState(
    s.blindStructure ?? [{ smallBlind: s.smallBlind, bigBlind: s.bigBlind, ante: s.ante, durationMinutes: 20 }]
  );

  function addBlindLevel() {
    if (readOnly) return;
    const last = blindLevels[blindLevels.length - 1];
    const next = { smallBlind: last.smallBlind * 2, bigBlind: last.bigBlind * 2, ante: last.ante, durationMinutes: last.durationMinutes };
    const updated = [...blindLevels, next];
    setBlindLevels(updated);
    updateField("blindStructure", updated);
  }

  function removeBlindLevel(idx: number) {
    if (readOnly) return;
    if (blindLevels.length <= 1) return;
    const updated = blindLevels.filter((_, i) => i !== idx);
    setBlindLevels(updated);
    updateField("blindStructure", updated);
  }

  function updateBlindLevel(idx: number, field: string, value: number) {
    if (readOnly) return;
    const updated = blindLevels.map((lvl, i) => i === idx ? { ...lvl, [field]: value } : lvl);
    setBlindLevels(updated);
    updateField("blindStructure", updated);
    if (idx === 0) {
      if (field === "smallBlind") updateField("smallBlind", value);
      if (field === "bigBlind") updateField("bigBlind", value);
      if (field === "ante") updateField("ante", value);
    }
  }

  const SectionTitle = ({ children }: { children: React.ReactNode }) => (
    <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mt-2 mb-1">{children}</div>
  );

  const YesNo = ({ label, value, onChange, hint }: { label: string; value: boolean; onChange: (v: boolean) => void; hint?: string }) => (
    <div className="flex items-center justify-between gap-3 min-h-[40px]">
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="text-sm text-slate-300 truncate">{label}</span>
        {hint && <span className="text-[9px] text-slate-600 cursor-help" title={hint}>?</span>}
      </div>
      <div className="cp-segmented shrink-0">
        <button onClick={() => onChange(true)}
          className="cp-segmented-item" data-active={value ? "true" : undefined}
          style={value ? { background: 'rgba(34, 197, 94, 0.15)', color: '#4ade80' } : undefined}>
          Yes
        </button>
        <button onClick={() => onChange(false)}
          className="cp-segmented-item" data-active={!value ? "true" : undefined}
          style={!value ? { background: 'rgba(239, 68, 68, 0.1)', color: '#f87171' } : undefined}>
          No
        </button>
      </div>
    </div>
  );

  const TriToggle = ({ label, value, options, onChange }: { label: string; value: string; options: { value: string; label: string }[]; onChange: (v: string) => void }) => (
    <div className="space-y-1.5">
      <span className="text-sm text-slate-300">{label}</span>
      <div className="cp-segmented w-full">
        {options.map((opt) => (
          <button key={opt.value} onClick={() => onChange(opt.value)}
            className="cp-segmented-item flex-1" data-active={value === opt.value ? "true" : undefined}>
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div className="cp-panel p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-bold text-white">Room Settings {readOnly
          ? <span className="text-xs text-slate-500 font-normal ml-1">(View Only)</span>
          : <span className="text-xs text-amber-400 font-normal ml-1">(Host)</span>
        }</h3>
        <button onClick={onClose} className="cp-btn cp-btn-ghost !min-h-[36px] !min-w-[36px] !px-0 text-slate-400 hover:text-white" aria-label="Close settings">✕</button>
      </div>

      {/* Tabs — segmented control style */}
      <div className="cp-segmented w-full overflow-x-auto">
        {([
          { key: "game" as const, label: "Blinds" },
          { key: "rules" as const, label: "Rules" },
          { key: "special" as const, label: "Special" },
          { key: "players" as const, label: "Players" },
          { key: "moderation" as const, label: "Mod" },
          { key: "bots" as const, label: "Bots" },
        ]).map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className="cp-segmented-item flex-1 whitespace-nowrap" data-active={tab === t.key ? "true" : undefined}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ══ BLINDS & STRUCTURE TAB ══ */}
      {tab === "game" && (
        <div className="space-y-3">
          <SectionTitle>Poker Variant</SectionTitle>
          <SettingRow label="Game Type">
            <select value={s.gameType} onChange={(e) => updateField("gameType", e.target.value)} className="input-field text-xs !py-1.5">
              <option value="texas">No Limit Texas Hold'em</option>
              <option value="omaha">Pot Limit Omaha</option>
            </select>
          </SettingRow>
          <SettingRow label="Max Players">
            <select value={s.maxPlayers} onChange={(e) => updateField("maxPlayers", Number(e.target.value))} className="input-field text-xs !py-1.5 w-20">
              {[2, 3, 4, 5, 6, 7, 8, 9].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </SettingRow>

          <SectionTitle>Blind Levels</SectionTitle>
          <div className="space-y-2">
            {/* Header row */}
            <div className="grid grid-cols-[2rem_1fr_1fr_1fr_1fr_1.5rem] gap-1 text-[9px] text-slate-500 uppercase tracking-wider px-1">
              <span>#</span><span>SB</span><span>BB</span><span>Ante</span><span>Min</span><span></span>
            </div>
            {blindLevels.map((lvl, i) => (
              <div key={i} className="grid grid-cols-[2rem_1fr_1fr_1fr_1fr_1.5rem] gap-1 items-center">
                <span className="text-[10px] text-slate-500 text-center">{i + 1}</span>
                <input type="number" value={lvl.smallBlind} min={1}
                  onChange={(e) => updateBlindLevel(i, "smallBlind", Number(e.target.value))}
                  className="input-field text-[11px] !py-1 w-full text-center" />
                <input type="number" value={lvl.bigBlind} min={2}
                  onChange={(e) => updateBlindLevel(i, "bigBlind", Number(e.target.value))}
                  className="input-field text-[11px] !py-1 w-full text-center" />
                <input type="number" value={lvl.ante} min={0}
                  onChange={(e) => updateBlindLevel(i, "ante", Number(e.target.value))}
                  className="input-field text-[11px] !py-1 w-full text-center" />
                <input type="number" value={lvl.durationMinutes} min={1}
                  onChange={(e) => updateBlindLevel(i, "durationMinutes", Number(e.target.value))}
                  className="input-field text-[11px] !py-1 w-full text-center" />
                <button onClick={() => removeBlindLevel(i)}
                  className="text-[10px] text-slate-600 hover:text-red-400 transition-colors text-center leading-none"
                  title="Remove level">×</button>
              </div>
            ))}
            <button onClick={addBlindLevel}
              className="w-full text-[10px] py-1.5 rounded-md border border-dashed border-white/10 text-slate-400 hover:text-white hover:border-white/20 transition-all">
              + Add Level
            </button>
          </div>

          <SectionTitle>Buy-in</SectionTitle>
          <div className="grid grid-cols-2 gap-3">
            <SettingRow label="Min">
              <input type="number" value={s.buyInMin} onChange={(e) => updateField("buyInMin", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" />
            </SettingRow>
            <SettingRow label="Max">
              <input type="number" value={s.buyInMax} onChange={(e) => updateField("buyInMax", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" />
            </SettingRow>
          </div>
        </div>
      )}

      {/* ══ GAME RULES TAB ══ */}
      {tab === "rules" && (
        <div className="space-y-3">
          <SectionTitle>Hand Flow</SectionTitle>
          <YesNo
            label="Auto-start next hand?"
            value={s.autoStartNextHand}
            onChange={(v) => updateField("autoStartNextHand", v)}
            hint="Automatically starts the next hand after showdown delay"
          />
          <TriToggle
            label="Showdown speed"
            value={s.showdownSpeed}
            options={[
              { value: "fast", label: "Fast (3s)" },
              { value: "normal", label: "Normal (6s)" },
              { value: "slow", label: "Slow (9s)" },
            ]}
            onChange={(v) => updateField("showdownSpeed", v)}
          />
          <YesNo
            label="Deal to away players?"
            value={s.dealToAwayPlayers}
            onChange={(v) => updateField("dealToAwayPlayers", v)}
            hint="When off, disconnected/away seats are excluded from auto-deal eligibility"
          />
          <YesNo
            label="Reveal all at showdown?"
            value={s.revealAllAtShowdown}
            onChange={(v) => updateField("revealAllAtShowdown", v)}
            hint="Force reveal on river-call or all-in runouts"
          />
          <YesNo
            label="Room funds tracking?"
            value={s.roomFundsTracking}
            onChange={(v) => updateField("roomFundsTracking", v)}
            hint="Tracks per-player buy-ins, net and stack restoration across rejoin"
          />

          <SectionTitle>Gameplay</SectionTitle>
          <TriToggle label="Allow Run It Twice?"
            value={s.runItTwiceMode}
            options={[
              { value: "always", label: "Always" },
              { value: "ask_players", label: "Ask Players" },
              { value: "off", label: "No" },
            ]}
            onChange={(v) => { updateField("runItTwiceMode", v); updateField("runItTwice", v !== "off"); }}
          />
          <YesNo
            label="Auto reveal on all-in + called?"
            value={s.autoRevealOnAllInCall}
            onChange={(v) => updateField("autoRevealOnAllInCall", v)}
            hint="Reveal live players' hole cards when no more betting decisions remain"
          />
          <YesNo
            label="Allow show after fold?"
            value={s.allowShowAfterFold}
            onChange={(v) => updateField("allowShowAfterFold", v)}
            hint="Folded players may voluntarily reveal before hand end"
          />
          <YesNo label="Allow UTG Straddle 2BB?" value={s.straddleAllowed} onChange={(v) => updateField("straddleAllowed", v)} />
          <YesNo label="Rebuy allowed?" value={s.rebuyAllowed} onChange={(v) => updateField("rebuyAllowed", v)} />

          <SectionTitle>Timers</SectionTitle>
          <div className="grid grid-cols-2 gap-3">
            <SettingRow label="Decision Time (sec)">
              <input type="number" value={s.actionTimerSeconds} onChange={(e) => updateField("actionTimerSeconds", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" min={5} max={120} />
            </SettingRow>
            <SettingRow label="Time Bank (sec)">
              <input type="number" value={s.timeBankSeconds} onChange={(e) => updateField("timeBankSeconds", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" min={0} max={300} />
            </SettingRow>
          </div>
          <SettingRow label="Hands to fill Time Bank">
            <input type="number" value={s.timeBankHandsToFill} onChange={(e) => updateField("timeBankHandsToFill", Number(e.target.value))} className="input-field text-xs !py-1.5 w-24" min={1} max={50} />
          </SettingRow>
          <div className="grid grid-cols-2 gap-3">
            <SettingRow label="Extension/Use (sec)">
              <input type="number" value={s.thinkExtensionSecondsPerUse} onChange={(e) => updateField("thinkExtensionSecondsPerUse", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" min={1} max={60} />
            </SettingRow>
            <SettingRow label="Extension Quota (/hr)">
              <input type="number" value={s.thinkExtensionQuotaPerHour} onChange={(e) => updateField("thinkExtensionQuotaPerHour", Number(e.target.value))} className="input-field text-xs !py-1.5 w-full" min={0} max={20} />
            </SettingRow>
          </div>
        </div>
      )}

      {/* ══ SPECIAL FEATURES TAB ══ */}
      {tab === "special" && (
        <div className="space-y-3">
          <SectionTitle>Bomb Pot</SectionTitle>
          <YesNo label="Bomb Pot enabled?" value={s.bombPotEnabled} onChange={(v) => updateField("bombPotEnabled", v)}
            hint="All players put in a set amount pre-flop with no betting" />
          {s.bombPotEnabled && (<>
            <TriToggle label="Trigger mode"
              value={s.bombPotTriggerMode ?? "frequency"}
              options={[
                { value: "frequency", label: "Every N" },
                { value: "probability", label: "% Chance" },
                { value: "manual", label: "Manual" },
              ]}
              onChange={(v) => updateField("bombPotTriggerMode", v)}
            />
            {(s.bombPotTriggerMode ?? "frequency") === "frequency" && (
              <SettingRow label="Every N hands">
                <input type="number" value={s.bombPotFrequency} onChange={(e) => updateField("bombPotFrequency", Number(e.target.value))} className="input-field text-xs !py-1.5 w-20" min={1} max={100} />
              </SettingRow>
            )}
            {(s.bombPotTriggerMode ?? "frequency") === "probability" && (
              <SettingRow label="Probability (%)">
                <input type="number" value={s.bombPotProbability ?? 0} onChange={(e) => updateField("bombPotProbability", Number(e.target.value))} className="input-field text-xs !py-1.5 w-20" min={0} max={100} />
              </SettingRow>
            )}
            <TriToggle label="Ante mode"
              value={s.bombPotAnteMode ?? "bb_multiplier"}
              options={[
                { value: "bb_multiplier", label: "× BB" },
                { value: "fixed", label: "Fixed" },
              ]}
              onChange={(v) => updateField("bombPotAnteMode", v)}
            />
            <SettingRow label={s.bombPotAnteMode === "fixed" ? "Ante (chips)" : "Ante (× BB)"}>
              <input type="number" value={s.bombPotAnteValue ?? 1} onChange={(e) => updateField("bombPotAnteValue", Number(e.target.value))} className="input-field text-xs !py-1.5 w-20" min={1} max={100} />
            </SettingRow>
          </>)}

          <SectionTitle>Double Board</SectionTitle>
          <TriToggle label="Double Board?"
            value={s.doubleBoardMode}
            options={[
              { value: "always", label: "Always" },
              { value: "bomb_pot", label: "Bomb Pot Only" },
              { value: "off", label: "Off" },
            ]}
            onChange={(v) => updateField("doubleBoardMode", v)}
          />

          <SectionTitle>7-2 Bounty</SectionTitle>
          <SettingRow label="Bounty amount (0 = off)">
            <input type="number" value={s.sevenTwoBounty} onChange={(e) => updateField("sevenTwoBounty", Number(e.target.value))} className="input-field text-xs !py-1.5 w-24" min={0} />
          </SettingRow>
          {s.sevenTwoBounty > 0 && (
            <p className="text-[10px] text-slate-500">Each player pays {s.sevenTwoBounty} to the winner holding 7-2</p>
          )}
        </div>
      )}

      {/* ══ PLAYERS TAB ══ */}
      {tab === "players" && (
        <div className="space-y-2">
          <p className="text-[10px] text-slate-500">Owner: <span className="text-amber-400 font-medium">{roomState.ownership.ownerName}</span></p>
          {players.length === 0 ? (
            <p className="text-xs text-slate-500 text-center py-4">No players seated</p>
          ) : (
            players.map((p) => {
              const isMe = p.userId === authUserId;
              const isPlayerOwner = p.userId === roomState.ownership.ownerId;
              const isPlayerCoHost = roomState.ownership.coHostIds.includes(p.userId);
              return (
                <div key={p.seat} className="flex items-center gap-3 p-2 rounded-lg bg-white/[0.03] border border-white/5">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-slate-600 to-slate-700 flex items-center justify-center text-xs font-bold text-white">{p.seat}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white truncate">{p.name}</span>
                      {isPlayerOwner && <span className="text-[9px] bg-amber-500/20 text-amber-400 px-1 rounded">👑 Host</span>}
                      {isPlayerCoHost && <span className="text-[9px] bg-blue-500/20 text-blue-400 px-1 rounded">⭐ Co-Host</span>}
                      {isMe && <span className="text-[9px] bg-cyan-500/20 text-cyan-400 px-1 rounded">You</span>}
                    </div>
                    <span className="text-[10px] text-slate-500">{p.stack.toLocaleString()} chips</span>
                  </div>
                  {!isMe && !isPlayerOwner && (
                    <div className="flex gap-1 shrink-0">
                      {isHost && (
                        <button onClick={() => onSetCoHost(p.userId, !isPlayerCoHost)}
                          className="text-[10px] px-2 py-1 rounded bg-white/5 text-slate-400 hover:text-white transition-colors">
                          {isPlayerCoHost ? "Remove Co-Host" : "Make Co-Host"}
                        </button>
                      )}
                      {isHost && (
                        <button onClick={() => onTransfer(p.userId)}
                          className="text-[10px] px-2 py-1 rounded bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors">
                          Transfer Host
                        </button>
                      )}
                      <button onClick={() => onKick(p.userId, kickReason, false)}
                        className="text-[10px] px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors">
                        Kick
                      </button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* ══ MODERATION TAB ══ */}
      {tab === "moderation" && (
        <div className="space-y-3">
          <SettingRow label="Room Visibility">
            <select value={s.visibility} onChange={(e) => updateField("visibility", e.target.value)} className="input-field text-xs !py-1.5">
              <option value="public">Public</option>
              <option value="private">Private</option>
            </select>
          </SettingRow>
          {s.visibility === "private" && (
            <SettingRow label="Password">
              <input type="text" value={s.password ?? ""} onChange={(e) => updateField("password", e.target.value || null)} className="input-field text-xs !py-1.5 w-40" placeholder="Set password..." />
            </SettingRow>
          )}
          <SettingRow label="Kick Reason">
            <input value={kickReason} onChange={(e) => setKickReason(e.target.value)} className="input-field text-xs !py-1.5 w-full" placeholder="Optional reason for kicks..." />
          </SettingRow>
          <SettingRow label="Max Consecutive Timeouts">
            <input type="number" value={s.maxConsecutiveTimeouts} onChange={(e) => updateField("maxConsecutiveTimeouts", Number(e.target.value))} className="input-field text-xs !py-1.5 w-20" min={1} max={10} />
          </SettingRow>
          <SettingRow label="Disconnect Grace (sec)">
            <input type="number" value={s.disconnectGracePeriod} onChange={(e) => updateField("disconnectGracePeriod", Number(e.target.value))} className="input-field text-xs !py-1.5 w-20" min={5} max={120} />
          </SettingRow>

          {/* Ban list */}
          {roomState.banList.length > 0 && (
            <div>
              <span className="text-[10px] text-slate-500 uppercase font-medium">Banned Users ({roomState.banList.length})</span>
              <div className="mt-1 flex flex-wrap gap-1">
                {roomState.banList.map((uid) => (
                  <span key={uid} className="text-[10px] bg-red-500/10 text-red-400 px-2 py-0.5 rounded">{uid.slice(0, 8)}...</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══ BOTS TAB ══ */}
      {tab === "bots" && (
        <div className="space-y-3">
          <SectionTitle>GTO Bot Seats</SectionTitle>
          <p className="text-[10px] text-slate-400">
            Assign bots to empty seats. Choose a personality and model version per seat.
          </p>

          <SettingRow label="Bot Buy-in">
            <input
              type="number"
              value={s.botBuyIn ?? s.bigBlind * 100}
              onChange={(e) => updateField("botBuyIn", Number(e.target.value))}
              className="input-field text-xs !py-1.5 w-28"
              min={s.buyInMin}
              max={s.buyInMax}
              disabled={readOnly}
            />
          </SettingRow>
          <p className="text-[10px] text-slate-500">
            Default: {s.bigBlind * 100} chips (100 BB). Range: {s.buyInMin} – {s.buyInMax}.
          </p>

          {Array.from({ length: s.maxPlayers }, (_, i) => i + 1).map((seat) => {
            const botSeats = s.botSeats ?? [];
            const existing = botSeats.find((b) => b.seat === seat);
            const seatPlayer = players.find((p) => p.seat === seat);
            const isOccupiedByHuman = !!seatPlayer && !seatPlayer.isBot;

            return (
              <div key={seat} className="flex items-center gap-2 p-2 rounded-lg bg-white/[0.03] border border-white/5">
                <span className="text-xs text-slate-400 w-14">Seat {seat}</span>

                {isOccupiedByHuman ? (
                  <span className="text-[10px] text-slate-500 italic flex-1">
                    Player: {seatPlayer.name}
                  </span>
                ) : (
                  <>
                    <select
                      value={existing?.profile ?? ""}
                      onChange={(e) => {
                        const prev = (botSeats ?? []).filter((b) => b.seat !== seat);
                        if (e.target.value) {
                          prev.push({ seat, profile: e.target.value, modelVersion: existing?.modelVersion ?? "v2.1" });
                        }
                        updateField("botSeats", prev);
                      }}
                      className="input-field text-xs !py-1 flex-1"
                      disabled={readOnly}
                    >
                      <option value="">-- None --</option>
                      <option value="gto_balanced">GTO Balanced</option>
                      <option value="limp_fish">Limp-Fish (passive caller)</option>
                      <option value="tag">TAG (tight-aggressive)</option>
                      <option value="lag">LAG (loose-aggressive)</option>
                      <option value="nit">Nit (very tight)</option>
                    </select>
                    {existing && (
                      <select
                        value={existing.modelVersion ?? "v2.1"}
                        onChange={(e) => {
                          const updated = botSeats.map((b) =>
                            b.seat === seat ? { ...b, modelVersion: e.target.value } : b
                          );
                          updateField("botSeats", updated);
                        }}
                        className="input-field text-[10px] !py-1 w-16"
                        disabled={readOnly}
                      >
                        <option value="v0">V0</option>
                        <option value="v1">V1</option>
                        <option value="v2">V2 (latest)</option>
                        <option value="v2.1">V2.1 (300k)</option>
                        <option value="v2.2">V2.2 (full)</option>
                        <option value="v3">V3 (CFR)</option>
                      </select>
                    )}
                  </>
                )}

                {existing && !isOccupiedByHuman && (
                  <div className="flex items-center gap-1">
                    <span className="text-[9px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded">
                      Active
                    </span>
                    {isHost && seatPlayer && onBotAddChips && (
                      <button
                        onClick={() => {
                          const amount = prompt(`Add chips to ${seatPlayer.name} (Seat ${seat}):`, String(s.bigBlind * 50));
                          if (amount && Number(amount) > 0) {
                            onBotAddChips(seat, Number(amount));
                          }
                        }}
                        className="text-[9px] bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded hover:bg-blue-500/20 transition-colors"
                      >
                        +Chips
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          <div className="text-[10px] text-slate-500 mt-2 space-y-1">
            <p><span className="text-indigo-400 font-medium">V0</span> = Heuristic (rule-based, no ML model)</p>
            <p><span className="text-indigo-400 font-medium">V1</span> = Legacy trained MLP</p>
            <p><span className="text-indigo-400 font-medium">V2</span> = model-v2-latest (currently V2.1)</p>
            <p><span className="text-indigo-400 font-medium">V2.1</span> = 300k curated checkpoint</p>
            <p><span className="text-indigo-400 font-medium">V2.2</span> = full-data optimized checkpoint</p>
            <p><span className="text-indigo-400 font-medium">V3</span> = CFR solver trained (177M samples)</p>
          </div>
        </div>
      )}
    </div>
  );
}
