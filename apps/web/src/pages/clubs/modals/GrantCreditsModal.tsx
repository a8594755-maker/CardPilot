import { useState, useEffect, useMemo } from "react";
import type { ClubMember } from "@cardpilot/shared-types";

interface GrantCreditsModalProps {
  isOpen: boolean;
  members: ClubMember[];
  preselectedUserId?: string;
  preselectedDisplayName?: string;
  onSubmit: (userId: string, amount: number, note: string) => void;
  onClose: () => void;
}

export function GrantCreditsModal({
  isOpen,
  members,
  preselectedUserId,
  preselectedDisplayName,
  onSubmit,
  onClose,
}: GrantCreditsModalProps) {
  const [selectedUserId, setSelectedUserId] = useState("");
  const [amount, setAmount] = useState<number | "">("");
  const [note, setNote] = useState("");
  const [searchFilter, setSearchFilter] = useState("");

  // Pre-fill selectedUserId when modal opens or preselectedUserId changes
  useEffect(() => {
    if (isOpen) {
      setSelectedUserId(preselectedUserId ?? "");
      setAmount("");
      setNote("");
      setSearchFilter("");
    }
  }, [isOpen, preselectedUserId]);

  const filteredMembers = useMemo(() => {
    if (!searchFilter.trim()) return members;
    const lower = searchFilter.toLowerCase();
    return members.filter(
      (m) =>
        (m.displayName ?? "").toLowerCase().includes(lower) ||
        m.userId.toLowerCase().includes(lower),
    );
  }, [members, searchFilter]);

  const selectedDisplay =
    preselectedUserId === selectedUserId && preselectedDisplayName
      ? preselectedDisplayName
      : members.find((m) => m.userId === selectedUserId)?.displayName ??
        selectedUserId.slice(0, 8);

  const isValid = selectedUserId !== "" && typeof amount === "number" && amount > 0;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="glass-card p-6 w-full max-w-md mx-4 space-y-4">
        <h3 className="text-lg font-bold text-white">Grant Credits</h3>

        {/* Member select */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">Member</label>
          <input
            type="text"
            placeholder="Search members..."
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            className="w-full px-3 py-2 mb-1 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <select
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value)}
            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="" disabled>
              Select a member
            </option>
            {filteredMembers.map((m) => (
              <option key={m.userId} value={m.userId}>
                {m.displayName ?? m.userId.slice(0, 8)} ({m.userId.slice(0, 8)})
              </option>
            ))}
          </select>
          {selectedUserId && (
            <div className="text-[10px] text-slate-500 mt-1">
              Selected: {selectedDisplay}
            </div>
          )}
        </div>

        {/* Amount */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">Amount</label>
          <input
            type="number"
            placeholder="Enter amount"
            value={amount}
            onChange={(e) => {
              const v = e.target.value;
              setAmount(v === "" ? "" : Number(v));
            }}
            min={1}
            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        {/* Note */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">
            Note <span className="text-slate-600">(optional)</span>
          </label>
          <textarea
            placeholder="Reason for granting credits"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            rows={2}
            maxLength={500}
          />
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          <button onClick={onClose} className="flex-1 btn-secondary text-sm">
            Cancel
          </button>
          <button
            onClick={() => {
              if (isValid) {
                onSubmit(selectedUserId, amount as number, note.trim());
              }
            }}
            disabled={!isValid}
            className="flex-1 btn-primary text-sm disabled:opacity-50"
          >
            Grant
          </button>
        </div>
      </div>
    </div>
  );
}
