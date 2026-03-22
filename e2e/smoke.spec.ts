import { test, expect, type Page } from '@playwright/test';

// Give each test enough time for Supabase probes + network
test.setTimeout(60_000);

/**
 * Helper: enter as guest and land on lobby.
 */
async function loginAsGuest(page: Page, name = 'TestPlayer') {
  await page.goto('/');
  // Wait for auth screen
  await page.waitForSelector('.cp-auth-screen', { timeout: 15_000 });

  // Fill optional guest name
  const guestNameInput = page.locator('input[placeholder*="Enter your name"]');
  if (await guestNameInput.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await guestNameInput.fill(name);
  }

  // Click "Continue as Guest"
  const guestBtn = page.locator('button:has-text("Continue as Guest")');
  await guestBtn.waitFor({ state: 'visible', timeout: 5_000 });
  await guestBtn.click();

  // Wait for auth screen to disappear
  await page.waitForSelector('.cp-auth-screen', { state: 'detached', timeout: 30_000 });

  // Dismiss onboarding modal if it appears ("Start Playing" button)
  const startBtn = page.locator('button:has-text("Start Playing")');
  if (await startBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await startBtn.click();
    await page
      .locator('.fixed.inset-0.z-50')
      .waitFor({ state: 'detached', timeout: 5_000 })
      .catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// 1. Auth Screen
// ---------------------------------------------------------------------------
test.describe('Auth Screen', () => {
  test('shows auth screen on first visit', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.cp-auth-screen')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('.cp-auth-brand')).toBeVisible();
  });

  test('has login and signup tabs', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.cp-auth-screen', { timeout: 15_000 });
    const tabs = page.locator('.cp-auth-tab-btn');
    await expect(tabs).toHaveCount(2);
    await expect(tabs.first()).toContainText(/Log In/i);
    await expect(tabs.last()).toContainText(/Sign Up/i);
  });

  test('switching to signup shows extra fields', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.cp-auth-screen', { timeout: 15_000 });
    await page.locator('.cp-auth-tab-btn', { hasText: 'Sign Up' }).click();

    await expect(page.getByPlaceholder('How others see you')).toBeVisible();
    await expect(page.getByPlaceholder('Re-enter password')).toBeVisible();
  });

  test('has guest access button', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.cp-auth-screen', { timeout: 15_000 });
    await expect(page.locator('.cp-auth-guest-btn')).toBeVisible();
    await expect(page.locator('.cp-auth-guest-btn')).toContainText(/Continue as Guest/i);
  });

  test('guest login reaches lobby', async ({ page }) => {
    await loginAsGuest(page, 'GuestSmoke');
    await expect(page.locator('.cp-lobby-title').first()).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// 2. Lobby
// ---------------------------------------------------------------------------
test.describe('Lobby', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsGuest(page);
  });

  test('shows lobby section cards', async ({ page }) => {
    // Quick Play, Join with Code, Create a Room
    await expect(page.locator('.cp-lobby-title').first()).toBeVisible();
    await expect(page.locator('button:has-text("Create Room")')).toBeVisible();
  });

  test('lobby has join-by-code input', async ({ page }) => {
    await expect(page.getByPlaceholder('ROOM CODE')).toBeVisible();
    await expect(page.locator('button:has-text("Join")')).toBeVisible();
  });

  test('create room card has blind presets', async ({ page }) => {
    // Should see blind presets like 1/2, 1/3, etc.
    await expect(page.locator('button:has-text("1/3")')).toBeVisible();
    await expect(page.locator('button:has-text("2/5")')).toBeVisible();
  });

  test('create room card has table size options', async ({ page }) => {
    await expect(page.locator('button:has-text("Heads-up")')).toBeVisible();
    await expect(page.locator('button:has-text("6-max")')).toBeVisible();
    await expect(page.locator('button:has-text("9-max")')).toBeVisible();
  });

  test('nav bar is visible with expected links', async ({ page }) => {
    for (const label of ['Lobby', 'Profile']) {
      await expect(page.locator(`nav >> text="${label}"`).first()).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// 3. Navigation
// ---------------------------------------------------------------------------
test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsGuest(page);
  });

  test('can navigate to profile page', async ({ page }) => {
    await page.locator('nav >> text="Profile"').first().click();
    await page.waitForURL(/\/profile/, { timeout: 10_000 });
    await expect(page.locator('text=Display Name').first()).toBeVisible({ timeout: 5_000 });
  });

  test('can navigate back to lobby from profile', async ({ page }) => {
    await page.locator('nav >> text="Profile"').first().click();
    await page.waitForURL(/\/profile/, { timeout: 10_000 });
    await page.locator('nav >> text="Lobby"').first().click();
    await page.waitForURL(/\/lobby/, { timeout: 10_000 });
    await expect(page.locator('.cp-lobby-title').first()).toBeVisible();
  });

  test('can navigate to GTO strategy page', async ({ page }) => {
    const cfrNav = page.locator('nav >> text="GTO Strategy"').first();
    if (await cfrNav.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await cfrNav.click();
      await page.waitForURL(/\/cfr/, { timeout: 10_000 });
    }
  });

  test('can navigate to history page', async ({ page }) => {
    const histNav = page.locator('nav >> text="History"').first();
    if (await histNav.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await histNav.click();
      await page.waitForURL(/\/history/, { timeout: 10_000 });
    }
  });

  test('unknown routes redirect to lobby', async ({ page }) => {
    await page.goto('/nonexistent-route');
    await page.waitForURL(/\/lobby/, { timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// 4. Error Boundary
// ---------------------------------------------------------------------------
test.describe('Error Boundary', () => {
  test('no crash on lobby', async ({ page }) => {
    await loginAsGuest(page);
    await expect(page.locator('text=Something went wrong')).not.toBeVisible({ timeout: 3_000 });
  });
});
