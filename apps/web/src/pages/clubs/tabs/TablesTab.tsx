import React, { useState, useCallback } from "react";
import type {
  Club,
  ClubTable,
  ClubRuleset,
} from "@cardpilot/shared-types";
import { EmptyState } from "../shared";
import type { ClubPermissions } from "../hooks/useClubPermissions";
import type { ClubSocketActions } from "../hooks/useClubSocket";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TablesTabProps {
  club: Club;
  tables: ClubTable[];
  rulesets: ClubRuleset[];
  permissions: ClubPermissions;
  actions: ClubSocketActions;
  onRenameTable: (tableId: string, currentName: string) => void;
  onCloseTable: (tableId: string, tableName: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const TablesTab = React.memo(function TablesTab({
  club,
  tables,
  rulesets,
  permissions,
  actions,
  onRenameTable,
  onCloseTable,
}: TablesTabProps) {
  const [showCreateTable, setShowCreateTable] = useState(false);
  const [newTableName, setNewTableName] = useState("");
  const [newTableRulesetId, setNewTableRulesetId] = useState("");

  const handleCreateTable = useCallback(() => {
    if (!newTableName.trim()) return;
    actions.createTable(newTableName.trim(), newTableRulesetId || undefined);
    setShowCreateTable(false);
    setNewTableName("");
    setNewTableRulesetId("");
  }, [actions, newTableName, newTableRulesetId]);

  return (
    <div className="space-y-3">
      {/* Create table form (collapsible) */}
      {permissions.canCreateTable && (
        <div className="space-y-2">
          {showCreateTable ? (
            <div className="p-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-2">
              <h4 className="text-xs font-semibold text-emerald-300">Create Table</h4>
              <input
                type="text"
                placeholder="Table name"
                value={newTableName}
                onChange={(e) => setNewTableName(e.target.value)}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                maxLength={80}
                autoFocus
              />
              {rulesets.length > 0 && (
                <div>
                  <label className="block text-[10px] text-slate-400 mb-0.5">Ruleset</label>
                  <select
                    value={newTableRulesetId}
                    onChange={(e) => setNewTableRulesetId(e.target.value)}
                    className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="">Default</option>
                    {rulesets.map((rs) => (
                      <option key={rs.id} value={rs.id}>
                        {rs.name} ({rs.rulesJson.stakes.smallBlind}/{rs.rulesJson.stakes.bigBlind})
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div className="flex gap-2">
                <button
                  onClick={handleCreateTable}
                  disabled={!newTableName.trim()}
                  className="btn-primary text-xs disabled:opacity-50"
                >
                  Create
                </button>
                <button
                  onClick={() => setShowCreateTable(false)}
                  className="btn-ghost text-xs"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowCreateTable(true)}
              className="btn-primary text-xs"
            >
              + New Table
            </button>
          )}
        </div>
      )}

      {/* Table list */}
      {tables.length === 0 ? (
        <EmptyState
          icon="\uD83C\uDCB4"
          title="No tables yet"
          description={
            permissions.canCreateTable
              ? "Create one to get started!"
              : "No tables have been created in this club yet."
          }
        />
      ) : (
        tables.map((t) => (
          <div
            key={t.id}
            className={`flex flex-col gap-3 rounded-2xl border p-3 sm:flex-row sm:items-center sm:gap-4 ${
              t.status === "open"
                ? "bg-emerald-500/5 border-emerald-500/20"
                : "bg-white/[0.02] border-white/5"
            }`}
          >
            {/* Player count badge */}
            <div
              className={`flex h-12 w-12 items-center justify-center rounded-xl text-sm font-bold border ${
                t.status === "open"
                  ? "bg-emerald-500/20 border-emerald-500/30 text-emerald-300"
                  : "bg-white/5 border-white/10 text-slate-500"
              }`}
            >
              {t.playerCount ?? 0}
            </div>

            {/* Table info */}
            <div className="flex-1 space-y-1">
              <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-sm font-semibold text-white">{t.name}</div>
                  <div className="text-[11px] text-slate-400">
                    {t.stakes ?? "\u2014"} · {t.playerCount ?? 0}/{t.maxPlayers ?? "\u2014"} players
                  </div>
                </div>
                <span className="text-[11px] font-medium uppercase text-amber-300">
                  {t.status === "open" &&
                  (t.playerCount ?? 0) < (t.minPlayersToStart ?? 2)
                    ? "Waiting for players"
                    : t.status}
                </span>
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
              {t.status === "open" && (
                <button
                  onClick={() => actions.joinTable(t.id)}
                  className="btn-success text-xs !py-1.5"
                >
                  Join Table
                </button>
              )}
              {permissions.canManageTables && t.status !== "closed" && (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <span className="text-[10px] text-slate-400">
                    {t.config?.smallBlind ?? 1}/{t.config?.bigBlind ?? 2} ·{" "}
                    {t.config?.maxSeats ?? 6}-max
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => onRenameTable(t.id, t.name)}
                      className="rounded px-2 py-1 text-[10px] text-cyan-300 hover:bg-cyan-500/10"
                    >
                      Edit
                    </button>
                    {permissions.canCloseTable && (
                      <button
                        onClick={() => onCloseTable(t.id, t.name)}
                        className="rounded px-2 py-1 text-[10px] text-red-300 hover:bg-red-500/10"
                      >
                        Close
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
});

export default TablesTab;
