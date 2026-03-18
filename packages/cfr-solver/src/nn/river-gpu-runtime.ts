import { existsSync, readFileSync } from 'fs';
import type { NNRiverValueFn } from '../vectorized/wasm-cfr-bridge.js';
import { getActiveWasmModule } from '../vectorized/wasm-cfr-bridge.js';

const NUM_COMBOS = 1326;

export interface RiverGpuRuntimeOptions {
  modelPath?: string;
  verbose?: boolean;
}

export interface RiverGpuRuntime {
  /**
   * Human-readable backend label.
   * Examples: "exact-fallback", "json-combo-table-legacy".
   */
  provider: string;
  /**
   * True when nnRiverValueFn is usable in WASM solve params.
   * False means caller should run exact river evaluation.
   */
  enabled: boolean;
  /**
   * Callback for WASM NN slot. Present only when enabled=true.
   */
  callback?: NNRiverValueFn;
  /**
   * Optional message explaining why runtime is disabled.
   */
  reason?: string;
  dispose(): Promise<void>;
}

interface JsonComboTable {
  comboValues?: number[];
}

function loadLegacyComboTable(modelPath: string): Float32Array | null {
  if (!existsSync(modelPath)) return null;
  if (!modelPath.toLowerCase().endsWith('.json')) return null;
  try {
    const raw = readFileSync(modelPath, 'utf8');
    const parsed = JSON.parse(raw) as JsonComboTable;
    if (!parsed.comboValues || parsed.comboValues.length !== NUM_COMBOS) return null;
    return new Float32Array(parsed.comboValues);
  } catch {
    return null;
  }
}

/**
 * Creates the runtime used by the WASM NN river callback slot.
 *
 * IMPORTANT:
 * - `riverEvalMode=nn` should never silently downgrade to heuristic approximation.
 * - If a supported native NN backend is unavailable, we return `enabled=false`
 *   so caller can execute exact river evaluation.
 */
export async function createRiverGpuRuntime(
  options: RiverGpuRuntimeOptions,
): Promise<RiverGpuRuntime> {
  const verbose = options.verbose ?? false;
  const modelPath = options.modelPath?.trim();

  if (!modelPath) {
    return {
      provider: 'exact-fallback',
      enabled: false,
      reason: 'nnModel path not provided',
      dispose: async () => {},
    };
  }

  // Future native route:
  // True CUDA ORT/TensorRT inference requires native C++ backend wiring.
  // WASM cannot execute CUDA kernels directly.
  if (modelPath.toLowerCase().endsWith('.onnx')) {
    if (verbose) {
      console.log(
        `  [NN] ONNX model '${modelPath}' requested, but native ORT CUDA ` +
          'backend is not attached to WASM callback path yet; using exact fallback.',
      );
    }
    return {
      provider: 'exact-fallback',
      enabled: false,
      reason: 'native ORT CUDA backend not available on WASM path',
      dispose: async () => {},
    };
  }

  // Back-compat only. Disabled by default to avoid accidental approximation.
  const allowLegacy = process.env.EZ_GTO_ALLOW_LEGACY_JSON_NN === '1';
  if (!allowLegacy) {
    return {
      provider: 'exact-fallback',
      enabled: false,
      reason: 'legacy json NN disabled; set EZ_GTO_ALLOW_LEGACY_JSON_NN=1 to enable',
      dispose: async () => {},
    };
  }

  const comboTable = loadLegacyComboTable(modelPath);
  if (!comboTable) {
    return {
      provider: 'exact-fallback',
      enabled: false,
      reason: `unsupported model format or invalid file: ${modelPath}`,
      dispose: async () => {},
    };
  }

  if (verbose) {
    console.log(`  [NN] Loaded legacy JSON combo table from ${modelPath}`);
  }

  const callback: NNRiverValueFn = (
    _boardPtr,
    _boardLen,
    _turnCard,
    potOffset,
    startingPot,
    _effectiveStack,
    turnNC,
    comboGlobalIdsPtr,
    oopReachPtr,
    ipReachPtr,
    traverser,
    outEVPtr,
  ) => {
    const module = getActiveWasmModule();
    if (!module) return;

    const comboBase = comboGlobalIdsPtr >> 2;
    const oopBase = oopReachPtr >> 2;
    const ipBase = ipReachPtr >> 2;
    const outBase = outEVPtr >> 2;
    const potScale = Math.max(0.01, startingPot + potOffset);
    const sign = traverser === 0 ? 1 : -1;

    for (let i = 0; i < turnNC; i++) {
      const gid = module.HEAP32[comboBase + i];
      const oop = module.HEAPF32[oopBase + i];
      const ip = module.HEAPF32[ipBase + i];
      const reachDelta = oop - ip;
      const prior = comboTable[gid];

      module.HEAPF32[outBase + i] = sign * potScale * (0.65 * prior + 0.35 * reachDelta);
    }
  };

  return {
    provider: 'json-combo-table-legacy',
    enabled: true,
    callback,
    dispose: async () => {},
  };
}
