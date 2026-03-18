import { useState } from 'react';
import { useRangeEditor } from '../../stores/range-editor';

export function SavedRangesTree() {
  const { savedCategories, setHands } = useRangeEditor();

  const [expandedCategories, setExpandedCategories] = useState<Set<number>>(
    new Set(savedCategories.map((_, i) => i)),
  );

  function toggleCategory(index: number) {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return (
    <div className="p-3 space-y-1">
      {savedCategories.map((category, catIdx) => (
        <div key={catIdx}>
          {/* Category Header */}
          <button
            className="flex items-center gap-1 text-xs font-medium w-full text-left py-1"
            style={{ color: '#333' }}
            onClick={() => toggleCategory(catIdx)}
          >
            <span style={{ fontSize: 10 }}>
              {expandedCategories.has(catIdx) ? '\u229F' : '\u229E'}
            </span>
            <span style={{ color: '#1a7a7a', fontWeight: 600 }}>{category.name}</span>
          </button>

          {/* Ranges */}
          {expandedCategories.has(catIdx) && (
            <div className="ml-4 space-y-0.5">
              {category.ranges.map((range, rangeIdx) => (
                <div
                  key={rangeIdx}
                  className="flex items-center gap-2 text-xs py-0.5 cursor-pointer rounded px-1"
                  style={{ color: '#333' }}
                  onClick={() => setHands(range.hands)}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLDivElement).style.background = '#ddd';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLDivElement).style.background = '';
                  }}
                >
                  <span
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: range.color }}
                  />
                  <span className="flex-1 truncate" style={{ fontSize: 12 }}>
                    {range.name}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
