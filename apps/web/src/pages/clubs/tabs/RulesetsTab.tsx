import React, { memo, useState } from 'react';
import type { Club, ClubRuleset, ClubGameType, ClubRules } from '@cardpilot/shared-types';
import { DEFAULT_CLUB_RULES } from '@cardpilot/shared-types';
import { RulesSummary } from '../shared';
import type { ClubPermissions } from '../hooks/useClubPermissions';
import type { ClubSocketActions } from '../hooks/useClubSocket';

// ── Props ──

interface RulesetsTabProps {
  club: Club;
  rulesets: ClubRuleset[];
  defaultRuleset: ClubRuleset | null;
  permissions: ClubPermissions;
  actions: ClubSocketActions;
  showToast: (msg: string) => void;
}

// ── Component ──

export const RulesetsTab = memo(function RulesetsTab({
  club,
  rulesets,
  defaultRuleset,
  permissions,
  actions,
  showToast,
}: RulesetsTabProps) {
  // ── Default-ruleset selector state ──
  const [selectedDefaultId, setSelectedDefaultId] = useState(defaultRuleset?.id ?? '');

  // ── Create-form visibility ──
  const [showForm, setShowForm] = useState(false);

  // ── Create-form field state ──
  const [formName, setFormName] = useState('');
  const [formSB, setFormSB] = useState(DEFAULT_CLUB_RULES.stakes.smallBlind);
  const [formBB, setFormBB] = useState(DEFAULT_CLUB_RULES.stakes.bigBlind);
  const [formMaxSeats, setFormMaxSeats] = useState(DEFAULT_CLUB_RULES.maxSeats);
  const [formActionTimer, setFormActionTimer] = useState(DEFAULT_CLUB_RULES.time.actionTimeSec);
  const [formGameType, setFormGameType] = useState<ClubGameType>(
    DEFAULT_CLUB_RULES.extras.gameType,
  );
  const [formMinBuyIn, setFormMinBuyIn] = useState(DEFAULT_CLUB_RULES.buyIn.minBuyIn);
  const [formMaxBuyIn, setFormMaxBuyIn] = useState(DEFAULT_CLUB_RULES.buyIn.maxBuyIn);
  const [formTimeBank, setFormTimeBank] = useState(DEFAULT_CLUB_RULES.time.timeBankSec);
  const [formSevenTwo, setFormSevenTwo] = useState(DEFAULT_CLUB_RULES.extras.sevenTwoBounty);
  const [formRunItTwice, setFormRunItTwice] = useState(DEFAULT_CLUB_RULES.runit.allowRunItTwice);
  const [formSetDefault, setFormSetDefault] = useState(false);

  // ── Handlers ──

  function handleApplyDefault() {
    if (!selectedDefaultId) return;
    actions.setDefaultRuleset(selectedDefaultId);
  }

  function handleCreate() {
    if (!formName.trim()) {
      showToast('Ruleset name is required');
      return;
    }

    const rulesJson: ClubRules = {
      ...DEFAULT_CLUB_RULES,
      stakes: { smallBlind: formSB, bigBlind: formBB },
      maxSeats: formMaxSeats,
      buyIn: {
        ...DEFAULT_CLUB_RULES.buyIn,
        minBuyIn: formMinBuyIn,
        maxBuyIn: formMaxBuyIn,
      },
      time: {
        ...DEFAULT_CLUB_RULES.time,
        actionTimeSec: formActionTimer,
        timeBankSec: formTimeBank,
      },
      extras: {
        ...DEFAULT_CLUB_RULES.extras,
        gameType: formGameType,
        sevenTwoBounty: formSevenTwo,
      },
      runit: {
        ...DEFAULT_CLUB_RULES.runit,
        allowRunItTwice: formRunItTwice,
      },
    };

    actions.createRuleset({
      clubId: club.id,
      name: formName.trim(),
      rulesJson,
      setDefault: formSetDefault,
    });

    // Reset form
    setFormName('');
    setFormSB(DEFAULT_CLUB_RULES.stakes.smallBlind);
    setFormBB(DEFAULT_CLUB_RULES.stakes.bigBlind);
    setFormMaxSeats(DEFAULT_CLUB_RULES.maxSeats);
    setFormActionTimer(DEFAULT_CLUB_RULES.time.actionTimeSec);
    setFormGameType(DEFAULT_CLUB_RULES.extras.gameType);
    setFormMinBuyIn(DEFAULT_CLUB_RULES.buyIn.minBuyIn);
    setFormMaxBuyIn(DEFAULT_CLUB_RULES.buyIn.maxBuyIn);
    setFormTimeBank(DEFAULT_CLUB_RULES.time.timeBankSec);
    setFormSevenTwo(DEFAULT_CLUB_RULES.extras.sevenTwoBounty);
    setFormRunItTwice(DEFAULT_CLUB_RULES.runit.allowRunItTwice);
    setFormSetDefault(false);
    setShowForm(false);
  }

  function handleCancel() {
    setShowForm(false);
  }

  // ── Render ──

  return (
    <div className="space-y-6">
      {/* ── Default Ruleset Selector ── */}
      {permissions.canManageRulesets && rulesets.length > 0 && (
        <div className="flex items-center gap-3">
          <label className="text-xs text-slate-400 whitespace-nowrap">Default ruleset:</label>
          <select
            value={selectedDefaultId}
            onChange={(e) => setSelectedDefaultId(e.target.value)}
            className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 outline-none focus:border-cyan-500"
          >
            <option value="">— None —</option>
            {rulesets.map((rs) => (
              <option key={rs.id} value={rs.id}>
                {rs.name}
              </option>
            ))}
          </select>
          <button
            onClick={handleApplyDefault}
            disabled={!selectedDefaultId}
            className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Apply
          </button>
        </div>
      )}

      {/* ── Create Ruleset (collapsible) ── */}
      {permissions.canManageRulesets && (
        <div className="rounded-lg border border-slate-700 bg-slate-800/50">
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-slate-300 hover:text-white transition-colors"
          >
            <span>Create Ruleset</span>
            <span className="text-slate-500">{showForm ? '−' : '+'}</span>
          </button>

          {showForm && (
            <div className="border-t border-slate-700 px-4 py-4 space-y-4">
              {/* Name */}
              <div>
                <label className="mb-1 block text-xs text-slate-400">Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. Friday Night 1/2"
                  className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                {/* SB */}
                <div>
                  <label className="mb-1 block text-xs text-slate-400">SB</label>
                  <input
                    type="number"
                    min={1}
                    value={formSB}
                    onChange={(e) => setFormSB(Number(e.target.value))}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
                  />
                </div>

                {/* BB */}
                <div>
                  <label className="mb-1 block text-xs text-slate-400">BB</label>
                  <input
                    type="number"
                    min={1}
                    value={formBB}
                    onChange={(e) => setFormBB(Number(e.target.value))}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
                  />
                </div>

                {/* Max Seats */}
                <div>
                  <label className="mb-1 block text-xs text-slate-400">Max Seats</label>
                  <select
                    value={formMaxSeats}
                    onChange={(e) => setFormMaxSeats(Number(e.target.value))}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
                  >
                    {[2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Action Timer */}
                <div>
                  <label className="mb-1 block text-xs text-slate-400">Action Timer (s)</label>
                  <input
                    type="number"
                    min={5}
                    value={formActionTimer}
                    onChange={(e) => setFormActionTimer(Number(e.target.value))}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
                  />
                </div>

                {/* Game Type */}
                <div>
                  <label className="mb-1 block text-xs text-slate-400">Game Type</label>
                  <select
                    value={formGameType}
                    onChange={(e) => setFormGameType(e.target.value as ClubGameType)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
                  >
                    <option value="texas">Texas Hold'em</option>
                    <option value="omaha">Omaha</option>
                  </select>
                </div>

                {/* Min Buy-In */}
                <div>
                  <label className="mb-1 block text-xs text-slate-400">Min Buy-In</label>
                  <input
                    type="number"
                    min={1}
                    value={formMinBuyIn}
                    onChange={(e) => setFormMinBuyIn(Number(e.target.value))}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
                  />
                </div>

                {/* Max Buy-In */}
                <div>
                  <label className="mb-1 block text-xs text-slate-400">Max Buy-In</label>
                  <input
                    type="number"
                    min={1}
                    value={formMaxBuyIn}
                    onChange={(e) => setFormMaxBuyIn(Number(e.target.value))}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
                  />
                </div>

                {/* Time Bank */}
                <div>
                  <label className="mb-1 block text-xs text-slate-400">Time Bank (s)</label>
                  <input
                    type="number"
                    min={0}
                    value={formTimeBank}
                    onChange={(e) => setFormTimeBank(Number(e.target.value))}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
                  />
                </div>

                {/* 7-2 Bounty */}
                <div>
                  <label className="mb-1 block text-xs text-slate-400">7-2 Bounty</label>
                  <input
                    type="number"
                    min={0}
                    value={formSevenTwo}
                    onChange={(e) => setFormSevenTwo(Number(e.target.value))}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
                  />
                </div>
              </div>

              {/* Checkboxes */}
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formRunItTwice}
                    onChange={(e) => setFormRunItTwice(e.target.checked)}
                    className="rounded border-slate-600 bg-slate-900 text-cyan-500 focus:ring-cyan-500"
                  />
                  Run-it-twice
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formSetDefault}
                    onChange={(e) => setFormSetDefault(e.target.checked)}
                    className="rounded border-slate-600 bg-slate-900 text-cyan-500 focus:ring-cyan-500"
                  />
                  Set as default
                </label>
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleCancel}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs text-slate-400 hover:text-slate-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  className="rounded-lg bg-cyan-600 px-4 py-2 text-xs font-medium text-white hover:bg-cyan-500 transition-colors"
                >
                  Create
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Ruleset Card List ── */}
      {rulesets.length === 0 ? (
        <div className="py-8 text-center text-xs text-slate-500">No rulesets created yet.</div>
      ) : (
        <div className="space-y-3">
          {rulesets.map((rs) => (
            <div
              key={rs.id}
              className="rounded-lg border border-slate-700 bg-slate-800/50 px-4 py-3 space-y-2"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-200">{rs.name}</span>
                {rs.isDefault && (
                  <span className="rounded-full bg-amber-600/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-400">
                    DEFAULT
                  </span>
                )}
              </div>

              <RulesSummary rules={rs.rulesJson} />

              {permissions.canManageRulesets && !rs.isDefault && (
                <button
                  onClick={() => actions.setDefaultRuleset(rs.id)}
                  className="text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors"
                >
                  Set as default
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

export default RulesetsTab;
