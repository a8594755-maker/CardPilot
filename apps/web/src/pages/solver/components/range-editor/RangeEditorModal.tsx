import { useCallback } from 'react';
import { Dialog, DialogContent } from '../ui/Dialog';
import { useRangeEditor } from '../../stores/range-editor';
import { RangeEditorMatrix } from './RangeEditorMatrix';
import { RangeTextInput } from './RangeTextInput';
import { WeightSlider } from './WeightSlider';
import { SavedRangesTree } from './SavedRangesTree';
import { countCombos } from '../../lib/range-parser';

export function RangeEditorModal() {
  const {
    isOpen,
    closeEditor,
    targetPlayer,
    selectedHands,
    weight,
    clearHands,
    selectTopXPercent,
  } = useRangeEditor();

  const totalCombos = countCombos(selectedHands);
  const pct = ((totalCombos / 1326) * 100).toFixed(1);
  const playerLabel = targetPlayer === 0 ? 'Range 1 (OOP)' : 'Range 2 (IP)';

  const handleSliderChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      selectTopXPercent(parseFloat(e.target.value));
    },
    [selectTopXPercent],
  );

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && closeEditor()}>
      <DialogContent title={`Range Editor - ${playerLabel}`} className="!max-w-[900px] !w-[900px]">
        <div className="flex min-h-[460px] -mx-4 -my-3">
          {/* Left panel: Matrix + Controls */}
          <div className="flex-1 p-4 flex flex-col gap-3">
            {/* Top controls: display mode toggle */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <label className="gto-label" style={{ fontSize: 11 }}>
                  Display Mode
                </label>
                <select
                  className="gto-input"
                  style={{ width: 80, fontSize: 11, padding: '2px 4px' }}
                >
                  <option>Mode 2</option>
                  <option>Mode 1</option>
                </select>
              </div>
              <select
                className="gto-input"
                style={{ width: 100, fontSize: 11, padding: '2px 4px' }}
              >
                <option>No limit</option>
              </select>
            </div>

            {/* Matrix */}
            <RangeEditorMatrix />

            {/* Range slider */}
            <div className="flex items-center gap-2">
              <div
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: '50%',
                  background: '#ef4444',
                  flexShrink: 0,
                }}
              />
              <input
                type="range"
                min={0}
                max={100}
                step={0.5}
                value={parseFloat(pct)}
                onChange={handleSliderChange}
                className="flex-1"
                style={{ accentColor: '#2980b9' }}
              />
              <span
                className="gto-label"
                style={{ fontSize: 11, color: '#2980b9', minWidth: 36, textAlign: 'right' }}
              >
                {pct}%
              </span>
            </div>

            {/* Range text input */}
            <RangeTextInput />

            {/* Bottom row: Clear + Done */}
            <div className="flex items-center gap-3">
              <button
                onClick={clearHands}
                className="gto-btn gto-btn-primary"
                style={{ minWidth: 80 }}
              >
                Clear
              </button>
              <button
                onClick={closeEditor}
                className="gto-btn gto-btn-primary"
                style={{ minWidth: 80 }}
              >
                Done
              </button>
            </div>
          </div>

          {/* Right panel: Saved Ranges + Weight/Combos */}
          <div className="w-[260px] flex-shrink-0 border-l border-[#ccc] flex flex-col">
            {/* Saved ranges tree */}
            <div className="flex-1 overflow-y-auto">
              <SavedRangesTree />
            </div>

            {/* Weight + Combo count */}
            <div className="border-t border-[#ccc] p-3 space-y-2">
              <div className="flex items-center gap-2">
                <span className="gto-label" style={{ fontSize: 12 }}>
                  Weight:
                </span>
                <WeightSlider />
                <span className="gto-label" style={{ fontSize: 12, fontFamily: 'monospace' }}>
                  {weight}%
                </span>
              </div>
              <div>
                <span className="gto-summary" style={{ fontSize: 12 }}>
                  {totalCombos.toFixed(2)} combos
                </span>
                <br />
                <span className="gto-label-muted">{pct}%</span>
              </div>
            </div>

            {/* Modifier keys */}
            <div className="border-t border-[#ccc] px-3 py-2 flex gap-1">
              <span
                className="px-2 py-0.5 text-[10px] rounded"
                style={{ background: '#ddd', color: '#333', border: '1px solid #bbb' }}
              >
                CTRL
              </span>
              <span
                className="px-2 py-0.5 text-[10px] rounded"
                style={{ background: '#ddd', color: '#333', border: '1px solid #bbb' }}
              >
                SHIFT
              </span>
              <span
                className="px-2 py-0.5 text-[10px] rounded"
                style={{ background: '#ddd', color: '#333', border: '1px solid #bbb' }}
              >
                CTRL+SHIFT
              </span>
            </div>

            {/* Bottom buttons */}
            <div className="border-t border-[#ccc] px-2 py-2 flex gap-1 flex-wrap">
              <button
                className="gto-btn gto-btn-primary"
                style={{ fontSize: 11, padding: '4px 10px' }}
              >
                Add Range
              </button>
              <button
                className="gto-btn gto-btn-secondary"
                style={{ fontSize: 11, padding: '4px 10px' }}
              >
                Rename
              </button>
              <button
                className="gto-btn gto-btn-secondary"
                style={{ fontSize: 11, padding: '4px 10px' }}
              >
                Delete
              </button>
              <button
                className="gto-btn gto-btn-primary"
                style={{ fontSize: 11, padding: '4px 10px' }}
              >
                Add Category
              </button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
