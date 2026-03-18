import { useState } from 'react';
import { useSolverConfig } from '../../stores/solver-config';

export function ProfileManager() {
  const { profiles, saveProfile, loadProfile, deleteProfile } = useSolverConfig();
  const [newName, setNewName] = useState('');
  const [showSave, setShowSave] = useState(false);

  function handleSave() {
    if (!newName.trim()) return;
    saveProfile(newName.trim());
    setNewName('');
    setShowSave(false);
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-xs text-muted-foreground">Profiles</label>
        <button
          onClick={() => setShowSave(!showSave)}
          className="text-xs text-primary hover:underline"
        >
          {showSave ? 'Cancel' : '+ Save Current'}
        </button>
      </div>

      {showSave && (
        <div className="flex gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Profile name..."
            className="flex-1 px-2 py-1 bg-secondary border border-border rounded text-sm"
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
          />
          <button
            onClick={handleSave}
            disabled={!newName.trim()}
            className="px-3 py-1 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
          >
            Save
          </button>
        </div>
      )}

      {profiles.length === 0 ? (
        <p className="text-xs text-muted-foreground py-2">No saved profiles.</p>
      ) : (
        <div className="space-y-1 max-h-40 overflow-auto">
          {profiles.map((p) => (
            <div
              key={p.id}
              className="group flex items-center justify-between px-2 py-1.5 rounded hover:bg-secondary text-sm"
            >
              <button onClick={() => loadProfile(p.id)} className="flex-1 text-left truncate">
                {p.name}
              </button>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
                <span className="text-[10px] text-muted-foreground">
                  {new Date(p.createdAt).toLocaleDateString()}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteProfile(p.id);
                  }}
                  className="text-xs text-muted-foreground hover:text-destructive px-1"
                >
                  X
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
