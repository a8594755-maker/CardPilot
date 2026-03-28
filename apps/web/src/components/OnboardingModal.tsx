export function OnboardingModal({ onComplete }: { onComplete: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm">
      <div
        className="glass-card p-8 w-full max-w-md mx-4 space-y-6"
        style={{ animation: 'fadeSlideUp 300ms var(--cp-ease-out)' }}
      >
        <div className="space-y-5 text-center">
          <div
            className="w-14 h-14 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center mx-auto shadow-lg"
            style={{ boxShadow: '0 8px 24px rgba(217, 119, 6, 0.3)' }}
          >
            <svg
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <h2 className="text-xl font-extrabold text-white tracking-tight">You're All Set!</h2>
          <p className="text-sm text-slate-400 leading-relaxed">
            Head to the lobby to create or join a room and start playing. The host will decide the
            table settings.
          </p>
          <button onClick={onComplete} className="btn-success w-full !py-3 text-base font-bold">
            Start Playing
          </button>
        </div>
      </div>
    </div>
  );
}
