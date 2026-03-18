import test from 'node:test';
import assert from 'node:assert/strict';
import {
  recognizeLines,
  detectPreflopAggressor,
  classifyActionDeviation,
  type LineTag,
} from '../line-recognition.js';
import type { HandAction } from '@cardpilot/shared-types';

// ── Helpers ──

function action(
  seat: number,
  street: 'PREFLOP' | 'FLOP' | 'TURN' | 'RIVER',
  type: HandAction['type'],
  amount: number,
  at: number,
): HandAction {
  return { seat, street, type, amount, at };
}

function hasTags(result: { lineTags: LineTag[] }, expected: LineTag[]): void {
  for (const tag of expected) {
    assert.ok(
      result.lineTags.includes(tag),
      `Expected tag "${tag}" not found. Got: [${result.lineTags.join(', ')}]`,
    );
  }
}

function lacksTag(result: { lineTags: LineTag[] }, tag: LineTag): void {
  assert.ok(
    !result.lineTags.includes(tag),
    `Tag "${tag}" should NOT be present. Got: [${result.lineTags.join(', ')}]`,
  );
}

const BB = 100;
const SEATS = [1, 2, 3, 4, 5, 6];

// ── Preflop aggressor detection ──

test('detectPreflopAggressor: single open = SRP, seat is raiser', () => {
  const actions: HandAction[] = [
    action(1, 'PREFLOP', 'post_sb', 50, 1),
    action(2, 'PREFLOP', 'post_bb', 100, 2),
    action(3, 'PREFLOP', 'raise', 250, 3),
    action(4, 'PREFLOP', 'fold', 0, 4),
    action(5, 'PREFLOP', 'fold', 0, 5),
    action(2, 'PREFLOP', 'call', 150, 6),
  ];
  const result = detectPreflopAggressor(actions);
  assert.equal(result.seat, 3);
  assert.equal(result.potType, 'SRP');
});

test('detectPreflopAggressor: 3bet = 3BP', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(4, 'PREFLOP', 'raise', 700, 2),
    action(3, 'PREFLOP', 'call', 450, 3),
  ];
  const result = detectPreflopAggressor(actions);
  assert.equal(result.seat, 4);
  assert.equal(result.potType, '3BP');
});

test('detectPreflopAggressor: 4bet = 4BP', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(4, 'PREFLOP', 'raise', 700, 2),
    action(3, 'PREFLOP', 'raise', 1800, 3),
    action(4, 'PREFLOP', 'call', 1100, 4),
  ];
  const result = detectPreflopAggressor(actions);
  assert.equal(result.seat, 3);
  assert.equal(result.potType, '4BP');
});

test('detectPreflopAggressor: limped pot', () => {
  const actions: HandAction[] = [
    action(1, 'PREFLOP', 'post_sb', 50, 1),
    action(2, 'PREFLOP', 'post_bb', 100, 2),
    action(3, 'PREFLOP', 'call', 100, 3),
    action(2, 'PREFLOP', 'check', 0, 4),
  ];
  const result = detectPreflopAggressor(actions);
  assert.equal(result.seat, null);
  assert.equal(result.potType, 'LIMPED');
});

// ── Preflop line tags ──

test('LIMP: hero calls without prior raise', () => {
  const actions: HandAction[] = [
    action(1, 'PREFLOP', 'post_sb', 50, 1),
    action(2, 'PREFLOP', 'post_bb', 100, 2),
    action(3, 'PREFLOP', 'call', 100, 3), // hero limps
    action(2, 'PREFLOP', 'check', 0, 4),
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 3,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['LIMP']);
});

test('THREE_BET: hero re-raises single open', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(4, 'PREFLOP', 'raise', 700, 2), // hero 3bets
    action(3, 'PREFLOP', 'call', 450, 3),
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 4,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['THREE_BET']);
});

test('SQUEEZE: hero 3bets after open + cold call', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(4, 'PREFLOP', 'call', 250, 2), // cold call
    action(5, 'PREFLOP', 'raise', 900, 3), // hero squeezes
    action(3, 'PREFLOP', 'fold', 0, 4),
    action(4, 'PREFLOP', 'fold', 0, 5),
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 5,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['SQUEEZE']);
});

