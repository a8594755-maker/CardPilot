import { NumericInput } from '../ui/NumericInput';

interface Column {
  key: string;
  label: string;
  narrow?: boolean;
}

interface PlayerTableProps {
  columns: Column[];
  rows: Record<string, number>[];
  maxRows: number;
  onUpdate: (index: number, key: string, value: number) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  startingPot: number;
  onStartingPotChange: (pot: number) => void;
  totals: Record<string, number>;
  totalLabels: Record<string, string>;
}

export function PlayerTable({
  columns,
  rows,
  maxRows,
  onUpdate,
  onAdd,
  onRemove,
  startingPot,
  onStartingPotChange,
  totals,
  totalLabels,
}: PlayerTableProps) {
  const emptyCount = Math.max(0, Math.min(4, maxRows - rows.length));

  return (
    <div style={{ padding: '12px 8px' }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, marginBottom: 8 }}>
        <div style={{ width: 64, flexShrink: 0 }} />
        {columns.map((col) => (
          <div
            key={col.key}
            style={{
              flex: col.narrow ? '0 0 48px' : 1,
              fontSize: 12,
              fontWeight: 600,
              color: '#555',
              textAlign: 'center',
            }}
          >
            {col.label}
          </div>
        ))}
        <div
          style={{
            width: 90,
            flexShrink: 0,
            fontSize: 12,
            fontWeight: 600,
            color: '#555',
            textAlign: 'center',
          }}
        >
          Starting Pot
        </div>
      </div>

      {/* Player rows */}
      {rows.map((row, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <div
            style={{ width: 64, flexShrink: 0, fontSize: 13, color: '#333', textAlign: 'right' }}
          >
            Player{i + 1}:
          </div>
          {columns.map((col) => (
            <div key={col.key} style={{ flex: col.narrow ? '0 0 48px' : 1 }}>
              <NumericInput
                value={row[col.key] ?? 0}
                onChange={(v) => onUpdate(i, col.key, v)}
                className={`gto-input ${i === 0 ? 'gto-input-blue' : i === 1 ? 'gto-input-green' : ''}`}
                style={{ textAlign: 'center' }}
              />
            </div>
          ))}
          {i === 0 ? (
            <div style={{ width: 90, flexShrink: 0 }}>
              <NumericInput
                value={startingPot}
                onChange={(v) => onStartingPotChange(v)}
                min={0}
                className="gto-input"
                style={{ textAlign: 'center' }}
              />
            </div>
          ) : (
            <div style={{ width: 90, flexShrink: 0 }} />
          )}
        </div>
      ))}

      {/* Empty rows */}
      {Array.from({ length: emptyCount }).map((_, i) => (
        <div
          key={`empty-${i}`}
          style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}
        >
          <div style={{ width: 64, flexShrink: 0 }} />
          {columns.map((col) => (
            <div key={col.key} style={{ flex: col.narrow ? '0 0 48px' : 1 }}>
              <input
                type="number"
                disabled
                className="gto-input"
                style={{ textAlign: 'center', background: '#e8e8e8', borderColor: '#ccc' }}
              />
            </div>
          ))}
          <div style={{ width: 90, flexShrink: 0 }}>
            <input
              type="number"
              disabled
              className="gto-input"
              style={{ textAlign: 'center', background: '#e8e8e8', borderColor: '#ccc' }}
            />
          </div>
        </div>
      ))}

      {/* Add / remove controls */}
      <div style={{ display: 'flex', gap: 12, marginTop: 8, marginLeft: 72 }}>
        {rows.length < maxRows && (
          <button
            onClick={onAdd}
            style={{
              fontSize: 12,
              color: '#2980b9',
              cursor: 'pointer',
              background: 'none',
              border: 'none',
            }}
          >
            + Add Player
          </button>
        )}
        {rows.length > 2 && (
          <button
            onClick={() => onRemove(rows.length - 1)}
            style={{
              fontSize: 12,
              color: '#c0392b',
              cursor: 'pointer',
              background: 'none',
              border: 'none',
            }}
          >
            - Remove Last
          </button>
        )}
      </div>

      {/* Totals */}
      <div style={{ marginTop: 12, paddingTop: 8, borderTop: '1px solid #ccc' }}>
        {Object.entries(totalLabels).map(([key, label]) => (
          <div key={key} className="gto-summary" style={{ marginBottom: 2 }}>
            {label}: {(totals[key] ?? 0).toLocaleString()}
          </div>
        ))}
      </div>
    </div>
  );
}
