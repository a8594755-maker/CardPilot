import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomInt, randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { io, type Socket } from "socket.io-client";
import type {
  ClientToServerEvents,
  ServerToClientEvents,
  TableState,
} from "@cardpilot/shared-types";

type TestSocket = Socket<ServerToClientEvents, ClientToServerEvents>;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForCondition(check: () => boolean, timeoutMs = 8_000): Promise<void> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (check()) return;
    await sleep(40);
  }
  throw new Error(`Condition not met within ${timeoutMs}ms`);
}

function waitForSocketEvent<T>(
  socket: { on: (event: string, cb: (payload: T) => void) => void; off: (event: string, cb: (payload: T) => void) => void },
  event: string,
  predicate: (payload: T) => boolean = () => true,
  timeoutMs = 8_000,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      socket.off(event, handler);
      reject(new Error(`Timed out waiting for event \"${event}\"`));
    }, timeoutMs);

    const handler = (payload: T) => {
      if (!predicate(payload)) return;
      clearTimeout(timer);
      socket.off(event, handler);
      resolve(payload);
    };

    socket.on(event, handler);
  });
}

function latestSnapshotForTable(snapshots: TableState[], tableId: string): TableState | null {
  for (let i = snapshots.length - 1; i >= 0; i -= 1) {
    if (snapshots[i].tableId === tableId) return snapshots[i];
  }
  return null;
}

function assertMonotonicVersions(snapshots: TableState[], label: string): void {
  let previous = -1;
  for (const snapshot of snapshots) {
    assert.ok(
      snapshot.stateVersion >= previous,
      `${label} received non-monotonic snapshot version: ${snapshot.stateVersion} < ${previous}`,
    );
    previous = snapshot.stateVersion;
  }
}

