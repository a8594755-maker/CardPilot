interface DialogFooterProps {
  onSaveDefault?: () => void;
  onClose: () => void;
  onBuildTree?: () => void;
  memoryEstimate?: string;
}

export function DialogFooter({
  onSaveDefault,
  onClose,
  onBuildTree,
  memoryEstimate,
}: DialogFooterProps) {
  return (
    <div className="gto-footer -mx-4 -mb-3 mt-3">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {onSaveDefault && (
          <button onClick={onSaveDefault} className="gto-btn gto-btn-primary">
            Save as Default
          </button>
        )}
        {memoryEstimate && (
          <span className="gto-summary" style={{ fontSize: 12 }}>
            Estimated memory: {memoryEstimate}
          </span>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={onClose} className="gto-btn gto-btn-secondary">
          Close
        </button>
        {onBuildTree && (
          <button onClick={onBuildTree} className="gto-btn gto-btn-primary">
            Build Tree
          </button>
        )}
      </div>
    </div>
  );
}