test('FOUR_BET_PLUS: hero 4bets', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(4, 'PREFLOP', 'raise', 700, 2),
    action(3, 'PREFLOP', 'raise', 1800, 3), // hero 4bets
    action(4, 'PREFLOP', 'call', 1100, 4),
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 3,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['FOUR_BET_PLUS']);
});

test('COLD_4BET: hero enters with 4bet without prior aggression', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(4, 'PREFLOP', 'raise', 700, 2),
    action(5, 'PREFLOP', 'raise', 1800, 3), // hero cold 4bets
    action(3, 'PREFLOP', 'fold', 0, 4),
    action(4, 'PREFLOP', 'call', 1100, 5),
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 5,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['FOUR_BET_PLUS', 'COLD_4BET']);
});

// ── Postflop line tags ──

test('CBET: PFA bets flop', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'check', 0, 3),
    action(3, 'FLOP', 'raise', 300, 4), // PFA cbets
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 3,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['CBET']);
});

test('DELAYED_CBET: PFA checks flop, bets turn', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'check', 0, 3),
    action(3, 'FLOP', 'check', 0, 4), // PFA checks flop
    action(2, 'TURN', 'check', 0, 5),
    action(3, 'TURN', 'raise', 400, 6), // PFA bets turn
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 3,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['DELAYED_CBET']);
  lacksTag(result, 'CBET');
});

test('DONK_BET: non-PFA bets before PFA acts', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'raise', 300, 3), // non-PFA donks
    action(3, 'FLOP', 'call', 300, 4),
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 2,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['DONK_BET']);
});

test('PROBE: non-PFA bets after PFA checks on same street', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'check', 0, 3),
    action(3, 'FLOP', 'check', 0, 4),
    action(3, 'TURN', 'check', 0, 5), // PFA checks turn
    action(2, 'TURN', 'raise', 300, 6), // non-PFA probes turn
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 2,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['PROBE']);
});

test('CHECK_RAISE: hero checks then raises after opponent bet', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'check', 0, 3), // hero checks
    action(3, 'FLOP', 'raise', 300, 4), // opponent bets
    action(2, 'FLOP', 'raise', 900, 5), // hero check-raises
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 2,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['CHECK_RAISE']);
});

test('XR_TURN: check-raise on the turn', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'check', 0, 3),
    action(3, 'FLOP', 'check', 0, 4),
    action(2, 'TURN', 'check', 0, 5),
    action(3, 'TURN', 'raise', 400, 6),
    action(2, 'TURN', 'raise', 1200, 7), // XR turn
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 2,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['CHECK_RAISE', 'XR_TURN']);
});

test('FLOAT_BET: call flop IP, bet turn when checked to', () => {
  const actions: HandAction[] = [
    action(2, 'PREFLOP', 'raise', 250, 1), // villain opens
    action(5, 'PREFLOP', 'call', 250, 2), // hero calls
    action(2, 'FLOP', 'raise', 300, 3), // villain bets flop
    action(5, 'FLOP', 'call', 300, 4), // hero calls flop
    action(2, 'TURN', 'check', 0, 5), // villain checks turn
    action(5, 'TURN', 'raise', 600, 6), // hero floats
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 5,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['FLOAT_BET']);
});

test('CHECK_BACK: IP hero checks when checked to', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'check', 0, 3),
    action(3, 'FLOP', 'check', 0, 4), // hero checks back
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 3,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['CHECK_BACK']);
});

test('OVERBET: hero bets > pot', () => {
  const actions: HandAction[] = [
    action(1, 'PREFLOP', 'post_sb', 50, 1),
    action(2, 'PREFLOP', 'post_bb', 100, 2),
    action(3, 'PREFLOP', 'raise', 250, 3),
    action(2, 'PREFLOP', 'call', 150, 4),
    // pot ~ 500
    action(2, 'FLOP', 'check', 0, 5),
    action(3, 'FLOP', 'raise', 600, 6), // overbet: 600 > 500
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 3,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['OVERBET']);
});

test('LEAD_RIVER: OOP non-PFA leads river after checking flop and turn', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'check', 0, 3),
    action(3, 'FLOP', 'check', 0, 4),
    action(2, 'TURN', 'check', 0, 5),
    action(3, 'TURN', 'check', 0, 6),
    action(2, 'RIVER', 'raise', 350, 7), // hero leads river
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 2,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['LEAD_RIVER']);
});