async function startServer(): Promise<{ process: ChildProcessWithoutNullStreams; url: string }> {
  const port = 45_000 + randomInt(1_000);
  const cwd = resolve(process.cwd());
  const serverEntry = resolve(cwd, "src/server.ts");
  const tsxLoaderUrl = pathToFileURL(resolve(cwd, "../../node_modules/tsx/dist/loader.mjs")).href;

  const child = spawn("node", ["--import", tsxLoaderUrl, serverEntry], {
    cwd,
    env: {
      ...process.env,
      NODE_ENV: "test",
      PORT: String(port),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let logs = "";
  child.stdout.on("data", (chunk: unknown) => {
    logs += String(chunk);
  });
  child.stderr.on("data", (chunk: unknown) => {
    logs += String(chunk);
  });

  await waitForCondition(() => {
    if (child.exitCode !== null) {
      throw new Error(`Server exited before start (code=${child.exitCode}). Logs:\n${logs}`);
    }
    return logs.includes('"event":"server.started"');
  }, 12_000);

  return { process: child, url: `http://127.0.0.1:${port}` };
}

async function stopServer(child: ChildProcessWithoutNullStreams): Promise<void> {
  if (child.exitCode !== null) return;
  child.kill();

  const startedAt = Date.now();
  while (child.exitCode === null && Date.now() - startedAt < 4_000) {
    await sleep(50);
  }

  if (child.exitCode === null) {
    child.kill("SIGTERM");
  }
}

async function connectClient(serverUrl: string, userId: string, displayName: string): Promise<TestSocket> {
  const socket: TestSocket = io(serverUrl, {
    transports: ["websocket"],
    reconnection: false,
    auth: { userId, displayName },
  });

  await waitForSocketEvent<{ socketId: string; userId: string }>(
    socket as unknown as { on: (event: string, cb: (payload: { socketId: string; userId: string }) => void) => void; off: (event: string, cb: (payload: { socketId: string; userId: string }) => void) => void },
    "connected",
    () => true,
    8_000,
  );

  return socket;
}

describe("Multi-client snapshot sync", () => {
  it("keeps two clients in deterministic sync and hydrates reconnect with latest authoritative snapshot", async () => {
    const { process: serverProcess, url } = await startServer();

    const hostUserId = `host-${randomUUID()}`;
    const guestUserId = `guest-${randomUUID()}`;

    let host: TestSocket | null = null;
    let guest: TestSocket | null = null;
    let guestRejoin: TestSocket | null = null;

    try {
      host = await connectClient(url, hostUserId, "Host");
      guest = await connectClient(url, guestUserId, "Guest");

      const hostSnapshots: TableState[] = [];
      const guestSnapshots: TableState[] = [];
      host.on("table_snapshot", (snapshot: TableState) => hostSnapshots.push(snapshot));
      guest.on("table_snapshot", (snapshot: TableState) => guestSnapshots.push(snapshot));

      host.emit("create_room", {
        roomName: "Sync Regression",
        maxPlayers: 2,
        smallBlind: 50,
        bigBlind: 100,
        isPublic: true,
      });

      const roomCreated = await waitForSocketEvent<{ tableId: string; roomCode: string }>(
        host as unknown as { on: (event: string, cb: (payload: { tableId: string; roomCode: string }) => void) => void; off: (event: string, cb: (payload: { tableId: string; roomCode: string }) => void) => void },
        "room_created",
        () => true,
      );

      const { tableId, roomCode } = roomCreated;

      await waitForCondition(() => latestSnapshotForTable(hostSnapshots, tableId) !== null);

      guest.emit("join_room_code", { roomCode });
      await waitForSocketEvent<{ tableId: string }>(
        guest as unknown as { on: (event: string, cb: (payload: { tableId: string }) => void) => void; off: (event: string, cb: (payload: { tableId: string }) => void) => void },
        "room_joined",
        (payload) => payload.tableId === tableId,
      );
      await waitForCondition(() => latestSnapshotForTable(guestSnapshots, tableId) !== null);

      host.emit("sit_down", { tableId, seat: 1, buyIn: 5_000, name: "Host" });
      guest.emit("sit_down", { tableId, seat: 2, buyIn: 5_000, name: "Guest" });

      await waitForCondition(() => {
        const hostLatest = latestSnapshotForTable(hostSnapshots, tableId);
        const guestLatest = latestSnapshotForTable(guestSnapshots, tableId);
        return Boolean(
          hostLatest
            && guestLatest
            && hostLatest.players.length === 2
            && guestLatest.players.length === 2
            && hostLatest.stateVersion === guestLatest.stateVersion,
        );
      }, 10_000);

      assertMonotonicVersions(hostSnapshots.filter((snapshot) => snapshot.tableId === tableId), "host");
      assertMonotonicVersions(guestSnapshots.filter((snapshot) => snapshot.tableId === tableId), "guest");

      host.emit("start_hand", { tableId });

      await waitForCondition(() => {
        const hostLatest = latestSnapshotForTable(hostSnapshots, tableId);
        const guestLatest = latestSnapshotForTable(guestSnapshots, tableId);
        return Boolean(
          hostLatest
            && guestLatest
            && hostLatest.handId
            && hostLatest.handId === guestLatest.handId
            && hostLatest.stateVersion === guestLatest.stateVersion,
        );
      }, 10_000);

      const beforeActionSnapshot = latestSnapshotForTable(hostSnapshots, tableId);
      assert.ok(beforeActionSnapshot, "Host should have a snapshot before action");
      if (!beforeActionSnapshot) {
        throw new Error("Missing before-action snapshot");
      }
      assert.ok(beforeActionSnapshot.handId, "A hand should be active");
      assert.ok(beforeActionSnapshot.actorSeat === 1 || beforeActionSnapshot.actorSeat === 2, "Actor seat should be one of the seated players");

      const actorSocket = beforeActionSnapshot.actorSeat === 1 ? host : guest;
      const action: "check" | "call" | "fold" = beforeActionSnapshot.legalActions?.canCheck
        ? "check"
        : beforeActionSnapshot.legalActions?.canCall
          ? "call"
          : "fold";

      actorSocket.emit("action_submit", {
        tableId,
        handId: beforeActionSnapshot.handId,
        action,
      });

      await waitForCondition(() => {
        const hostLatest = latestSnapshotForTable(hostSnapshots, tableId);
        const guestLatest = latestSnapshotForTable(guestSnapshots, tableId);
        return Boolean(
          hostLatest
            && guestLatest
            && hostLatest.stateVersion > beforeActionSnapshot.stateVersion
            && hostLatest.stateVersion === guestLatest.stateVersion,
        );
      }, 10_000);

      const versionBeforeReconnect = latestSnapshotForTable(hostSnapshots, tableId)?.stateVersion ?? -1;

      guest.disconnect();
      guest = null;

      guestRejoin = await connectClient(url, guestUserId, "Guest");
      const guestRejoinSnapshots: TableState[] = [];
      guestRejoin.on("table_snapshot", (snapshot: TableState) => guestRejoinSnapshots.push(snapshot));

      guestRejoin.emit("join_room_code", { roomCode });
      await waitForSocketEvent<{ tableId: string }>(
        guestRejoin as unknown as { on: (event: string, cb: (payload: { tableId: string }) => void) => void; off: (event: string, cb: (payload: { tableId: string }) => void) => void },
        "room_joined",
        (payload) => payload.tableId === tableId,
      );

      const hydrated = await waitForSocketEvent<TableState>(
        guestRejoin as unknown as { on: (event: string, cb: (payload: TableState) => void) => void; off: (event: string, cb: (payload: TableState) => void) => void },
        "table_snapshot",
        (snapshot) => snapshot.tableId === tableId,
        10_000,
      );

      const hostCurrentSnapshot = latestSnapshotForTable(hostSnapshots, tableId);
      assert.ok(hostCurrentSnapshot, "Host should still have a latest snapshot");
      if (!hostCurrentSnapshot) {
        throw new Error("Missing host snapshot after guest reconnect");
      }

      assert.ok(
        hydrated.stateVersion >= versionBeforeReconnect,
        `Rejoin snapshot must not regress version (${hydrated.stateVersion} < ${versionBeforeReconnect})`,
      );
      assert.equal(hydrated.handId, hostCurrentSnapshot.handId, "Rejoined client should hydrate current handId");
      assert.equal(hydrated.street, hostCurrentSnapshot.street, "Rejoined client should hydrate current street");
      assert.equal(hydrated.pot, hostCurrentSnapshot.pot, "Rejoined client should hydrate current pot");

      assertMonotonicVersions(guestRejoinSnapshots.filter((snapshot) => snapshot.tableId === tableId), "guest-rejoin");
    } finally {
      host?.disconnect();
      guest?.disconnect();
      guestRejoin?.disconnect();
      await stopServer(serverProcess);
    }
  });
});
