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

function readWebSource(): string {
  try {
    return readFileSync(
      resolve(process.cwd(), '../web/src/pages/clubs/tabs/LeaderboardTab.tsx'),
      'utf-8',
    );
  } catch {
    return readFileSync(
      resolve(process.cwd(), 'apps/web/src/pages/clubs/tabs/LeaderboardTab.tsx'),
      'utf-8',
    );
  }
}

describe('Club leaderboard scope defaults', () => {
  it('defaults server leaderboard requests to week when scope is omitted', () => {
    const source = readServerSource();
    assert.match(
      source,
      /payload\.timeRange === 'day'[\s\S]*payload\.timeRange === 'week'[\s\S]*payload\.timeRange === 'all'[\s\S]*: 'week';/,
    );
  });

  it('defaults member leaderboard UI to week and exposes day/week/all switcher', () => {
    const source = readWebSource();
    assert.match(source, /useState<ClubLeaderboardRange>\('week'\)/);
    assert.match(source, /value: 'day'/);
    assert.match(source, /value: 'week'/);
    assert.match(source, /value: 'all'/);
  });
});
