#!/usr/bin/env tsx
/**
 * Export one corrected Path-1 board into identity-bound v5.5 bridge-source rows.
 *
 * This is asset preparation only.  It never writes actor weights and never grants
 * H3 launch authority.  The input board is streamed twice: first for strict QA and
 * source identity, then for deterministic representative reconstruction.
 */

import { createHash } from 'node:crypto';
import {
  createReadStream,
  createWriteStream,
  existsSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { dirname, isAbsolute, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { createGunzip } from 'node:zlib';

import {
  buildBucketComboMap,
  deterministicSampleN,
  inferActionsFromHistory,
  mapCfrProbsToV55Actions,
  parseInfoSetKey,
  replayHistoryTrace,
} from './cfr-to-training-data.js';
import { getWeightedRangeCombos, loadHUSRPRanges } from '../integration/preflop-ranges.js';
import { calcBetAmount, calcRaiseAmount, getTreeConfig } from '../tree/tree-config.js';
import type { TreeConfig } from '../types.js';

export const SOURCE_SCHEMA = 'path1.v55_bridge_source.v2';
export const OOD_LABEL = 'SYNTHETIC_PATH1_SRP_ENTRY_OOD_NOT_DEPLOYMENT_REACHABLE';
export const FULL_SCOPE = 'FULL_BOARD_CORPUS';
export const SMOKE_SCOPE = 'SMOKE_PREFIX_ONLY_FORBIDDEN_TRAINING';
export const MAX_ROUNDING_RESIDUAL = 0.0050000001;
export const DESIGN_LOCK_V3_SHA256 =
  'fe8ae6ecb32829be62f9acd3acf0935df1ee3778b4761ebbf2c2d2b6f5f5832e';

type BridgeScope = typeof FULL_SCOPE | typeof SMOKE_SCOPE;
type Meta = {
  game: string;
  stack: string;
  config: string;
  boardId: number;
  flopCards: [number, number, number];
  iterations: number;
  bucketCount: number;
  infoSets: number;
};

type ComboEntry = { combo: [number, number]; turnCard?: number; riverCard?: number };

export type ProbabilityCorrection = {
  probabilities: number[];
  rawSum: number;
  residual: number;
  correctedIndex: number;
};

/** Restore only bounded three-decimal export residual; never erase action support. */
export function correctRoundedProbabilityMass(raw: unknown): ProbabilityCorrection {
  if (!Array.isArray(raw) || raw.length < 2 || raw.length > 16) {
    throw new Error('probabilities_action_count_out_of_contract');
  }
  const probabilities = raw.map((value) => Number(value));
  if (probabilities.some((value) => !Number.isFinite(value) || value < 0 || value > 1)) {
    throw new Error('invalid_probability');
  }
  const rawSum = probabilities.reduce((sum, value) => sum + value, 0);
  const residual = 1 - rawSum;
  if (Math.abs(residual) > MAX_ROUNDING_RESIDUAL) {
    throw new Error(`rounding_residual_out_of_contract:${residual}`);
  }
  let correctedIndex = 0;
  for (let i = 1; i < probabilities.length; i++) {
    if (probabilities[i] > probabilities[correctedIndex]) correctedIndex = i;
  }
  probabilities[correctedIndex] += residual;
  if (
    probabilities[correctedIndex] < -1e-12 ||
    probabilities[correctedIndex] > 1 + 1e-12 ||
    Math.abs(probabilities.reduce((sum, value) => sum + value, 0) - 1) > 1e-12
  ) {
    throw new Error('probability_residual_correction_failed');
  }
  probabilities[correctedIndex] = Math.min(1, Math.max(0, probabilities[correctedIndex]));
  return { probabilities, rawSum, residual, correctedIndex };
}

/** Bind every exact Path-1 action to its v5.5 actor slot using source-tree replay. */
export function actionSlotsForV55(
  historyKey: string,
  actions: string[],
  config = getTreeConfig('pipeline_srp_v3_200bb'),
) {
  return actions.map((_, actionIndex) => {
    const oneHot = actions.map((__, index) => (index === actionIndex ? 1 : 0));
    const mapped = mapCfrProbsToV55Actions(historyKey, actions, oneHot, config);
    const nonzero = mapped.flatMap((value, slot) => (value > 0 ? [slot] : []));
    if (nonzero.length !== 1 || mapped[nonzero[0]] !== 1) {
      throw new Error(`action_slot_mapping_not_one_hot:${actionIndex}`);
    }
    return nonzero[0];
  });
}

export function sourceActionDescriptors(historyKey: string, actions: string[], config: TreeConfig) {
  const state = replayHistoryTrace(historyKey, config).state;
  const sizes =
    state.street === 'FLOP'
      ? config.betSizes.flop
      : state.street === 'TURN'
        ? config.betSizes.turn
        : config.betSizes.river;
  const nominalSlots = actionSlotsForV55(historyKey, actions, config);
  return actions.map((action, index) => {
    let additionalAmount: number | null = null;
    if (action === 'allin') additionalAmount = state.stacks[state.currentPlayer];
    else {
      const matched = action.match(/^(bet|raise)_(\d+)$/);
      if (matched) {
        const sizeIndex = Number.parseInt(matched[2], 10);
        const fraction = sizes[sizeIndex];
        if (!Number.isFinite(fraction)) throw new Error(`missing_source_size:${action}`);
        additionalAmount =
          matched[1] === 'bet'
            ? calcBetAmount(state.pot, fraction, state.stacks[state.currentPlayer])
            : calcRaiseAmount(
                state.pot,
                state.facingBet,
                fraction,
                state.stacks[state.currentPlayer],
              );
      }
    }
    return {
      source_action_name: action,
      exact_additional_amount: additionalAmount,
      exact_amount_over_source_pot:
        additionalAmount === null ? null : additionalAmount / Math.max(state.pot, 1e-9),
      nominal_v55_slot: nominalSlots[index],
    };
  });
}

export function parseArgs(argv: string[]) {
  const value = (name: string): string => {
    const index = argv.indexOf(name);
    if (index < 0 || !argv[index + 1]) throw new Error(`missing ${name}`);
    return argv[index + 1];
  };
  const optionalNumber = (name: string, fallback: number): number => {
    const index = argv.indexOf(name);
    if (index < 0) return fallback;
    const parsed = Number(argv[index + 1]);
    if (!Number.isInteger(parsed) || parsed < 0) throw new Error(`invalid ${name}`);
    return parsed;
  };
  const gz = resolve(value('--board-gz'));
  const meta = resolve(value('--board-meta'));
  const output = resolve(value('--output-jsonl'));
  const manifest = resolve(value('--manifest'));
  const smokeRows = optionalNumber('--smoke-prefix-rows', 0);
  for (const path of [gz, meta, output, manifest]) {
    if (!isAbsolute(path)) throw new Error('all paths must be absolute');
  }
  if (smokeRows > 0 && smokeRows > 10_000)
    throw new Error('smoke prefix exceeds frozen 10000-row ceiling');
  return { gz, meta, output, manifest, smokeRows };
}

function openLines(path: string) {
  const raw = createReadStream(path);
  return createInterface({ input: raw.pipe(createGunzip()), crlfDelay: Infinity });
}

export async function strictBoardAudit(gzPath: string, meta: Meta) {
  const compressedSha = createHash('sha256');
  const rawForHash = createReadStream(gzPath);
  rawForHash.on('data', (chunk) => compressedSha.update(chunk));
  const hashDone = new Promise<void>((accept, reject) => {
    rawForHash.on('end', () => accept());
    rawForHash.on('error', reject);
  });
  let physicalRows = 0;
  let validRows = 0;
  let decisive = 0;
  let sumMax = 0;
  let illegalPostAllinRows = 0;
  let correctedRoundingRows = 0;
  let maxAbsResidual = 0;
  const streetPrefixCounts: Record<string, number> = { F: 0, T: 0, R: 0 };
  const streetPlayerActionCounts: Record<string, number> = {};
  for await (const line of openLines(gzPath)) {
    physicalRows++;
    if (!line.trim()) throw new Error(`blank_source_row:${physicalRows}`);
    let row: { key?: unknown; probs?: unknown };
    try {
      row = JSON.parse(line);
    } catch (error) {
      throw new Error(`invalid_json_row:${physicalRows}:${error}`);
    }
    if (typeof row.key !== 'string' || !/^[FTR]\|/.test(row.key)) {
      throw new Error(`source_key_schema_mismatch:${physicalRows}`);
    }
    const correction = correctRoundedProbabilityMass(row.probs);
    const keyParts = row.key.split('|');
    const streetPrefix = keyParts[0];
    const keyBoardId = Number.parseInt(keyParts[1], 10);
    const keyPlayer = Number.parseInt(keyParts[2], 10);
    if (
      keyParts.length !== 5 ||
      keyBoardId !== meta.boardId ||
      (keyPlayer !== 0 && keyPlayer !== 1)
    ) {
      throw new Error(`source_key_identity_mismatch:${physicalRows}`);
    }
    streetPrefixCounts[streetPrefix]++;
    const stratum = `${streetPrefix}|${keyPlayer}|${correction.probabilities.length}`;
    streetPlayerActionCounts[stratum] = (streetPlayerActionCounts[stratum] ?? 0) + 1;
    validRows++;
    if (Math.abs(correction.residual) > 1e-12) correctedRoundingRows++;
    maxAbsResidual = Math.max(maxAbsResidual, Math.abs(correction.residual));
    const max = Math.max(...correction.probabilities);
    sumMax += max;
    if (max >= 0.6) decisive++;
    const segment = row.key.split('|')[3]?.split('/').at(-1) ?? '';
    if (segment.endsWith('A') && correction.probabilities.length > 2) illegalPostAllinRows++;
  }
  await hashDone;
  const meanMax = validRows ? sumMax / validRows : 0;
  const decisiveRate = validRows ? decisive / validRows : 0;
  const metadataPass =
    meta.game === 'HU_NLHE_SRP' &&
    meta.stack === '200bb' &&
    meta.config === 'pipeline_srp_v3_200bb' &&
    Number.isInteger(meta.boardId) &&
    meta.boardId >= 0 &&
    Array.isArray(meta.flopCards) &&
    meta.flopCards.length === 3 &&
    new Set(meta.flopCards).size === 3 &&
    meta.iterations === 80_000 &&
    meta.bucketCount === 50 &&
    Number.isInteger(meta.infoSets) &&
    meta.infoSets > 100_000;
  const pass =
    metadataPass &&
    physicalRows === meta.infoSets &&
    validRows === meta.infoSets &&
    meanMax >= 0.55 &&
    decisiveRate >= 0.35 &&
    illegalPostAllinRows === 0;
  if (!pass) throw new Error('source_board_strict_qa_fail_closed');
  return {
    classification: 'CORRECTED_LEGAL_ALLIN_QA_PASS',
    compressedSha256: compressedSha.digest('hex'),
    physicalRows,
    validRows,
    meanMaxProbability: meanMax,
    decisiveRateGe0_6: decisiveRate,
    illegalPostAllinRows,
    correctedRoundingRows,
    maxAbsRoundingResidual: maxAbsResidual,
    streetPrefixCounts,
    streetPlayerActionCounts,
  };
}

function lookupRepresentative(
  maps: ReturnType<typeof buildBucketComboMap>,
  player: 0 | 1,
  street: string,
  bucketIdentity: string,
  seedKey: string,
): ComboEntry | null {
  const map = player === 0 ? maps.oopMap : maps.ipMap;
  let choices: ComboEntry[] | undefined;
  if (street === 'FLOP')
    choices = map.flop.get(Number.parseInt(bucketIdentity, 10))?.map((combo) => ({ combo }));
  else if (street === 'TURN') choices = map.turn.get(bucketIdentity);
  else if (street === 'RIVER') choices = map.river.get(bucketIdentity);
  if (!choices?.length) return null;
  return deterministicSampleN(choices, 1, seedKey)[0] ?? null;
}

function visibleBoard(flop: [number, number, number], street: string, representative: ComboEntry) {
  if (street === 'FLOP') return [...flop];
  if (street === 'TURN' && representative.turnCard !== undefined)
    return [...flop, representative.turnCard];
  if (
    street === 'RIVER' &&
    representative.turnCard !== undefined &&
    representative.riverCard !== undefined
  )
    return [...flop, representative.turnCard, representative.riverCard];
  throw new Error('representative_board_street_mismatch');
}

export async function exportBoard(
  gzPath: string,
  metaPath: string,
  outputPath: string,
  smokeRows: number,
) {
  const project = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../');
  const expectedRoot = resolve(project, 'data/cfr/pipeline_v3_hu_srp_200bb_legalallin_v2');
  if (dirname(gzPath) !== expectedRoot || dirname(metaPath) !== expectedRoot) {
    throw new Error('quarantined_or_unregistered_asset_root_forbidden');
  }
  if (!existsSync(gzPath) || !existsSync(metaPath)) throw new Error('source_board_pair_missing');
  if (existsSync(outputPath) || existsSync(`${outputPath}.partial`))
    throw new Error('refusing_to_overwrite_output');
  const meta = JSON.parse(readFileSync(metaPath, 'utf8')) as Meta;
  const expectedStem = `flop_${String(meta.boardId).padStart(3, '0')}`;
  if (
    !gzPath.endsWith(`${expectedStem}.jsonl.gz`) ||
    !metaPath.endsWith(`${expectedStem}.meta.json`)
  ) {
    throw new Error('board_pair_identity_mismatch');
  }
  const qa = await strictBoardAudit(gzPath, meta);
  const scope: BridgeScope = smokeRows > 0 ? SMOKE_SCOPE : FULL_SCOPE;
  const config = getTreeConfig('pipeline_srp_v3_200bb');
  const charts = resolve(project, 'data/preflop_charts.json');
  const { oopRange, ipRange } = loadHUSRPRanges(charts);
  const maps = buildBucketComboMap(
    meta.flopCards,
    getWeightedRangeCombos(oopRange),
    getWeightedRangeCombos(ipRange),
    meta.bucketCount,
    10,
    20260712,
  );
  const partial = `${outputPath}.partial`;
  const output = createWriteStream(partial, { flags: 'wx', encoding: 'utf8' });
  let sourceRow = 0;
  let outputRow = 0;
  let missingRepresentativeRows = 0;
  try {
    for await (const line of openLines(gzPath)) {
      if (smokeRows > 0 && sourceRow >= smokeRows) break;
      const row = JSON.parse(line) as { key: string; probs: number[] };
      const parsed = parseInfoSetKey(row.key);
      if (!parsed.street || parsed.boardId !== meta.boardId || ![0, 1].includes(parsed.player)) {
        throw new Error(`info_set_identity_mismatch:${sourceRow}`);
      }
      const actions = inferActionsFromHistory(parsed.historyKey, config);
      if (actions.length !== row.probs.length)
        throw new Error(`action_probability_length_mismatch:${sourceRow}`);
      const representative = lookupRepresentative(
        maps,
        parsed.player,
        parsed.street,
        parsed.bucketStr,
        `20260712|combo|${meta.boardId}|${row.key}`,
      );
      if (!representative) {
        missingRepresentativeRows++;
        throw new Error(`missing_representative:${sourceRow}:${row.key}`);
      }
      const boardCards = visibleBoard(meta.flopCards, parsed.street, representative);
      if (boardCards.some((card) => representative.combo.includes(card))) {
        throw new Error(`representative_card_conflict:${sourceRow}`);
      }
      const correction = correctRoundedProbabilityMass(row.probs);
      const replay = replayHistoryTrace(parsed.historyKey, config);
      const actionDescriptors = sourceActionDescriptors(parsed.historyKey, actions, config);
      const nominalV55ActorTarget = mapCfrProbsToV55Actions(
        parsed.historyKey,
        actions,
        correction.probabilities,
        config,
      );
      const bridge = {
        schema_version: SOURCE_SCHEMA,
        bridge_design_lock_v3_sha256: DESIGN_LOCK_V3_SHA256,
        bridge_scope: scope,
        board_id: meta.boardId,
        info_set_key: row.key,
        player: parsed.player,
        history_key: parsed.historyKey,
        bucket_identity: parsed.bucketStr,
        hole_cards: representative.combo,
        board_cards: boardCards,
        cfr_actions: actions,
        cfr_action_descriptors: actionDescriptors,
        cfr_probabilities: correction.probabilities,
        nominal_v55_actor_target: nominalV55ActorTarget,
        path1_state_snapshot: replay.state,
        path1_history_events: replay.events,
        source_probability_sum: correction.rawSum,
        rounding_residual: correction.residual,
        rounding_residual_action_index: correction.correctedIndex,
        source_file_sha256: qa.compressedSha256,
        source_row_ordinal: outputRow,
        source_strategy_row_ordinal: sourceRow,
        path1_asset_classification: qa.classification,
        required_provenance_label: OOD_LABEL,
      };
      if (!output.write(`${JSON.stringify(bridge)}\n`)) {
        await new Promise<void>((accept) => output.once('drain', accept));
      }
      sourceRow++;
      outputRow++;
    }
  } catch (error) {
    output.destroy();
    throw error;
  }
  await new Promise<void>((accept, reject) => {
    output.end(() => accept());
    output.on('error', reject);
  });
  if (outputRow === 0) throw new Error('empty_bridge_output');
  renameSync(partial, outputPath);
  return {
    schema_version: 'path1.v55_bridge_source.manifest.v3',
    status:
      scope === FULL_SCOPE ? 'PASS_FULL_BOARD_EXPORT' : 'PASS_SMOKE_PREFIX_FORBIDDEN_TRAINING',
    bridge_scope: scope,
    bridge_design_lock_v3_sha256: DESIGN_LOCK_V3_SHA256,
    source_board_gz: gzPath,
    source_board_meta: metaPath,
    source_board_sha256: qa.compressedSha256,
    source_qa: qa,
    output_jsonl: outputPath,
    output_rows: outputRow,
    missing_representative_rows: missingRepresentativeRows,
    selection_seed: 20260712,
    representatives_per_bucket: 1,
    actor_only: true,
    critic_rows: 0,
    training_eligible: scope === FULL_SCOPE,
    behavior_launch_authorized: false,
    official_hands_authorized: 0,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  let result: Record<string, unknown>;
  let exitCode = 0;
  try {
    result = await exportBoard(args.gz, args.meta, args.output, args.smokeRows);
  } catch (error) {
    const partial = `${args.output}.partial`;
    if (existsSync(partial)) renameSync(partial, `${partial}.failed-${Date.now()}`);
    result = {
      schema_version: 'path1.v55_bridge_source.manifest.v3',
      status: 'FAIL_CLOSED',
      error: String(error),
      behavior_launch_authorized: false,
      official_hands_authorized: 0,
    };
    exitCode = 2;
  }
  if (existsSync(args.manifest)) throw new Error('refusing_to_overwrite_manifest');
  const manifestPartial = `${args.manifest}.partial`;
  writeFileSync(manifestPartial, `${JSON.stringify(result, null, 2)}\n`, { flag: 'wx' });
  renameSync(manifestPartial, args.manifest);
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  process.exitCode = exitCode;
}

const isMain =
  process.argv[1] &&
  resolve(process.argv[1]).replace(/\\/g, '/').endsWith('/path1-to-v55-bridge-source.ts');
if (isMain)
  main().catch((error) => {
    process.stderr.write(`${error?.stack ?? error}\n`);
    process.exitCode = 1;
  });