// ── Multi-street barrel patterns ──

test('DOUBLE_BARREL: PFA bets flop and turn', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'check', 0, 3),
    action(3, 'FLOP', 'raise', 300, 4),
    action(2, 'FLOP', 'call', 300, 5),
    action(2, 'TURN', 'check', 0, 6),
    action(3, 'TURN', 'raise', 700, 7),
    action(2, 'TURN', 'call', 700, 8),
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 3,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['CBET', 'BARREL', 'DOUBLE_BARREL']);
  lacksTag(result, 'TRIPLE_BARREL');
});

test('TRIPLE_BARREL: PFA bets flop, turn, river', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'check', 0, 3),
    action(3, 'FLOP', 'raise', 300, 4),
    action(2, 'FLOP', 'call', 300, 5),
    action(2, 'TURN', 'check', 0, 6),
    action(3, 'TURN', 'raise', 700, 7),
    action(2, 'TURN', 'call', 700, 8),
    action(2, 'RIVER', 'check', 0, 9),
    action(3, 'RIVER', 'raise', 1500, 10),
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 3,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['CBET', 'BARREL', 'TRIPLE_BARREL']);
});

test('BARREL broken if PFA checks a street', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(2, 'PREFLOP', 'call', 150, 2),
    action(2, 'FLOP', 'check', 0, 3),
    action(3, 'FLOP', 'raise', 300, 4), // bet flop
    action(2, 'FLOP', 'call', 300, 5),
    action(2, 'TURN', 'check', 0, 6),
    action(3, 'TURN', 'check', 0, 7), // check turn → barrel broken
    action(2, 'RIVER', 'check', 0, 8),
    action(3, 'RIVER', 'raise', 600, 9),
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 3,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  lacksTag(result, 'BARREL');
  lacksTag(result, 'DOUBLE_BARREL');
  lacksTag(result, 'TRIPLE_BARREL');
});

// ── Action deviation classification ──

test('classifyActionDeviation: correct when chosen matches best', () => {
  const result = classifyActionDeviation({
    gtoMix: { raise: 0.7, call: 0.2, fold: 0.1 },
    actualAction: 'raise',
  });
  assert.equal(result, 'CORRECT');
});

test('classifyActionDeviation: OVERFOLD when folding is rarely recommended', () => {
  const result = classifyActionDeviation({
    gtoMix: { raise: 0.5, call: 0.45, fold: 0.05 },
    actualAction: 'fold',
  });
  assert.equal(result, 'OVERFOLD');
});

test('classifyActionDeviation: OVERCALL when calling is bad and fold is best', () => {
  const result = classifyActionDeviation({
    gtoMix: { raise: 0.05, call: 0.1, fold: 0.85 },
    actualAction: 'call',
  });
  assert.equal(result, 'OVERCALL');
});

test('classifyActionDeviation: OVERBLUFF when raising is bad and fold is high', () => {
  const result = classifyActionDeviation({
    gtoMix: { raise: 0.05, call: 0.25, fold: 0.7 },
    actualAction: 'raise',
  });
  assert.equal(result, 'OVERBLUFF');
});

// ── Edge cases ──

test('empty actions → no tags, SRP pot type', () => {
  const result = recognizeLines({
    actions: [],
    heroSeat: 1,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  assert.deepEqual(result.lineTags, []);
  assert.equal(result.potType, 'SRP');
  assert.equal(result.preflopAggressorSeat, null);
});

test('preflop only → no postflop tags', () => {
  const actions: HandAction[] = [
    action(3, 'PREFLOP', 'raise', 250, 1),
    action(4, 'PREFLOP', 'raise', 700, 2),
    action(3, 'PREFLOP', 'fold', 0, 3),
  ];
  const result = recognizeLines({
    actions,
    heroSeat: 4,
    buttonSeat: 6,
    playerSeats: SEATS,
    bigBlind: BB,
  });
  hasTags(result, ['THREE_BET']);
  lacksTag(result, 'CBET');
  lacksTag(result, 'BARREL');
});
