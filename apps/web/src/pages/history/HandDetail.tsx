import { useMemo, useState } from "react";
import type { HandActionRecord, HandRecord } from "../../lib/hand-history.js";

const STREETS = ["PREFLOP", "FLOP", "TURN", "RIVER"];
const EDITABLE_TAGS = ["SRP", "3bet_pot", "4bet_pot", "all_in"];

function cardsText(cards: string[]) {
  return cards.length ? cards.join(" ") : "—";
}

function createHandText(hand: HandRecord): string {
  const lines: string[] = [];
  lines.push(`CardPilot Hand #${hand.id}`);
  lines.push(`${new Date(hand.createdAt).toLocaleString()} · ${hand.gameType} ${hand.stakes} · ${hand.tableSize}-max`);
  lines.push(`Hero: ${hand.position} ${cardsText(hand.heroCards)}`);
  lines.push(`Board: ${cardsText(hand.board)}`);
  lines.push(`Pot: ${hand.potSize} | End Stack: ${hand.stackSize} | Result: ${hand.result ?? 0}`);
  lines.push(`Tags: ${hand.tags.join(", ") || "-"}`);
  lines.push("");
  for (const street of STREETS) {
    const actions = hand.actions.filter((a) => a.street.toUpperCase() === street);
    if (!actions.length) continue;
    lines.push(street);
    for (const a of actions) {
      lines.push(`Seat ${a.seat}: ${a.type}${a.amount > 0 ? ` ${a.amount}` : ""}`);
    }
    lines.push("");
  }
  return lines.join("\n").trim();
}

function splitBoard(board: string[]) {
  return {
    flop: board.slice(0, 3),
    turn: board.slice(3, 4),
    river: board.slice(4, 5),
  };
}

function streetGroups(actions: HandActionRecord[]) {
  return STREETS.map((street) => ({
    street,
    actions: actions.filter((a) => a.street.toUpperCase() === street),
  })).filter((g) => g.actions.length > 0);
}

export function HandDetail({
  hand,
  onCopy,
  onDownload,
  onToggleTag,
}: {
  hand: HandRecord | null;
  onCopy: (text: string) => void;
  onDownload: (hand: HandRecord) => void;
  onToggleTag: (tag: string) => void;
}) {
  const [customTag, setCustomTag] = useState("");

  const groupedActions = useMemo(() => (hand ? streetGroups(hand.actions) : []), [hand]);

  if (!hand) {
    return <div className="history-empty">Select a hand to view details.</div>;
  }

  const runouts = hand.runoutBoards && hand.runoutBoards.length > 0 ? hand.runoutBoards : [hand.board];
  const result = hand.result ?? 0;

  return (
    <div className="history-detail history-sheet-in">
      <div className="history-detail-top">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-400">Hero Cards</div>
          <div className="history-hero-cards">{hand.heroCards.map((c) => <span key={c}>{c}</span>)}</div>
        </div>
        <div className="history-summary-chips">
          <span>Pot {hand.potSize}</span>
          <span>Stack {hand.stackSize}</span>
          <span className={result > 0 ? "text-emerald-400" : result < 0 ? "text-red-400" : "text-slate-300"}>Net {result > 0 ? "+" : ""}{result}</span>
        </div>
      </div>

      <div className="history-board-wrap">
        {runouts.map((board, idx) => {
          const split = splitBoard(board);
          return (
            <div key={idx} className="history-board-line">
              {runouts.length > 1 ? <div className="text-[11px] text-slate-500 mb-1">Run {idx + 1}</div> : null}
              <div className="history-board-streets">
                <span>FLOP: <strong>{cardsText(split.flop)}</strong></span>
                <span>TURN: <strong>{cardsText(split.turn)}</strong></span>
                <span>RIVER: <strong>{cardsText(split.river)}</strong></span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="history-tag-row mb-2">
        {EDITABLE_TAGS.map((tag) => (
          <button key={tag} onClick={() => onToggleTag(tag)} className={`history-tag-chip ${hand.tags.includes(tag) ? "history-tag-chip-active" : ""}`}>
            {tag}
          </button>
        ))}
        <input
          className="input-field text-xs !py-1 !px-2 w-[110px]"
          value={customTag}
          placeholder="new tag"
          onChange={(e) => setCustomTag(e.target.value)}
        />
        <button
          className="btn-ghost text-xs !py-1 !px-2"
          onClick={() => {
            const tag = customTag.trim();
            if (!tag) return;
            if (!hand.tags.includes(tag)) onToggleTag(tag);
            setCustomTag("");
          }}
        >
          Add
        </button>
      </div>

      <div className="history-actions-wrap">
        {groupedActions.map((group) => (
          <div key={group.street} className="history-street-group">
            <div className="history-street-title">{group.street}</div>
            {group.actions.map((a, idx) => (
              <div key={`${group.street}_${idx}`} className="history-action-row">
                <span className="text-slate-400">Seat {a.seat}</span>
                <span className="text-white">{a.type.toUpperCase()}</span>
                <span className="ml-auto text-slate-300">{a.amount || "-"}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="history-detail-actions">
        <button className="btn-ghost text-xs !py-2 !px-3" onClick={() => onCopy(createHandText(hand))}>Copy</button>
        <button className="btn-ghost text-xs !py-2 !px-3" onClick={() => onDownload(hand)}>Download JSON</button>
      </div>
    </div>
  );
}
