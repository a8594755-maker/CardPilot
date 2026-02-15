type LogLevel = "info" | "warn" | "error";

type LogPayload = {
  event: string;
  tableId?: string;
  handId?: string | null;
  seat?: number;
  userId?: string;
  message?: string;
  [key: string]: unknown;
};

function write(level: LogLevel, payload: LogPayload): void {
  const entry = {
    ts: new Date().toISOString(),
    level,
    ...payload,
  };
  const line = JSON.stringify(entry);

  if (level === "error") {
    console.error(line);
    return;
  }

  if (level === "warn") {
    console.warn(line);
    return;
  }

  console.log(line);
}

export function logInfo(payload: LogPayload): void {
  write("info", payload);
}

export function logWarn(payload: LogPayload): void {
  write("warn", payload);
}

export function logError(payload: LogPayload): void {
  write("error", payload);
}
