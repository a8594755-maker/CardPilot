import { useState, useEffect } from 'react';

interface RenameTableModalProps {
  isOpen: boolean;
  currentName: string;
  onSubmit: (newName: string) => void;
  onClose: () => void;
}

export function RenameTableModal({
  isOpen,
  currentName,
  onSubmit,
  onClose,
}: RenameTableModalProps) {
  const [name, setName] = useState(currentName);

  useEffect(() => {
    setName(currentName);
  }, [currentName]);

  const isValid = name.trim() !== '' && name.trim() !== currentName;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="glass-card p-6 w-full max-w-md mx-4 space-y-4">
        <h3 className="text-lg font-bold text-white">Rename Table</h3>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            maxLength={80}
            autoFocus
          />
        </div>

        <div className="flex gap-2 pt-2">
          <button onClick={onClose} className="flex-1 btn-secondary text-sm">
            Cancel
          </button>
          <button
            onClick={() => {
              if (isValid) {
                onSubmit(name.trim());
              }
            }}
            disabled={!isValid}
            className="flex-1 btn-primary text-sm disabled:opacity-50"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
