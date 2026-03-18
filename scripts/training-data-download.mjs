#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..');

const defaults = {
  manifest: path.join(projectRoot, 'data', 'metadata', 'training-samples-v2.manifest.json'),
  envFile: path.join(projectRoot, 'packages', 'cfr-solver', 'scripts', 'cluster.env'),
  output: '',
  force: false,
  skipVerify: false,
};

function usage() {
  console.log('Usage: node scripts/training-data-download.mjs [options]');
  console.log('');
  console.log('Options:');
  console.log('  --manifest <path>   Manifest JSON path');
  console.log('  --output <path>     Override output file path');
  console.log('  --env-file <path>   Env file with E2_PROFILE/E2_ENDPOINT/E2_BUCKET');
  console.log('  --force             Re-download even if local file exists');
  console.log('  --skip-verify       Skip SHA256 and size verification');
  console.log('  -h, --help          Show help');
}

function parseArgs(argv) {
  const out = { ...defaults };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '-h' || arg === '--help') {
      usage();
      process.exit(0);
    }
    if (arg === '--manifest') {
      out.manifest = argv[++i];
      continue;
    }
    if (arg === '--output') {
      out.output = argv[++i];
      continue;
    }
    if (arg === '--env-file') {
      out.envFile = argv[++i];
      continue;
    }
    if (arg === '--force') {
      out.force = true;
      continue;
    }
    if (arg === '--skip-verify') {
      out.skipVerify = true;
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
  const raw = await fs.readFile(envFilePath, 'utf8');
  const env = {};
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
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
  const probe = spawnSync('aws', ['--version'], { env, encoding: 'utf8' });
  if (probe.error || probe.status !== 0) {
    throw new Error('aws CLI not found in PATH');
  }
}

function runAws(args, env) {
  const result = spawnSync('aws', args, {
    stdio: 'inherit',
    env,
  });
  if (result.error || result.status !== 0) {
    throw new Error(`aws command failed: aws ${args.join(' ')}`);
  }
}

async function sha256File(filePath) {
  const hash = createHash('sha256');
  const stream = createReadStream(filePath);
  for await (const chunk of stream) {
    hash.update(chunk);
  }
  return hash.digest('hex');
}

async function verifyFile(filePath, expectedSize, expectedSha256) {
  const stat = await fs.stat(filePath);
  if (Number(stat.size) !== Number(expectedSize)) {
    throw new Error(`Size mismatch for ${filePath}. expected=${expectedSize} actual=${stat.size}`);
  }
  const actualSha256 = await sha256File(filePath);
  if (actualSha256.toLowerCase() !== String(expectedSha256).toLowerCase()) {
    throw new Error(
      `SHA256 mismatch for ${filePath}. expected=${expectedSha256} actual=${actualSha256}`,
    );
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  options.manifest = normalizePath(options.manifest);
  options.envFile = normalizePath(options.envFile);

  await fs.access(options.manifest);
  await fs.access(options.envFile);

  const manifest = JSON.parse(await fs.readFile(options.manifest, 'utf8'));
  const objectKey = manifest?.object?.key;
  const expectedSha256 = manifest?.sha256;
  const expectedSize = manifest?.sizeBytes;
  const defaultLocalPath = manifest?.localPath;
  if (!objectKey || !expectedSha256 || expectedSize == null || !defaultLocalPath) {
    throw new Error('Manifest is missing object.key/localPath/sizeBytes/sha256');
  }

  const outputPath = normalizePath(options.output || defaultLocalPath);

  const fileEnv = await readEnvFile(options.envFile);
  const runtimeEnv = { ...process.env, ...fileEnv };

  const profile = runtimeEnv.E2_PROFILE;
  const endpoint = runtimeEnv.E2_ENDPOINT;
  const bucket = runtimeEnv.E2_BUCKET;
  if (!profile || !endpoint || !bucket) {
    throw new Error('Missing E2_PROFILE/E2_ENDPOINT/E2_BUCKET in env file');
  }

  ensureAwsCliAvailable(runtimeEnv);

  const s3Object = `s3://${bucket}/${objectKey}`;
  const outputDir = path.dirname(outputPath);
  const tmpFile = `${outputPath}.tmp`;

  try {
    await fs.access(outputPath);
    if (!options.force) {
      console.log(`Local file already exists: ${outputPath}`);
      if (options.skipVerify) {
        console.log('Skipping verification and download.');
        return;
      }
      try {
        await verifyFile(outputPath, expectedSize, expectedSha256);
        console.log('Existing file matches manifest. Skipping download.');
        return;
      } catch {
        throw new Error('Existing file does not match manifest. Re-run with --force to overwrite.');
      }
    }
  } catch (error) {
    const notFound =
      error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT';
    if (!notFound && !String(error.message || '').includes('does not match manifest')) {
      throw error;
    }
    if (!notFound) {
      throw error;
    }
  }

  await fs.mkdir(outputDir, { recursive: true });

  console.log('Downloading training dataset');
  console.log(`  object: ${s3Object}`);
  console.log(`  output: ${outputPath}`);
  runAws(
    ['s3', '--profile', profile, '--endpoint-url', endpoint, 'cp', s3Object, tmpFile],
    runtimeEnv,
  );

  try {
    if (!options.skipVerify) {
      await verifyFile(tmpFile, expectedSize, expectedSha256);
    }
    await fs.rename(tmpFile, outputPath);
  } catch (error) {
    await fs.rm(tmpFile, { force: true });
    throw error;
  }

  console.log(`Download complete: ${outputPath}`);
}

main().catch((error) => {
  console.error(`ERROR: ${error.message}`);
  process.exit(1);
});
