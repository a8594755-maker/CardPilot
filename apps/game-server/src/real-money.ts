export const REAL_MONEY_COMING_SOON_ERROR = {
  code: "COMING_SOON",
  message: "Real money is not available yet.",
} as const;

export type RealMoneyComingSoonErrorPayload = typeof REAL_MONEY_COMING_SOON_ERROR;

export class RealMoneyComingSoonError extends Error {
  code: RealMoneyComingSoonErrorPayload["code"];

  constructor(payload: RealMoneyComingSoonErrorPayload = REAL_MONEY_COMING_SOON_ERROR) {
    super(payload.message);
    this.name = "RealMoneyComingSoonError";
    this.code = payload.code;
  }
}

export function assertRealMoneyEnabled(enabled: boolean): void {
  if (!enabled) {
    throw new RealMoneyComingSoonError();
  }
}
