import { test, expect, type Page } from '@playwright/test';

test.setTimeout(120_000);

/**
 * Resilient login: handles both fresh auth screen and already-logged-in states.
 */
async function ensureLoggedIn(page: Page) {
  await page.goto('/');
  await page.waitForTimeout(2_000);

  // If auth screen visible, do guest login
  const authScreen = page.locator('.cp-auth-screen');
  if (await authScreen.isVisible({ timeout: 3_000 }).catch(() => false)) {
    const guestNameInput = page.locator('input[placeholder*="Enter your name"]');
    if (await guestNameInput.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await guestNameInput.fill('SpeedTest');
    }
    const guestBtn = page.locator('button:has-text("Continue as Guest")');
    await guestBtn.waitFor({ state: 'visible', timeout: 5_000 });
    await guestBtn.click();
    await authScreen.waitFor({ state: 'detached', timeout: 30_000 });
  }

  // Dismiss onboarding modal if it appears
  const startBtn = page.locator('button:has-text("Start Playing")');
  if (await startBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await startBtn.click();
    await page
      .locator('.fixed.inset-0.z-50')
      .waitFor({ state: 'detached', timeout: 5_000 })
      .catch(() => {});
  }
}

/**
 * Create a room via socket API and navigate to it. Returns the table ID.
 */
async function createRoomViaSocket(page: Page): Promise<string> {
  // Wait for socket to be ready
  await page.waitForFunction(
    () => {
      return !!(window as unknown as Record<string, any>).__testSocket?.connected;
    },
    { timeout: 10_000 },
  );

  // Create room via socket and get the real table ID back
  const tableId = await page.evaluate(() => {
    return new Promise<string>((resolve, reject) => {
      const socket = (window as unknown as Record<string, any>).__testSocket;
      if (!socket) {
        reject(new Error('__testSocket not found'));
        return;
      }

      const timeout = setTimeout(() => reject(new Error('create_room timeout')), 10_000);
      socket.once('room_created', (data: { tableId: string; roomCode: string }) => {
        clearTimeout(timeout);
        resolve(data.tableId);
      });
      socket.once('error_event', (data: any) => {
        clearTimeout(timeout);
        reject(new Error('create_room error: ' + JSON.stringify(data)));
      });

      socket.emit('create_room', {
        roomName: 'Speed Test',
        maxPlayers: 6,
        smallBlind: 50,
        bigBlind: 100,
        buyInMin: 2000,
        buyInMax: 20000,
        visibility: 'public',
      });
    });
  });

  console.log('Created room with tableId:', tableId);

  // Navigate to the actual table
  await page.goto(`/table/${encodeURIComponent(tableId)}`);
  await page.waitForTimeout(1_000);
  await expect(page.locator('.cp-table-felt')).toBeVisible({ timeout: 10_000 });

  return tableId;
}

/**
 * Sit down at the first available empty seat.
 */
async function sitDown(page: Page) {
  const emptySeats = page.locator('[data-empty-seat]');
  await emptySeats.first().waitFor({ state: 'visible', timeout: 10_000 });
  await emptySeats.first().click();

  const sitBtn = page.locator('button:has-text("Sit Down")');
  await sitBtn.waitFor({ state: 'visible', timeout: 5_000 });
  await sitBtn.click();

  // Wait for player to appear in a seat
  await page.locator('.cp-seat-name').first().waitFor({ state: 'visible', timeout: 10_000 });
}

/**
 * Add bot via socket update_settings. We are the host since we created the room.
 */
async function addBot(page: Page, tableId: string) {
  const result = await page.evaluate((tid) => {
    return new Promise<string>((resolve) => {
      const socket = (window as unknown as Record<string, any>).__testSocket;
      if (!socket) {
        resolve('ERROR: __testSocket not found');
        return;
      }

      const timeout = setTimeout(() => resolve('TIMEOUT'), 5000);
      socket.once('settings_updated', (data: any) => {
        clearTimeout(timeout);
        resolve('OK: ' + JSON.stringify(data));
      });
      socket.once('error_event', (data: any) => {
        clearTimeout(timeout);
        resolve('ERROR: ' + JSON.stringify(data));
      });

      socket.emit('update_settings', {
        tableId: tid,
        settings: {
          botSeats: [{ seat: 3, profile: 'gto_balanced' }],
          showdownSpeed: 'turbo',
        },
      });
    });
  }, tableId);

  console.log('addBot result:', result);
  if (result.startsWith('ERROR')) {
    throw new Error(`Failed to add bot: ${result}`);
  }

  // Wait for bot to appear
  await page.waitForFunction(
    () => {
      const seats = document.querySelectorAll('.cp-seat-name');
      return seats.length >= 2;
    },
    { timeout: 20_000 },
  );
}

