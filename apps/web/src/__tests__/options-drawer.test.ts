/**
 * Options Drawer regression tests
 * Ensures "Game Settings" and all menu items are always present.
 * Run with: npx vitest run apps/web/src/__tests__/options-drawer.test.ts
 */

import { describe, it, expect } from 'vitest';
import { OPTIONS_ITEMS } from '../config/optionsMenuItems';

describe('OPTIONS_ITEMS config', () => {
  it('contains Game Settings entry', () => {
    const settings = OPTIONS_ITEMS.find((item) => item.id === 'settings');
    expect(settings).toBeDefined();
    expect(settings!.label).toBe('Game Settings');
    expect(settings!.icon).toBeTruthy();
  });

  it('contains Players entry', () => {
    const players = OPTIONS_ITEMS.find((item) => item.id === 'players');
    expect(players).toBeDefined();
    expect(players!.label).toBe('Players');
  });

  it('contains Profile & Preferences entry', () => {
    const profile = OPTIONS_ITEMS.find((item) => item.id === 'profile');
    expect(profile).toBeDefined();
    expect(profile!.requiresHost).toBe(false);
  });

  it('contains all expected entries in correct order', () => {
    const ids = OPTIONS_ITEMS.map((item) => item.id);
    expect(ids).toEqual([
      'deal',
      'stand',
      'sit_toggle',
      'rebuy',
      'display_bb',
      'anim_speed',
      'sound',
      'theme',
      'bomb_pot',
      'pause_resume',
      'end_game',
      'settings',
      'players',
      'close_room',
      'gto',
      'hand_history',
      'stats',
      'log',
      'profile',
      'lobby',
    ]);
  });

  it('Game Settings, Players, and other host items require host', () => {
    const hostIds = ['settings', 'players', 'bomb_pot', 'pause_resume', 'end_game', 'close_room'];
    for (const id of hostIds) {
      const item = OPTIONS_ITEMS.find((i) => i.id === id);
      expect(item).toBeDefined();
      expect(item!.requiresHost).toBe(true);
    }
  });

  it('GTO Coach, Stats, Log, Profile, Lobby do NOT require host', () => {
    const nonHostIds = ['gto', 'stats', 'log', 'profile', 'lobby'];
    for (const id of nonHostIds) {
      const item = OPTIONS_ITEMS.find((i) => i.id === id);
      expect(item).toBeDefined();
      expect(item!.requiresHost).toBe(false);
    }
  });

  it('every item has a unique id', () => {
    const ids = OPTIONS_ITEMS.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('every item has an analyticsName', () => {
    for (const item of OPTIONS_ITEMS) {
      expect(item.analyticsName).toBeTruthy();
    }
  });

  it('settings items have settingsTab defined', () => {
    const settingsItems = OPTIONS_ITEMS.filter((item) => item.settingsTab);
    expect(settingsItems.length).toBeGreaterThanOrEqual(2);
    const tabs = settingsItems.map((item) => item.settingsTab);
    expect(tabs).toContain('game');
    expect(tabs).toContain('players');
  });
});

describe('Drawer sections builder (host vs guest)', () => {
  function buildSections(isHostOrCoHost: boolean) {
    return OPTIONS_ITEMS.map((item) => {
      const isDisabled = item.requiresHost && !isHostOrCoHost;
      return {
        id: item.id,
        label: item.label,
        disabled: isDisabled,
        disabledLabel: isDisabled ? 'Host only' : undefined,
      };
    });
  }

  it('host sees all items enabled', () => {
    const sections = buildSections(true);
    expect(sections.length).toBe(OPTIONS_ITEMS.length);
    for (const section of sections) {
      expect(section.disabled).toBe(false);
    }
  });

  it('guest sees all items present, host-only items disabled', () => {
    const sections = buildSections(false);
    expect(sections.length).toBe(OPTIONS_ITEMS.length);

    const settingsSection = sections.find((s) => s.id === 'settings')!;
    expect(settingsSection.disabled).toBe(true);
    expect(settingsSection.disabledLabel).toBe('Host only');

    const playersSection = sections.find((s) => s.id === 'players')!;
    expect(playersSection.disabled).toBe(true);

    const profileSection = sections.find((s) => s.id === 'profile')!;
    expect(profileSection.disabled).toBe(false);
    expect(profileSection.disabledLabel).toBeUndefined();
  });

  it('Game Settings is NEVER removed from the list regardless of role', () => {
    for (const isHost of [true, false]) {
      const sections = buildSections(isHost);
      const found = sections.find((s) => s.id === 'settings');
      expect(found).toBeDefined();
      expect(found!.label).toBe('Game Settings');
    }
  });
});
