export function OnboardingModal({ onComplete }: { onComplete: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass-card p-8 w-full max-w-md mx-4 space-y-6">
        <div className="space-y-5 text-center">
          <div className="text-4xl">🚀</div>
          <h2 className="text-xl font-bold text-white">You're All Set!</h2>
          <p className="text-sm text-slate-400">
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
