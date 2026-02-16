export function isRealMoneyEnabled(): boolean {
  const raw = import.meta.env.VITE_ENABLE_REAL_MONEY;
  if (typeof raw !== "string") return false;

  const normalized = raw.trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
}
