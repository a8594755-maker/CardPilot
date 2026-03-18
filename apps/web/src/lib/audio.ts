export type UiSfx = 'deal' | 'flip' | 'chipBet' | 'chipWin' | 'turn' | 'actionConfirm' | 'bounty72';

const SFX_VOLUME_MULTIPLIER = 2.5;

let sharedAudioCtx: AudioContext | null = null;

export function getAudioCtx(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const Ctx =
    window.AudioContext ||
    (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return null;
  if (!sharedAudioCtx) sharedAudioCtx = new Ctx();
  if (sharedAudioCtx.state === 'suspended') {
    void sharedAudioCtx.resume().catch(() => {});
  }
  return sharedAudioCtx;
}

export function playUiSfxTone(kind: UiSfx, muted: boolean) {
  if (muted) return;
  const ctx = getAudioCtx();
  if (!ctx) return;
  const now = ctx.currentTime;
  const out = ctx.createGain();
  out.gain.value = 0.05 * SFX_VOLUME_MULTIPLIER;
  out.connect(ctx.destination);

  const pulse = (
    freq: number,
    start: number,
    duration: number,
    type: OscillatorType = 'sine',
    gain = 0.24,
  ) => {
    const osc = ctx.createOscillator();
    const env = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, start);
    env.gain.setValueAtTime(0.0001, start);
    env.gain.exponentialRampToValueAtTime(gain, start + 0.012);
    env.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    osc.connect(env);
    env.connect(out);
    osc.start(start);
    osc.stop(start + duration + 0.02);
  };

  if (kind === 'deal') {
    pulse(520, now, 0.05, 'triangle', 0.18);
    pulse(660, now + 0.055, 0.05, 'triangle', 0.16);
    return;
  }
  if (kind === 'flip') {
    pulse(740, now, 0.06, 'square', 0.1);
    return;
  }
  if (kind === 'chipBet') {
    pulse(220, now, 0.06, 'triangle', 0.18);
    return;
  }
  if (kind === 'chipWin') {
    pulse(420, now, 0.07, 'triangle', 0.14);
    pulse(560, now + 0.06, 0.08, 'triangle', 0.14);
    return;
  }
  if (kind === 'actionConfirm') {
    pulse(880, now, 0.04, 'sine', 0.12);
    return;
  }
  if (kind === 'bounty72') {
    // Rising three-note fanfare for 7-2 bounty
    pulse(440, now, 0.08, 'triangle', 0.2);
    pulse(554, now + 0.1, 0.08, 'triangle', 0.2);
    pulse(880, now + 0.2, 0.12, 'sine', 0.24);
    return;
  }
  pulse(300, now, 0.08, 'sine', 0.2); // turn
}
