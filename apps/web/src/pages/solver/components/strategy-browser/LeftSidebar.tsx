import type { GtoPlusSample } from '../../lib/api-client';
import { NodeActionDisplay } from './NodeActionDisplay';
import { TreeNavigator } from './TreeNavigator';
import { RangeSummaryBar } from './RangeSummaryBar';

interface LeftSidebarProps {
  source: string;
  files: GtoPlusSample[];
  selectedFile: string;
  onSelectFile: (file: string) => void;
  ipFile?: string;
  onSelectIpFile?: (file: string) => void;
}

export function LeftSidebar({
  source,
  files,
  selectedFile,
  onSelectFile,
  ipFile,
  onSelectIpFile,
}: LeftSidebarProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Tree Navigator */}
      <div className="flex-shrink-0 border-b border-border p-2">
        <TreeNavigator />
      </div>

      {/* Node Action Display */}
      <div className="flex-shrink-0 border-b border-border p-2">
        <NodeActionDisplay />
      </div>

      {/* Range 1 (OOP) */}
      <div className="border-b border-border p-2">
        <RangeSummaryBar label="範圍 1 (OOP)" player={0} />
      </div>

      {/* Range 2 (IP) */}
      <div className="border-b border-border p-2">
        <RangeSummaryBar label="範圍 2 (IP)" player={1} />
      </div>

      {/* File Selectors (GTO+ mode) */}
      {source === 'gtoplus' && files.length > 0 && (
        <>
          {/* OOP File */}
          <div className="p-2 border-b border-border">
            <div className="text-xs font-medium mb-1">玩家 1 (OOP)</div>
            <select
              value={selectedFile}
              onChange={(e) => onSelectFile(e.target.value)}
              className="w-full px-2 py-1 rounded-md bg-secondary border border-border text-xs"
            >
              {files.map((f) => (
                <option key={f.path} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
          </div>

          {/* IP File */}
          <div className="p-2 border-b border-border">
            <div className="text-xs font-medium mb-1">玩家 2 (IP)</div>
            <select
              value={ipFile || ''}
              onChange={(e) => onSelectIpFile?.(e.target.value)}
              className="w-full px-2 py-1 rounded-md bg-secondary border border-border text-xs"
            >
              <option value="">-- 無 --</option>
              {files.map((f) => (
                <option key={f.path} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
            {ipFile && (
              <div className="mt-1 flex items-center gap-1 text-[10px] text-green-500">
                <span>&#10003;</span> 已配對
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
