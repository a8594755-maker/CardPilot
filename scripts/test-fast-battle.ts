/**
 * Quick test: connect to the game server, warm up the pool,
 * then start a Fast Battle session. Logs all events received.
 */
import { io } from 'socket.io-client';

const SERVER = 'http://127.0.0.1:4000';
const TEST_USER_ID = 'test-fb-user-001';
const TEST_DISPLAY_NAME = 'TestPlayer';

const socket = io(SERVER, {
  auth: {
    userId: TEST_USER_ID,
    displayName: TEST_DISPLAY_NAME,
  },
});

const log = (tag: string, ...args: unknown[]) =>
  console.log(`[${new Date().toISOString()}] [${tag}]`, ...args);

socket.on('connect', () => {
  log('CONNECT', 'Connected! socketId=', socket.id);

  // Step 1: Warmup the pool (creates rooms + spawns bots)
  log('EMIT', 'fast_battle_warmup');
  socket.emit('fast_battle_warmup');

  // Step 2: Wait for bots to connect and sit down (10 seconds)
  log('INFO', 'Waiting 10s for pool warmup...');
  setTimeout(() => {
    log('EMIT', 'fast_battle_start', { targetHandCount: 3, bigBlind: 3 });
    socket.emit('fast_battle_start', { targetHandCount: 3, bigBlind: 3 });
  }, 10000);
});

socket.on('connect_error', (err) => {
  log('CONNECT_ERROR', err.message);
});

socket.on('disconnect', (reason) => {
  log('DISCONNECT', reason);
});

// Listen to ALL fast battle events
socket.on('fast_battle_session_started', (d) => {
  log('SESSION_STARTED', JSON.stringify(d));
});

socket.on('fast_battle_table_assigned', (d) => {
  log('TABLE_ASSIGNED', JSON.stringify(d));
  // Request snapshot like the real client does
  setTimeout(() => {
    log('EMIT', 'request_table_snapshot', { tableId: d.tableId });
    socket.emit('request_table_snapshot', { tableId: d.tableId });
  }, 300);
});

socket.on('room_joined', (d) => {
  log('ROOM_JOINED', JSON.stringify(d));
  // Request snapshot like the real client does
  log('EMIT', 'request_table_snapshot + request_room_state', { tableId: d.tableId });
  socket.emit('request_table_snapshot', { tableId: d.tableId });
  socket.emit('request_room_state', { tableId: d.tableId });
});

socket.on('table_snapshot', (d) => {
  const playerCount = d.players?.length ?? 0;
  const activeCount =
    d.players?.filter(
      (p: { status: string; stack: number }) => p.status === 'active' && p.stack > 0,
    ).length ?? 0;
  log(
    'TABLE_SNAPSHOT',
    `tableId=${d.tableId} players=${playerCount} active=${activeCount} version=${d.stateVersion} hand=${d.handId ? d.handId.slice(0, 8) : 'none'} street=${d.street ?? 'none'}`,
  );
  if (d.players && d.players.length > 0) {
    for (const p of d.players) {
      log(
        '  PLAYER',
        `seat=${p.seat} userId=${p.userId?.slice(0, 20)} name=${p.name} status=${p.status} stack=${p.stack} inHand=${p.inHand}`,
      );
    }
  }
});

socket.on('hole_cards', (d) => {
  log('HOLE_CARDS', `seat=${d.seat} cards=${JSON.stringify(d.cards)}`);
});

socket.on('hand_started', () => {
  log('HAND_STARTED', '');
});

socket.on('action_on', (d) => {
  log('ACTION_ON', `seat=${d.seat} actions=${JSON.stringify(d.legalActions?.actions)}`);
  // If it's our seat, auto-fold
  if (d.seat === 1) {
    log('EMIT', 'player_action: fold');
    socket.emit('player_action', { action: 'fold' });
  }
});

socket.on('fast_battle_hand_result', (d) => {
  log('HAND_RESULT', `hand=${d.handNumber} result=${d.result} cumulative=${d.cumulativeResult}`);
});

socket.on('fast_battle_progress', (d) => {
  log(
    'PROGRESS',
    `hands=${d.handsPlayed}/${d.targetHandCount ?? '?'} cumResult=${d.cumulativeResult}`,
  );
});

socket.on('fast_battle_session_ended', (d) => {
  log('SESSION_ENDED', `handsPlayed=${d.report?.stats?.handsPlayed}`);
  setTimeout(() => {
    socket.disconnect();
    process.exit(0);
  }, 2000);
});

socket.on('fast_battle_error', (d) => {
  log('FB_ERROR', JSON.stringify(d));
});

socket.on('error_event', (d) => {
  log('ERROR_EVENT', JSON.stringify(d));
});

socket.on('system_message', (d) => {
  log('SYSTEM_MSG', d.message);
});

socket.on('room_state_update', (d) => {
  log('ROOM_STATE', `tableId=${d.tableId} status=${d.status}`);
});

// Timeout after 60s
setTimeout(() => {
  log('TIMEOUT', 'Test timed out after 60s');
  socket.disconnect();
  process.exit(1);
}, 60000);
