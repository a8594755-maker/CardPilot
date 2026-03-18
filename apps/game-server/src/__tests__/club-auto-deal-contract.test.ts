import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readServerSource(): string {
  try {
    return readFileSync(resolve(process.cwd(), 'src/server.ts'), 'utf-8');
  } catch {
    return readFileSync(resolve(process.cwd(), 'apps/game-server/src/server.ts'), 'utf-8');
  }
}

describe('Club auto-deal + deferred-leave contracts', () => {
  const source = readServerSource();

  it('auto-schedules dealing when players sit', () => {
    assert.match(
      source,
      /const seatPlayerDirect = async[\s\S]*scheduleAutoDealIfNeeded\(params\.tableId\)/,
    );
    assert.match(source, /socket\.on\(\s*'sit_down'[\s\S]*await seatPlayerDirect\(/);
    assert.match(source, /socket\.on\('approve_seat'[\s\S]*await seatPlayerDirect\(/);
    assert.match(source, /socket\.on\('sit_in'[\s\S]*scheduleAutoDealIfNeeded\(payload\.tableId\)/);
  });

  it('uses per-table minPlayersToStart in deal validation', () => {
    assert.match(source, /room\.settings\.minPlayersToStart/);
    assert.match(source, /Need at least \$\{minPlayersToStart\} eligible players to deal/);
    assert.match(
      source,
      /Auto-start skipped: need at least \$\{minPlayersToStart\} eligible players/,
    );
  });

  it('defers stand-up/leave during active hand and flushes queue after hand end', () => {
    assert.match(source, /if \(table\.isHandActive\(\)\) \{[\s\S]*pendingStandUps/);
    assert.match(source, /Leaving after this hand\./);
    assert.match(source, /const deferredSeats = pendingStandUps\.get\(tableId\)/);
    assert.match(source, /pendingStandUps\.delete\(tableId\)/);
  });
});
