const DEBUG_LOGS_ENABLED = import.meta.env.DEV;

export const debugLog = (...args: unknown[]) => {
  if (DEBUG_LOGS_ENABLED) console.log(...args);
};
