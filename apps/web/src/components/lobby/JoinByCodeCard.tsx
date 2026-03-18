import { memo, useState, useCallback, useRef, useEffect } from 'react';

export interface JoinByCodeProps {
  disabled: boolean;
  onJoin: (code: string) => void;
  error?: string | null;
}

export const JoinByCodeCard = memo(function JoinByCodeCard({
  disabled,
  onJoin,
  error,
}: JoinByCodeProps) {
  const [code, setCode] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const sanitize = useCallback((raw: string) => {
    return raw
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '')
      .slice(0, 8);
  }, []);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setCode(sanitize(e.target.value));
    },
    [sanitize],
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLInputElement>) => {
      e.preventDefault();
      const pasted = e.clipboardData.getData('text').trim();
      setCode(sanitize(pasted));
    },
    [sanitize],
  );

  const submit = useCallback(() => {
    const trimmed = code.trim();
    if (trimmed.length >= 4) {
      onJoin(trimmed);
    }
  }, [code, onJoin]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        submit();
      }
    },
    [submit],
  );

  // Auto-focus on mount for fast interaction
  useEffect(() => {
    // Don't steal focus on mobile
    if (window.innerWidth >= 640) {
      // small delay so layout settles
      const t = setTimeout(() => inputRef.current?.focus(), 300);
      return () => clearTimeout(t);
    }
  }, []);

  const canSubmit = !disabled && code.trim().length >= 4;

  return (
    <div className="cp-lobby-card">
      <h2 className="cp-lobby-title">Join with Code</h2>
      <p className="cp-lobby-subtitle mt-1">Got a room code? Paste it below.</p>

      <div className="flex items-center gap-2 mt-4">
        <input
          ref={inputRef}
          value={code}
          onChange={handleChange}
          onPaste={handlePaste}
          onKeyDown={handleKeyDown}
          placeholder="ROOM CODE"
          maxLength={8}
          disabled={disabled}
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          className="cp-lobby-input flex-1 font-mono text-center tracking-[0.22em] text-base uppercase"
          style={{ maxWidth: 220 }}
        />
        <button
          disabled={!canSubmit}
          onClick={submit}
          className="cp-btn cp-btn-primary shrink-0 text-[12px] px-3.5 py-1.5 min-h-[30px] rounded-md"
        >
          Join
        </button>
      </div>

      {error && <p className="mt-2 text-sm text-red-400 font-medium">{error}</p>}
    </div>
  );
});
