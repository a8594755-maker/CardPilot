import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = process.cwd();
const ENV_FILE_CANDIDATES = [
  ".env",
  ".env.local",
  "apps/game-server/.env",
  "apps/game-server/.env.local",
  "apps/web/.env",
  "apps/web/.env.local",
];

const REQUIRED_SERVER_KEYS = [
  "SUPABASE_URL",
  "SUPABASE_ANON_KEY",
  "SUPABASE_SERVICE_ROLE_KEY",
];

const REQUIRED_WEB_KEYS = [
  "VITE_SERVER_URL",
  "VITE_SUPABASE_URL",
  "VITE_SUPABASE_ANON_KEY",
];

const HEALTH_TIMEOUT_MS = 5000;

function parseArgs(argv) {
  let serverUrlOverride = "";
  for (let i = 2; i < argv.length; i++) {
    const token = argv[i];
    if (token === "--server-url") {
      const next = argv[i + 1];
      if (next && !next.startsWith("--")) {
        serverUrlOverride = next.trim();
        i += 1;
      }
      continue;
    }
    if (token.startsWith("--server-url=")) {
      serverUrlOverride = token.slice("--server-url=".length).trim();
    }
  }
  return { serverUrlOverride };
}

function parseDotEnv(content) {
  const output = {};
  for (const rawLine of content.split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx < 1) continue;
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    if (
      (value.startsWith("\"") && value.endsWith("\"")) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    output[key] = value;
  }
  return output;
}

function loadResolvedEnv() {
  const resolved = { ...process.env };
  const loadedFiles = [];

  for (const relPath of ENV_FILE_CANDIDATES) {
    const fullPath = resolve(ROOT, relPath);
    if (!existsSync(fullPath)) continue;
    const parsed = parseDotEnv(readFileSync(fullPath, "utf-8"));
    for (const [key, value] of Object.entries(parsed)) {
      if (!resolved[key]) {
        resolved[key] = value;
      }
    }
    loadedFiles.push(relPath);
  }

  return { env: resolved, loadedFiles };
}

function hasValue(env, key) {
  const raw = env[key];
  return typeof raw === "string" && raw.trim().length > 0;
}

function isHttpUrl(raw) {
  if (!raw || typeof raw !== "string") return false;
  try {
    const u = new URL(raw);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function mark(ok) {
  return ok ? "PASS" : "FAIL";
}

function warnMark(ok) {
  return ok ? "PASS" : "WARN";
}

function printSection(title) {
  console.log(`\n=== ${title} ===`);
}

function checkServerEnv(env) {
  printSection("Railway / Server Env");
  const setCount = REQUIRED_SERVER_KEYS.filter((key) => hasValue(env, key)).length;

  for (const key of REQUIRED_SERVER_KEYS) {
    console.log(`[${mark(hasValue(env, key))}] ${key}`);
  }

  let failed = false;
  if (setCount !== 0 && setCount !== REQUIRED_SERVER_KEYS.length) {
    failed = true;
    console.log("[FAIL] Server Supabase keys are partially configured. Set all 3 or none.");
  } else if (setCount === 0) {
    failed = true;
    console.log("[FAIL] Server Supabase keys are all missing. Production club persistence will not work.");
  } else {
    console.log("[PASS] Server Supabase keys are complete.");
  }

  const supabaseUrl = env.SUPABASE_URL;
  const supabaseUrlOk = isHttpUrl(supabaseUrl);
  console.log(`[${warnMark(supabaseUrlOk)}] SUPABASE_URL format`);
  if (!supabaseUrlOk) {
    failed = true;
    console.log("[FAIL] SUPABASE_URL is not a valid http/https URL.");
  }

  return { failed };
}

function checkWebEnv(env) {
  printSection("Netlify / Web Env");
  for (const key of REQUIRED_WEB_KEYS) {
    console.log(`[${mark(hasValue(env, key))}] ${key}`);
  }

  let failed = false;
  const serverUrl = env.VITE_SERVER_URL ?? "";
  if (!hasValue(env, "VITE_SERVER_URL")) {
    failed = true;
    console.log("[FAIL] VITE_SERVER_URL is empty. Production web cannot reach backend.");
  } else if (!isHttpUrl(serverUrl)) {
    failed = true;
    console.log("[FAIL] VITE_SERVER_URL is not a valid http/https URL.");
  } else {
    const u = new URL(serverUrl);
    const httpsOk = u.protocol === "https:";
    console.log(`[${warnMark(httpsOk)}] VITE_SERVER_URL uses HTTPS`);
    if (!httpsOk) {
      console.log("[WARN] VITE_SERVER_URL is not HTTPS. Browser security/CORS may fail in production.");
    }
    const pointsToLocal =
      u.hostname === "localhost" ||
      u.hostname === "127.0.0.1" ||
      u.hostname === "0.0.0.0";
    if (pointsToLocal) {
      failed = true;
      console.log("[FAIL] VITE_SERVER_URL points to localhost. This is not deploy-ready.");
    }
  }

  if (hasValue(env, "VITE_SUPABASE_URL") && hasValue(env, "SUPABASE_URL")) {
    const same = env.VITE_SUPABASE_URL === env.SUPABASE_URL;
    console.log(`[${warnMark(same)}] VITE_SUPABASE_URL matches SUPABASE_URL`);
    if (!same) {
      console.log("[WARN] Frontend and backend Supabase URLs differ.");
    }
  }

  return { failed };
}

async function checkHealthz(env, serverUrlOverride) {
  printSection("Runtime Health");

  const base = serverUrlOverride || (env.VITE_SERVER_URL || "").trim() || "http://127.0.0.1:4000";
  let healthzUrl = "";
  try {
    healthzUrl = new URL("/healthz", base).toString();
  } catch {
    console.log("[FAIL] Cannot build healthz URL from VITE_SERVER_URL.");
    return { failed: true };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  try {
    const res = await fetch(healthzUrl, { signal: controller.signal });
    if (!res.ok) {
      console.log(`[FAIL] healthz HTTP ${res.status} at ${healthzUrl}`);
      return { failed: true };
    }
    const data = await res.json();
    const enabled = data?.supabaseEnabled === true;
    console.log(`[${mark(enabled)}] GET ${healthzUrl} -> supabaseEnabled=${String(data?.supabaseEnabled)}`);
    if (!enabled) {
      console.log("[FAIL] supabaseEnabled is not true.");
      return { failed: true };
    }
    return { failed: false };
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    console.log(`[FAIL] Cannot reach ${healthzUrl}: ${msg}`);
    return { failed: true };
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  const { serverUrlOverride } = parseArgs(process.argv);
  console.log("CardPilot Env Doctor");
  const { env, loadedFiles } = loadResolvedEnv();
  console.log(
    loadedFiles.length > 0
      ? `Loaded env files: ${loadedFiles.join(", ")}`
      : "Loaded env files: (none)"
  );

  const server = checkServerEnv(env);
  const web = checkWebEnv(env);
  const runtime = await checkHealthz(env, serverUrlOverride);

  const hasFail = server.failed || web.failed || runtime.failed;
  printSection("Summary");
  if (hasFail) {
    console.log("[FAIL] Deployment readiness check failed.");
    process.exitCode = 1;
  } else {
    console.log("[PASS] Environment looks deploy-ready.");
  }
}

await main();
