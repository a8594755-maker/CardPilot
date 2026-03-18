import { useState, useEffect } from 'react';
import { useRangeEditor } from '../../stores/range-editor';
import { parseRange, handsToRange } from '../../lib/range-parser';

export function RangeTextInput() {
  const { selectedHands, setHands } = useRangeEditor();
  const [text, setText] = useState('');

  // Sync from selectedHands -> text
  useEffect(() => {
    const rangeStr = handsToRange(selectedHands);
    setText(rangeStr);
  }, [selectedHands]);

  function handleBlur() {
    const parsed = parseRange(text);
    setHands(Array.from(parsed));
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleBlur();
    }
  }

  return (
    <input
      type="text"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      placeholder="AA,AKs,AQs-A2s,KQo..."
      className="gto-input"
      style={{ fontSize: 11, fontFamily: "'Consolas', 'Courier New', monospace" }}
    />
  );
}