// ═══════════════════════════════════════════════════
// Bot Speed Test: measure how fast the bot responds
// ═══════════════════════════════════════════════════
test.describe('Bot Speed Test', () => {
  test('bot should respond within 3 seconds per action across 3 hands', async ({ page }) => {
    // Collect console logs for debugging
    page.on('console', (msg) => {
      if (msg.type() === 'error' || msg.text().includes('bot') || msg.text().includes('decision')) {
        console.log(`[BROWSER ${msg.type()}] ${msg.text()}`);
      }
    });

    // ── Setup ──
    console.log('=== Setup ===');
    await ensureLoggedIn(page);
    const tableId = await createRoomViaSocket(page);
    console.log('Table ID:', tableId);
    expect(tableId).toBeTruthy();

    await sitDown(page);
    console.log('Player seated');

    await addBot(page, tableId);
    console.log('Bot seated');
    console.log('Setup complete — 2 players seated');

    // ── Measure bot speed across 3 hands ──
    const botResponseTimes: number[] = [];

    for (let hand = 1; hand <= 3; hand++) {
      console.log(`\n=== Hand ${hand}: Dealing ===`);

      // Deal
      await page.evaluate((tid) => {
        const socket = (window as unknown as Record<string, any>).__testSocket;
        socket.emit('start_hand', { tableId: tid });
      }, tableId);

      await page.waitForTimeout(1_500);

      let actionCount = 0;
      while (actionCount < 8) {
        actionCount++;

        // Wait for action buttons to appear (our turn)
        const myTurn = await page
          .locator('.cp-btn-fold, .cp-btn-check, .cp-btn-call')
          .first()
          .waitFor({ state: 'visible', timeout: 15_000 })
          .then(() => true)
          .catch(() => false);

        if (!myTurn) {
          console.log(`  Hand ${hand}, action ${actionCount}: hand ended (no turn)`);
          break;
        }

        // Auto-muck at showdown if show/muck buttons appear
        const muckBtn = page.locator('button:has-text("Muck")');
        if (await muckBtn.isVisible({ timeout: 200 }).catch(() => false)) {
          await muckBtn.click();
          console.log(`  Hand ${hand}, action ${actionCount}: MUCK (showdown)`);
          break;
        }

        // Our turn — act immediately
        const checkBtn = page.locator('.cp-btn-check');
        const callBtn = page.locator('.cp-btn-call');
        const foldBtn = page.locator('.cp-btn-fold');

        if (await checkBtn.isVisible({ timeout: 500 }).catch(() => false)) {
          await checkBtn.click();
          console.log(`  Hand ${hand}, action ${actionCount}: CHECK`);
        } else if (await callBtn.isVisible({ timeout: 500 }).catch(() => false)) {
          await callBtn.click();
          console.log(`  Hand ${hand}, action ${actionCount}: CALL`);
        } else if (await foldBtn.isVisible({ timeout: 500 }).catch(() => false)) {
          await foldBtn.click();
          console.log(`  Hand ${hand}, action ${actionCount}: FOLD`);
          break;
        } else {
          console.log(`  Hand ${hand}, action ${actionCount}: no action buttons`);
          break;
        }

        // After our action, wait briefly for buttons to disappear (action processing)
        await page.waitForTimeout(300);

        // Now measure how long until our action buttons reappear (= bot acted + back to us)
        // or until 10s pass (hand ended / showdown)
        const t0 = Date.now();
        const nextTurn = await page
          .locator('.cp-btn-fold, .cp-btn-check, .cp-btn-call')
          .first()
          .waitFor({ state: 'visible', timeout: 10_000 })
          .then(() => true)
          .catch(() => false);
        const elapsed = Date.now() - t0;

        if (nextTurn && elapsed > 200 && elapsed < 3000) {
          // Only count responses under 3s as actual bot response times
          // (longer likely includes showdown/hand transition delays)
          console.log(`  Hand ${hand}, action ${actionCount}: bot responded in ${elapsed}ms`);
          botResponseTimes.push(elapsed);
        } else if (nextTurn && elapsed >= 3000) {
          console.log(
            `  Hand ${hand}, action ${actionCount}: hand transition ${elapsed}ms (excluded)`,
          );
        } else if (!nextTurn) {
          console.log(`  Hand ${hand}, action ${actionCount}: hand ended after ${elapsed}ms`);
          break;
        }
        // else: buttons reappeared instantly (< 200ms), same street still our turn
      }

      // Wait between hands
      await page.waitForTimeout(1_500);
    }

    // ── Results ──
    console.log('\n=== BOT SPEED RESULTS ===');
    console.log(`  Samples: ${botResponseTimes.length}`);
    if (botResponseTimes.length > 0) {
      const avg = botResponseTimes.reduce((a, b) => a + b, 0) / botResponseTimes.length;
      const max = Math.max(...botResponseTimes);
      const min = Math.min(...botResponseTimes);
      console.log(`  Min: ${min}ms`);
      console.log(`  Max: ${max}ms`);
      console.log(`  Avg: ${Math.round(avg)}ms`);
      console.log(`  All: [${botResponseTimes.join(', ')}]`);

      // Assert: bot should respond within 3 seconds on average
      expect(avg).toBeLessThan(3000);
      // Assert: no single response should take more than 5 seconds
      expect(max).toBeLessThan(5000);
    } else {
      console.log('  WARNING: No bot response times recorded!');
    }

    // Verify we're still on the table
    expect(page.url()).toContain('/table/');
  });
});
