import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const configModuleUrl = pathToFileURL(resolve(process.cwd(), "src/config.ts")).href;
const tsxLoaderUrl = pathToFileURL(resolve(process.cwd(), "../../node_modules/tsx/dist/loader.mjs")).href;
const probeScript = `
import { getRuntimeConfig } from "${configModuleUrl}";
const cfg = getRuntimeConfig();
console.log(JSON.stringify({
  enableRealMoney: cfg.enableRealMoney,
  url: process.env.SUPABASE_URL ?? null,
  anon: process.env.SUPABASE_ANON_KEY ?? null,
  service: process.env.SUPABASE_SERVICE_ROLE_KEY ?? null
}));
`;

function runConfigProbe(extraEnv: Record<string, string | undefined>) {
  const workingDir = mkdtempSync(resolve(tmpdir(), "cardpilot-config-test-"));
  try {
    const env: NodeJS.ProcessEnv = { ...process.env, NODE_ENV: "development" };
    delete env.SUPABASE_URL;
    delete env.SUPABASE_ANON_KEY;
    delete env.SUPABASE_SERVICE_ROLE_KEY;
    delete env.SUPABASE_STRICT_ENV;

    for (const [key, value] of Object.entries(extraEnv)) {
      if (typeof value === "undefined") {
        delete env[key];
      } else {
        env[key] = value;
      }
    }

    return spawnSync("node", ["--import", tsxLoaderUrl, "-e", probeScript], {
      cwd: workingDir,
      env,
      encoding: "utf-8",
    });
  } finally {
    rmSync(workingDir, { recursive: true, force: true });
  }
}

function parseLastJsonLine(stdout: string): { enableRealMoney: boolean; url: string | null; anon: string | null; service: string | null } {
  const lastLine = stdout.trim().split("\n").at(-1);
  assert.ok(lastLine, "expected probe output");
  return JSON.parse(lastLine);
}

describe("Runtime config Supabase env handling", () => {
  it("falls back to guest/local mode when Supabase env is partially configured", () => {
    const result = runConfigProbe({
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_ANON_KEY: "sb_publishable_test",
    });

    assert.equal(result.status, 0, result.stderr);
    const parsed = parseLastJsonLine(result.stdout);
    assert.deepEqual(parsed, { enableRealMoney: false, url: null, anon: null, service: null });
    assert.match(`${result.stdout}\n${result.stderr}`, /Supabase disabled; falling back to guest\/local mode/);
  });

  it("fails fast when strict mode is enabled and Supabase env is partial", () => {
    const result = runConfigProbe({
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_ANON_KEY: "sb_publishable_test",
      SUPABASE_STRICT_ENV: "true",
    });

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /Incomplete Supabase env/);
  });

  it("keeps Supabase env intact when all required keys are set", () => {
    const result = runConfigProbe({
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_ANON_KEY: "sb_publishable_test",
      SUPABASE_SERVICE_ROLE_KEY: "sb_service_role_test",
    });

    assert.equal(result.status, 0, result.stderr);
    const parsed = parseLastJsonLine(result.stdout);
    assert.deepEqual(parsed, {
      enableRealMoney: false,
      url: "https://example.supabase.co",
      anon: "sb_publishable_test",
      service: "sb_service_role_test",
    });
  });

  it("defaults ENABLE_REAL_MONEY to false", () => {
    const result = runConfigProbe({ ENABLE_REAL_MONEY: undefined });
    assert.equal(result.status, 0, result.stderr);
    const parsed = parseLastJsonLine(result.stdout);
    assert.equal(parsed.enableRealMoney, false);
  });

  it("parses ENABLE_REAL_MONEY=true", () => {
    const result = runConfigProbe({ ENABLE_REAL_MONEY: "true" });
    assert.equal(result.status, 0, result.stderr);
    const parsed = parseLastJsonLine(result.stdout);
    assert.equal(parsed.enableRealMoney, true);
  });
});
