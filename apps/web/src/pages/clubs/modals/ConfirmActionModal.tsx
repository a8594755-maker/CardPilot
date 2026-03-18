interface ConfirmActionModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  confirmVariant?: 'danger' | 'primary';
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmActionModal({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  confirmVariant = 'danger',
  onConfirm,
  onCancel,
}: ConfirmActionModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="glass-card p-6 w-full max-w-md mx-4 space-y-4">
        <h3 className="text-lg font-bold text-white">{title}</h3>
        <p className="text-sm text-slate-300">{message}</p>
        <div className="flex gap-2 pt-2">
          <button onClick={onCancel} className="flex-1 btn-secondary text-sm">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 text-sm ${
              confirmVariant === 'danger' ? 'btn-danger' : 'btn-primary'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
