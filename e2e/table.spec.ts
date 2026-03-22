import { test, expect, type Page } from '@playwright/test';

test.setTimeout(60_000);

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
 * Wait for the socket connection indicator to show "Online" / "Connected".
 * Returns true if connected, false if timed out.
 */
async function waitForSocketConnection(page: Page, timeoutMs = 8_000): Promise<boolean> {
  try {
    // The lobby shows a "Connected" label next to a green dot
    await page
      .locator('text=/Connected|Online/')
      .first()
      .waitFor({ state: 'visible', timeout: timeoutMs });
    return true;
  } catch {
    return false;
  }
}

/**
 * Helper: create a room and navigate to table view.
 * Requires game-server to be running.
 */
async function createRoomAndNavigate(page: Page) {
  // If "Go to Table" is already visible (room exists from server state), use that
  const goToTableBtn = page.locator('button:has-text("Go to Table")');
  if (await goToTableBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await goToTableBtn.click();
    await page.waitForURL(/\/table\//, { timeout: 15_000 });
    return;
  }

  // Otherwise create a new room
  const createBtn = page.locator('button:has-text("Create Room")');
  await expect(createBtn).toBeVisible({ timeout: 10_000 });
  await createBtn.click();

  // Wait for table URL (server responds with room_joined → AppContent navigates to /table/)
  await page.waitForURL(/\/table\//, { timeout: 15_000 });
}

// ---------------------------------------------------------------------------
// These tests require the game-server to be running on port 4000.
// They are skipped when the server is unreachable.
// ---------------------------------------------------------------------------
test.describe('Table (requires game-server)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsGuest(page, 'TableBot');
    const connected = await waitForSocketConnection(page);
    if (!connected) {
      test.skip(true, 'Game server not reachable — skipping table tests');
    }
  });

  test('can create a room and see the table', async ({ page }) => {
    await createRoomAndNavigate(page);

    expect(page.url()).toContain('/table/');
    await expect(page.locator('.cp-table-felt')).toBeVisible({ timeout: 10_000 });
  });

  test('table has empty seats', async ({ page }) => {
    await createRoomAndNavigate(page);

    const emptySeats = page.locator('[data-empty-seat]');
    await expect(emptySeats.first()).toBeVisible({ timeout: 10_000 });

    const count = await emptySeats.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  test('empty seat shows +Sit label', async ({ page }) => {
    await createRoomAndNavigate(page);

    await expect(page.locator('[data-empty-seat] .cp-seat-empty-label').first()).toContainText(
      '+Sit',
    );
  });

  test('table renders community card area', async ({ page }) => {
    await createRoomAndNavigate(page);

    await expect(page.locator('.cp-board-row')).toBeVisible({ timeout: 10_000 });
    // Should have 5 empty card slots when no hand is active
    const slots = page.locator('.cp-board-slot');
    await expect(slots).toHaveCount(5);
  });

  test('pot anchor is present', async ({ page }) => {
    await createRoomAndNavigate(page);

    await expect(page.locator('.cp-pot-anchor')).toBeAttached({ timeout: 10_000 });
  });

  test('seat ring container is visible', async ({ page }) => {
    await createRoomAndNavigate(page);

    await expect(page.locator('.cp-seat-ring')).toBeVisible({ timeout: 10_000 });
  });

  test('clicking empty seat opens buy-in modal', async ({ page }) => {
    await createRoomAndNavigate(page);

    const emptySeats = page.locator('[data-empty-seat]');
    await emptySeats.first().click();

    // Buy-in modal
    await expect(page.locator('text=Buy In')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('button:has-text("Sit Down")')).toBeVisible();
  });

  test('buy-in modal has slider and quick-pick buttons', async ({ page }) => {
    await createRoomAndNavigate(page);

    await page.locator('[data-empty-seat]').first().click();
    await expect(page.locator('text=Buy In')).toBeVisible({ timeout: 5_000 });

    // Range slider
    await expect(page.locator('input[type="range"]')).toBeVisible();
    // "chips" label
    await expect(page.locator('text=chips')).toBeVisible();
  });

  test('can sit down and see player name', async ({ page }) => {
    await createRoomAndNavigate(page);

    await page.locator('[data-empty-seat]').first().click();
    await expect(page.locator('button:has-text("Sit Down")')).toBeVisible({ timeout: 5_000 });
    await page.locator('button:has-text("Sit Down")').click();

    // Modal should close
    await expect(page.locator('text=Buy In')).not.toBeVisible({ timeout: 5_000 });

    // Player name should appear in one of the seats
    await expect(page.locator('.cp-seat-name').first()).toBeVisible({ timeout: 10_000 });
  });

  test('table top bar shows room info and exit button', async ({ page }) => {
    await createRoomAndNavigate(page);

    // Exit button
    const exitBtn = page.locator('.cp-table-exit-btn');
    await expect(exitBtn).toBeVisible({ timeout: 5_000 });
    await expect(exitBtn).toContainText('Lobby');
  });

  test('can exit table back to lobby', async ({ page }) => {
    await createRoomAndNavigate(page);

    await page.locator('.cp-table-exit-btn').click();
    await page.waitForURL(/\/lobby/, { timeout: 10_000 });
    await expect(page.locator('.cp-lobby-title').first()).toBeVisible();
  });
});
