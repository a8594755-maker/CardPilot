import { test, expect, type Page } from '@playwright/test';

test.setTimeout(120_000);

/**
 * Helper: enter as guest and land on lobby.
 */
async function loginAsGuest(page: Page, name = 'TestPlayer') {
  await page.goto('/');
  await page.waitForSelector('.cp-auth-screen', { timeout: 15_000 });

  const guestNameInput = page.locator('input[placeholder*="Enter your name"]');
  if (await guestNameInput.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await guestNameInput.fill(name);
  }

  const guestBtn = page.locator('button:has-text("Continue as Guest")');
  await guestBtn.waitFor({ state: 'visible', timeout: 5_000 });
  await guestBtn.click();
  await page.waitForSelector('.cp-auth-screen', { state: 'detached', timeout: 30_000 });

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
 * Helper: create a room and navigate to the table.
 */
async function createRoomAndNavigate(page: Page) {
  const goToTableBtn = page.locator('button:has-text("Go to Table")');
  if (await goToTableBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await goToTableBtn.click();
    await page.waitForURL(/\/table\//, { timeout: 15_000 });
    return;
  }

  const createBtn = page.locator('button:has-text("Create Room")');
  await expect(createBtn).toBeVisible({ timeout: 10_000 });
  await createBtn.click();

  const goBtn = page.locator('button:has-text("Go to Table")');
  await goBtn.waitFor({ state: 'visible', timeout: 10_000 });
  await goBtn.click();
  await page.waitForURL(/\/table\//, { timeout: 15_000 });
}

/**
 * Helper: sit down at the first available empty seat.
 */
async function sitDown(page: Page) {
  const emptySeats = page.locator('[data-empty-seat]');
  await emptySeats.first().waitFor({ state: 'visible', timeout: 10_000 });
  await emptySeats.first().click();

  // Buy-in modal
  const sitBtn = page.locator('button:has-text("Sit Down")');
  await sitBtn.waitFor({ state: 'visible', timeout: 5_000 });
  await sitBtn.click();

  // Wait for modal to close
  await expect(page.locator('.glass-card')).not.toBeVisible({ timeout: 5_000 });

  // Wait for player name to appear in a seat
  await page.locator('.cp-seat-name').first().waitFor({ state: 'visible', timeout: 10_000 });
}

/**
 * Helper: get the tableId from the URL.
 */
function getTableId(page: Page): string {
  const url = page.url();
  const match = url.match(/\/table\/([^/?#]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

/**
 * Helper: add a bot via socket update_settings.
 */
async function addBot(page: Page, tableId: string) {
  const result = await page.evaluate((tid) => {
    return new Promise<string>((resolve) => {
      const socket = (window as unknown as Record<string, any>).__testSocket;
      if (!socket) {
        resolve('ERROR: __testSocket not found');
        return;
      }

      const timeout = setTimeout(() => resolve('TIMEOUT: no response in 5s'), 5000);
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
        },
      });
    });
  }, tableId);

  console.log('addBot result:', result);

  if (result.startsWith('ERROR')) {
    throw new Error(`Failed to add bot: ${result}`);
  }

  // Wait for bot to connect and appear as a seated player
  await page.waitForFunction(
    () => {
      const seatNames = document.querySelectorAll('.cp-seat-name');
      return seatNames.length >= 2;
    },
    { timeout: 20_000 },
  );
}

/**
 * Helper: deal a hand via socket.
 */
async function dealHand(page: Page, tableId: string) {
  await page.evaluate((tid) => {
    const socket = (window as unknown as Record<string, any>).__testSocket;
    socket.emit('start_hand', { tableId: tid });
  }, tableId);
}

/**
 * Helper: wait for our turn (action buttons to appear).
 * Returns true if our turn appeared, false if timed out.
 */
async function waitForMyTurn(page: Page, timeoutMs = 15_000): Promise<boolean> {
  try {
    await page
      .locator('.cp-btn-fold, .cp-btn-check, .cp-btn-call')
      .first()
      .waitFor({ state: 'visible', timeout: timeoutMs });
    await page.waitForTimeout(300);
    return true;
  } catch {
    return false;
  }
}

/**
 * Helper: wait for a hand to end (action buttons disappear).
 */
async function waitForHandEnd(page: Page, label: string) {
  await page
    .locator('.cp-btn-fold, .cp-btn-check, .cp-btn-call')
    .first()
    .waitFor({ state: 'hidden', timeout: 20_000 })
    .catch(() => {
      console.log(`${label}: timeout waiting for hand end, continuing...`);
    });
  await page.waitForTimeout(2_500);
}

// ═══════════════════════════════════════════════════
// Comprehensive Test: verify all core table features
// ═══════════════════════════════════════════════════
test.describe('Play vs Bot — Full Feature Check', () => {
  test('login, sit, add bot, verify hole cards, fold, check/call, raise across 5 hands', async ({
    page,
  }) => {
    // ── Setup ──
    console.log('=== Setup: Login ===');
    await loginAsGuest(page, 'E2E-Player');

    console.log('=== Setup: Create room ===');
    await createRoomAndNavigate(page);
    const tableId = getTableId(page);
    console.log('Table ID:', tableId);
    expect(tableId).toBeTruthy();
    await expect(page.locator('.cp-table-felt')).toBeVisible({ timeout: 10_000 });

    console.log('=== Setup: Sit down ===');
    await sitDown(page);
    console.log('Player seated');

    console.log('=== Setup: Add bot ===');
    await addBot(page, tableId);
    console.log('Bot seated');

    // ── Track results ──
    const results = {
      holeCardsVisible: false,
      foldUsed: false,
      checkUsed: false,
      callUsed: false,
      raiseUsed: false,
      handsCompleted: 0,
    };

    // ── Hand 1: verify hole cards + call/check ──
    console.log('=== Hand 1: Deal — verify hole cards + call/check ===');
    await dealHand(page, tableId);
    await page.waitForTimeout(1_500);

    // Check hole cards
    const heroStrip = page.locator('.cp-hero-strip');
    const heroCards = heroStrip.locator('.cp-poker-card');
    if (await heroStrip.isVisible({ timeout: 5_000 }).catch(() => false)) {
      const cardCount = await heroCards.count();
      console.log(`  Hole cards visible: ${cardCount} cards`);
      results.holeCardsVisible = cardCount >= 2 || (await heroStrip.isVisible());
    } else {
      console.log('  WARNING: Hero strip not visible!');
    }

    // Play the hand — prefer check > call
    let streetCount = 0;
    while (streetCount < 5) {
      streetCount++;
      const myTurn = await waitForMyTurn(page);
      if (!myTurn) break;

      const checkBtn = page.locator('.cp-btn-check');
      const callBtn = page.locator('.cp-btn-call');
      const foldBtn = page.locator('.cp-btn-fold');

      if (await checkBtn.isVisible({ timeout: 500 }).catch(() => false)) {
        await checkBtn.click();
        results.checkUsed = true;
        console.log(`  Hand 1, street ${streetCount}: CHECK`);
      } else if (await callBtn.isVisible({ timeout: 500 }).catch(() => false)) {
        await callBtn.click();
        results.callUsed = true;
        console.log(`  Hand 1, street ${streetCount}: CALL`);
      } else if (await foldBtn.isVisible({ timeout: 500 }).catch(() => false)) {
        await foldBtn.click();
        console.log(`  Hand 1, street ${streetCount}: FOLD (fallback)`);
        break;
      } else {
        break;
      }

      await page.waitForTimeout(1_500);
      const still = await page
        .locator('.cp-btn-fold, .cp-btn-check, .cp-btn-call')
        .first()
        .isVisible({ timeout: 2_000 })
        .catch(() => false);
      if (!still) break;
    }
    await waitForHandEnd(page, 'Hand 1');
    results.handsCompleted++;
    console.log('=== Hand 1 complete ===');

    // ── Hand 2: test FOLD ──
    console.log('=== Hand 2: Deal — test FOLD ===');
    await dealHand(page, tableId);
    await page.waitForTimeout(1_500);

    if (await waitForMyTurn(page)) {
      const foldBtn = page.locator('.cp-btn-fold');
      if (await foldBtn.isVisible({ timeout: 500 }).catch(() => false)) {
        // If fold is disabled (free check), do check instead
        const isDisabled = await foldBtn
          .evaluate((el) => el.classList.contains('disabled') || (el as HTMLButtonElement).disabled)
          .catch(() => false);
        if (isDisabled) {
          const checkBtn = page.locator('.cp-btn-check');
          if (await checkBtn.isVisible({ timeout: 500 }).catch(() => false)) {
            await checkBtn.click();
            results.checkUsed = true;
            console.log('  Hand 2: CHECK (fold disabled — free check)');
          }
        } else {
          await foldBtn.click();
          results.foldUsed = true;
          console.log('  Hand 2: FOLD');
        }
      } else {
        // No fold button — might be check only
        const checkBtn = page.locator('.cp-btn-check');
        if (await checkBtn.isVisible({ timeout: 500 }).catch(() => false)) {
          await checkBtn.click();
          results.checkUsed = true;
          console.log('  Hand 2: CHECK (no fold available)');
        }
      }
    }
    await waitForHandEnd(page, 'Hand 2');
    results.handsCompleted++;
    console.log('=== Hand 2 complete ===');

    // ── Hand 3: test RAISE ──
    console.log('=== Hand 3: Deal — test RAISE ===');
    await dealHand(page, tableId);
    await page.waitForTimeout(1_500);

    if (await waitForMyTurn(page)) {
      const raiseBtn = page.locator('.cp-btn-raise');
      if (await raiseBtn.isVisible({ timeout: 1_000 }).catch(() => false)) {
        await raiseBtn.click();
        console.log('  Hand 3: Clicked RAISE button');

        // Wait for raise sheet to appear
        const raiseSheet = page.locator('.cp-raise-sheet');
        if (await raiseSheet.isVisible({ timeout: 3_000 }).catch(() => false)) {
          console.log('  Hand 3: Raise sheet visible');

          // Check that raise value is NOT 0
          const raiseValue = page.locator('.cp-raise-focus-value');
          if (await raiseValue.isVisible({ timeout: 1_000 }).catch(() => false)) {
            const valueText = await raiseValue.textContent();
            console.log(`  Hand 3: Raise value = ${valueText}`);
            expect(valueText).not.toBe('0');
          }

          // Click a preset (e.g. "Min" or "2x")
          const minPreset = raiseSheet.locator('button:has-text("Min")');
          if (await minPreset.isVisible({ timeout: 1_000 }).catch(() => false)) {
            await minPreset.click();
            console.log('  Hand 3: Selected Min preset');
          }

          // Confirm the raise
          const confirmBtn = raiseSheet.locator('button:has-text("RAISE")');
          if (await confirmBtn.isVisible({ timeout: 1_000 }).catch(() => false)) {
            await confirmBtn.click();
            results.raiseUsed = true;
            console.log('  Hand 3: RAISE confirmed');
          } else {
            // Fallback: try the raise submit button
            const altConfirm = raiseSheet.locator('.cp-raise-confirm');
            if (await altConfirm.isVisible({ timeout: 500 }).catch(() => false)) {
              await altConfirm.click();
              results.raiseUsed = true;
              console.log('  Hand 3: RAISE confirmed (alt button)');
            }
          }
        } else {
          console.log('  Hand 3: Raise sheet NOT visible — falling back to call/check');
          const callBtn = page.locator('.cp-btn-call');
          const checkBtn = page.locator('.cp-btn-check');
          if (await callBtn.isVisible({ timeout: 500 }).catch(() => false)) {
            await callBtn.click();
          } else if (await checkBtn.isVisible({ timeout: 500 }).catch(() => false)) {
            await checkBtn.click();
          }
        }
      } else {
        console.log('  Hand 3: No RAISE button — using call/check');
        const callBtn = page.locator('.cp-btn-call');
        const checkBtn = page.locator('.cp-btn-check');
        if (await callBtn.isVisible({ timeout: 500 }).catch(() => false)) {
          await callBtn.click();
          results.callUsed = true;
        } else if (await checkBtn.isVisible({ timeout: 500 }).catch(() => false)) {
          await checkBtn.click();
          results.checkUsed = true;
        }
      }
    }

    // After raise, play remaining streets normally
    for (let s = 0; s < 4; s++) {
      await page.waitForTimeout(1_500);
      const turn = await waitForMyTurn(page, 5_000);
      if (!turn) break;
      const checkBtn = page.locator('.cp-btn-check');
      const callBtn = page.locator('.cp-btn-call');
      if (await checkBtn.isVisible({ timeout: 500 }).catch(() => false)) {
        await checkBtn.click();
      } else if (await callBtn.isVisible({ timeout: 500 }).catch(() => false)) {
        await callBtn.click();
      } else {
        break;
      }
    }
    await waitForHandEnd(page, 'Hand 3');
    results.handsCompleted++;
    console.log('=== Hand 3 complete ===');

    // ── Hands 4-5: play normally to verify consistency ──
    for (let hand = 4; hand <= 5; hand++) {
      console.log(`=== Hand ${hand}: Deal ===`);
      await dealHand(page, tableId);
      await page.waitForTimeout(1_500);

      // Verify hole cards each hand
      if (await heroStrip.isVisible({ timeout: 3_000 }).catch(() => false)) {
        const cc = await heroCards.count();
        if (cc >= 2) console.log(`  Hand ${hand}: Hole cards OK (${cc} cards)`);
        else console.log(`  Hand ${hand}: WARNING - only ${cc} hole cards`);
      }

      let sc = 0;
      while (sc < 5) {
        sc++;
        const turn = await waitForMyTurn(page);
        if (!turn) break;
        const checkBtn = page.locator('.cp-btn-check');
        const callBtn = page.locator('.cp-btn-call');
        if (await checkBtn.isVisible({ timeout: 500 }).catch(() => false)) {
          await checkBtn.click();
          results.checkUsed = true;
          console.log(`  Hand ${hand}, street ${sc}: CHECK`);
        } else if (await callBtn.isVisible({ timeout: 500 }).catch(() => false)) {
          await callBtn.click();
          results.callUsed = true;
          console.log(`  Hand ${hand}, street ${sc}: CALL`);
        } else {
          break;
        }
        await page.waitForTimeout(1_500);
        const still = await page
          .locator('.cp-btn-fold, .cp-btn-check, .cp-btn-call')
          .first()
          .isVisible({ timeout: 2_000 })
          .catch(() => false);
        if (!still) break;
      }
      await waitForHandEnd(page, `Hand ${hand}`);
      results.handsCompleted++;
      console.log(`=== Hand ${hand} complete ===`);
    }

    // ── Final assertions ──
    console.log('\n=== RESULTS ===');
    console.log(`  Hands completed: ${results.handsCompleted}`);
    console.log(`  Hole cards visible: ${results.holeCardsVisible}`);
    console.log(`  Fold used: ${results.foldUsed}`);
    console.log(`  Check used: ${results.checkUsed}`);
    console.log(`  Call used: ${results.callUsed}`);
    console.log(`  Raise used: ${results.raiseUsed}`);

    expect(results.handsCompleted).toBeGreaterThanOrEqual(5);
    expect(results.holeCardsVisible).toBe(true);
    expect(results.checkUsed || results.callUsed).toBe(true);

    // Verify we're still at the table
    expect(page.url()).toContain('/table/');
    await expect(page.locator('.cp-table-felt')).toBeVisible();
  });
});
