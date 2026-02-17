import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { SOCKET_EVENT_NAMES } from "@cardpilot/shared-types";

function readRepoFile(relativeFromRepoRoot: string): string {
  const repoRoot = resolve(process.cwd(), "../..");
  return readFileSync(resolve(repoRoot, relativeFromRepoRoot), "utf-8");
}

describe("Socket event contract consistency", () => {
  const serverSource = readRepoFile("apps/game-server/src/server.ts");
  const roomManagerSource = readRepoFile("apps/game-server/src/room-manager.ts");
  const webSource = readRepoFile("apps/web/src/App.tsx");

  it("core client->server event names are consistent in shared types, server handlers, and web emits", () => {
    const coreClientToServer = [
      "request_lobby",
      "create_room",
      "join_room_code",
      "sit_down",
      "seat_request",
      "approve_seat",
      "reject_seat",
      "stand_up",
      "start_hand",
      "action_submit",
      "show_hand",
      "muck_hand",
      "submit_run_preference",
      "update_settings",
      "kick_player",
      "transfer_ownership",
      "set_cohost",
      "game_control",
      "close_room",
    ] as const;

    for (const event of coreClientToServer) {
      assert.ok(
        SOCKET_EVENT_NAMES.clientToServer.includes(event),
        `shared-types missing client->server event: ${event}`
      );
      assert.match(serverSource, new RegExp(`socket\\.on\\(\\s*\"${event}\"`), `server missing socket.on(\"${event}\")`);
      assert.match(webSource, new RegExp(`\\.emit\\(\"${event}\"`), `web missing emit(\"${event}\")`);
    }
  });

  it("core server->client event names are consistent in shared types, server emits, and web listeners", () => {
    const coreServerToClient = [
      "connected",
      "lobby_snapshot",
      "room_created",
      "room_joined",
      "table_snapshot",
      "hole_cards",
      "hand_started",
      "action_applied",
      "allin_locked",
      "run_count_confirmed",
      "reveal_hole_cards",
      "reveal_board_card",
      "showdown_results",
      "hand_ended",
      "hand_aborted",
      "advice_payload",
      "advice_deviation",
      "error_event",
      "room_state_update",
      "timer_update",
      "seat_request_pending",
      "seat_request_sent",
      "seat_approved",
      "seat_rejected",
      "settings_updated",
      "think_extension_result",
      "kicked",
      "room_closed",
      "stood_up",
      "system_message",
    ] as const;

    for (const event of coreServerToClient) {
      assert.ok(
        SOCKET_EVENT_NAMES.serverToClient.includes(event),
        `shared-types missing server->client event: ${event}`
      );
      const emittedByServer = new RegExp(`\\.emit\\(\"${event}\"`).test(serverSource)
        || new RegExp(`\"${event}\"`).test(roomManagerSource);
      assert.ok(emittedByServer, `server stack missing emit path for \"${event}\"`);
      assert.match(webSource, new RegExp(`s\\.on\\(\"${event}\"`), `web missing s.on(\"${event}\")`);
    }
  });
});
