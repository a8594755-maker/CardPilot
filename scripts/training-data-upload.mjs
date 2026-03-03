#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");

const defaults = {
  file: path.join(projectRoot, "data", "v2", "training-samples.jsonl"),
  key: "training/v2/training-samples.jsonl",
  manifest: path.join(projectRoot, "data", "metadata", "training-samples-v2.manifest.json"),
  envFile: path.join(projectRoot, "packages", "cfr-solver", "scripts", "cluster.env"),
};

function usage() {
  console.log("Usage: node scripts/training-data-upload.mjs [options]");
  console.log("");
  console.log("Options:");
  console.log("  --file <path>       Local JSONL file to upload");
  console.log("  --key <key>         Object key in E2 bucket");
  console.log("  --manifest <path>   Output manifest JSON path");
  console.log("  --env-file <path>   Env file with E2_PROFILE/E2_ENDPOINT/E2_BUCKET");
  console.log("  -h, --help          Show help");
}

function parseArgs(argv) {
  const out = { ...defaults };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "-h" || arg === "--help") {
      usage();
      process.exit(0);
    }
    if (arg === "--file") {
      out.file = argv[++i];
      continue;
    }
    if (arg === "--key") {
      out.key = argv[++i];
      continue;
    }
    if (arg === "--manifest") {
      out.manifest = argv[++i];
      continue;
    }
    if (arg === "--env-file") {
      out.envFile = argv[++i];
      continue;
    }
    throw new Error(`Unknown argument: ${arg}`);
  }
  return out;
}

function normalizePath(p) {
  if (!p) return p;
  return path.isAbsolute(p) ? p : path.join(projectRoot, p);
}

async function readEnvFile(envFilePath) {
  const raw = await fs.readFile(envFilePath, "utf8");
  const env = {};
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match) continue;
    let [, key, value] = match;
    value = value.trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

function ensureAwsCliAvailable(env) {
  const probe = spawnSync("aws", ["--version"], { env, encoding: "utf8" });
  if (probe.error || probe.status !== 0) {
    throw new Error("aws CLI not found in PATH");
  }
}

function runAws(args, env) {
  const result = spawnSync("aws", args, {
    stdio: "inherit",
    env,
  });
  if (result.error || result.status !== 0) {
    throw new Error(`aws command failed: aws ${args.join(" ")}`);
  }
}

async function sha256File(filePath) {
  const hash = createHash("sha256");
  const stream = createReadStream(filePath);
  for await (const chunk of stream) {
    hash.update(chunk);
  }
  return hash.digest("hex");
}

function nowIsoUtc() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  options.file = normalizePath(options.file);
  options.manifest = normalizePath(options.manifest);
  options.envFile = normalizePath(options.envFile);

  await fs.access(options.file);
  await fs.access(options.envFile);

  const fileEnv = await readEnvFile(options.envFile);
  const runtimeEnv = { ...process.env, ...fileEnv };

  const profile = runtimeEnv.E2_PROFILE;
  const endpoint = runtimeEnv.E2_ENDPOINT;
  const bucket = runtimeEnv.E2_BUCKET;
  if (!profile || !endpoint || !bucket) {
    throw new Error("Missing E2_PROFILE/E2_ENDPOINT/E2_BUCKET in env file");
  }

  ensureAwsCliAvailable(runtimeEnv);

  const stat = await fs.stat(options.file);
  const sha256 = await sha256File(options.file);
  const s3Object = `s3://${bucket}/${options.key}`;

  console.log("Uploading training dataset");
  console.log(`  file:    ${options.file}`);
  console.log(`  object:  ${s3Object}`);
  console.log(`  size:    ${stat.size} bytes`);
  console.log(`  sha256:  ${sha256}`);

  runAws(
    [
      "s3",
      "--profile",
      profile,
      "--endpoint-url",
      endpoint,
      "cp",
      options.file,
      s3Object,
    ],
    runtimeEnv,
  );

  const manifest = {
    version: 1,
    dataset: "training-samples-v2",
    updated: nowIsoUtc(),
    backend: "idrive-e2",
    object: {
      bucketEnv: "E2_BUCKET",
      key: options.key,
    },
    localPath: "data/v2/training-samples.jsonl",
    sizeBytes: stat.size,
    sha256,
  };

  await fs.mkdir(path.dirname(options.manifest), { recursive: true });
  await fs.writeFile(options.manifest, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

  console.log("Upload complete.");
  console.log(`Manifest updated: ${options.manifest}`);
}

main().catch((error) => {
  console.error(`ERROR: ${error.message}`);
  process.exit(1);
});
