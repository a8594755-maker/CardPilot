/** Compute evenly-spaced seat positions around an ellipse for the given player count.
 *  Seat 1 starts at bottom-center and proceeds clockwise. */
export function getSeatLayout(n: number): Record<number, { top: string; left: string }> {
  const cx = 50; // ellipse center X (%)
  const cy = 46; // ellipse center Y (%) — slightly above visual center of table image
  const rx = 40; // horizontal radius (%) (pulled inward)
  const ry = 30; // vertical radius (%) — reduced so hero seat clears the hero-strip cards below
  const result: Record<number, { top: string; left: string }> = {};
  for (let i = 0; i < n; i++) {
    // π/2 = bottom in screen coords; subtract to go clockwise
    const angle = Math.PI / 2 - (i * 2 * Math.PI) / n;
    result[i + 1] = {
      top: `${(cy + ry * Math.sin(angle)).toFixed(1)}%`,
      left: `${(cx + rx * Math.cos(angle)).toFixed(1)}%`,
    };
  }
  return result;
}

/** Portrait-first seat layout: tall oval for mobile portrait (PokerNow 1/1.8 canvas).
 *  Hero (seat 1) at bottom-center ~82%, opponents distributed on a tall vertical ellipse.
 *  Radii tuned for 500×900 portrait canvas so seats don't crowd the narrow width. */
export function getPortraitSeatLayout(n: number): Record<number, { top: string; left: string }> {
  const cx = 50;
  const cy = 50;
  const rx = 38; // narrower horizontal (portrait canvas is narrow)
  const ry = 36; // taller vertical spread — reduced to prevent bottom seats from being clipped
  const result: Record<number, { top: string; left: string }> = {};
  for (let i = 0; i < n; i++) {
    // π/2 = bottom in screen coords; subtract to go clockwise
    const angle = Math.PI / 2 - (i * 2 * Math.PI) / n;
    result[i + 1] = {
      top: `${(cy + ry * Math.sin(angle)).toFixed(1)}%`,
      left: `${(cx + rx * Math.cos(angle)).toFixed(1)}%`,
    };
  }
  return result;
}

export function mapSeatToVisualIndex(
  seatNum: number,
  heroSeat: number,
  maxPlayers: number,
): number {
  const normalizedSeat = (((seatNum - 1) % maxPlayers) + maxPlayers) % maxPlayers;
  const normalizedHero = (((heroSeat - 1) % maxPlayers) + maxPlayers) % maxPlayers;
  return ((normalizedSeat - normalizedHero + maxPlayers) % maxPlayers) + 1;
}
