#!/usr/bin/env tsx
/**
 * Quick smoke test: verify the WASM CFR module loads and both solvers work.
 */
import { isWasmAvailable } from '../vectorized/wasm-cfr-bridge.js';

console.log('WASM available:', isWasmAvailable());

if (!isWasmAvailable()) {
  console.error('WASM module not found. Build with emcmake first.');
  process.exit(1);
}

async function main() {
  const { createRequire } = await import('module');
  const { join, dirname } = await import('path');
  const { fileURLToPath } = await import('url');
  const __dirname = dirname(fileURLToPath(import.meta.url));
  const _require = createRequire(import.meta.url);
  const WASM_JS_PATH = join(__dirname, '..', '..', 'build', 'cpp', 'cfr_core.cjs');

  const createModule = _require(WASM_JS_PATH);
  const module = await createModule();

  // CfrSolver (full-game)
  console.log('CfrSolver available:', typeof module.CfrSolver);
  const cfrSolver = new module.CfrSolver();
  console.log('CfrSolver instantiated:', !!cfrSolver);
  cfrSolver.destroy();

  // StreetSolver (per-street, used by real-time resolver)
  console.log('StreetSolver available:', typeof module.StreetSolver);
  if (module.StreetSolver) {
    const streetSolver = new module.StreetSolver();
    console.log('StreetSolver instantiated:', !!streetSolver);
    streetSolver.destroy();
  } else {
    console.error('StreetSolver NOT available — real-time resolver will use TS fallback!');
    process.exit(1);
  }

  console.log('Smoke test PASSED (both CfrSolver + StreetSolver)');
}

main().catch((err) => {
  console.error('Smoke test FAILED:', err.message);
  process.exit(1);
});
