import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { SOCKET_EVENT_NAMES } from '@cardpilot/shared-types';

function readRepoFile(relativeFromRepoRoot: string): string {
  // Walk up from this file (__tests__/ → src/ → game-engine/ → packages/ → repo root)
  const repoRoot = resolve(import.meta.dirname, '..', '..', '..', '..');
  return readFileSync(resolve(repoRoot, relativeFromRepoRoot), 'utf-8');
}

function readRepoTree(relativeDirFromRepoRoot: string): string {
  const repoRoot = resolve(import.meta.dirname, '..', '..', '..', '..');
  const root = resolve(repoRoot, relativeDirFromRepoRoot);
  const contents: string[] = [];

  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir)) {
      const fullPath = resolve(dir, entry);
      const stats = statSync(fullPath);
      if (stats.isDirectory()) {
        walk(fullPath);
        continue;
      }
      if (/\.(ts|tsx)$/.test(entry) && !/\.test\./.test(entry)) {
        contents.push(readFileSync(fullPath, 'utf-8'));
      }
    }
  };

  walk(root);
  return contents.join('\n');
}

describe('Socket event contract consistency', () => {
  const serverSource = readRepoFile('apps/game-server/src/server.ts');
  const roomManagerSource = readRepoFile('apps/game-server/src/room-manager.ts');
  const webSource = readRepoTree('apps/web/src');

  it('core client->server event names are consistent in shared types, server handlers, and web emits', () => {
    const coreClientToServer = [
      'request_lobby',
      'create_room',
      'join_room_code',
      'sit_down',
      'stand_up',
      'action_submit',
    ] as const;

    for (const event of coreClientToServer) {
      assert.ok(
        SOCKET_EVENT_NAMES.clientToServer.includes(event),
        `shared-types missing client->server event: ${event}`,
      );
      assert.match(
        serverSource,
        new RegExp(`socket\\.on\\(\\s*['"]${event}['"]`),
        `server missing socket.on("${event}")`,
      );
      assert.match(
        webSource,
        new RegExp(`\\.emit\\(\\s*['"]${event}['"]`),
        `web missing emit("${event}")`,
      );
    }
  });

  it('core server->client event names are consistent in shared types, server emits, and web listeners', () => {
    const coreServerToClient = [
      'connected',
      'lobby_snapshot',
      'room_created',
      'room_joined',
      'table_snapshot',
      'hole_cards',
      'hand_started',
      'action_applied',
      'allin_locked',
      'reveal_hole_cards',
      'showdown_results',
      'hand_ended',
      'room_state_update',
      'advice_payload',
      'advice_deviation',
    ] as const;

    for (const event of coreServerToClient) {
      assert.ok(
        SOCKET_EVENT_NAMES.serverToClient.includes(event),
        `shared-types missing server->client event: ${event}`,
      );
      const emittedByServer =
        new RegExp(`\\.emit\\(\\s*['"]${event}['"]`).test(serverSource) ||
        new RegExp(`['"]${event}['"]`).test(roomManagerSource);
      assert.ok(emittedByServer, `server stack missing emit path for "${event}"`);
      assert.match(
        webSource,
        new RegExp(`\\.on\\(\\s*['"]${event}['"]`),
        `web missing s.on("${event}")`,
      );
    }
  });
});
