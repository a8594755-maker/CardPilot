/**
 * Options Drawer regression tests
 * Ensures "Game Settings" and all menu items are always present.
 * Run with: npx vitest run apps/web/src/__tests__/options-drawer.test.ts
 */

import { describe, it, expect } from "vitest";
import { OPTIONS_ITEMS } from "../config/optionsMenuItems";

describe("OPTIONS_ITEMS config", () => {
  it("contains Game Settings entry", () => {
    const settings = OPTIONS_ITEMS.find((item) => item.id === "settings");
    expect(settings).toBeDefined();
    expect(settings!.label).toBe("Game Settings");
    expect(settings!.icon).toBeTruthy();
  });

  it("contains Players entry", () => {
    const players = OPTIONS_ITEMS.find((item) => item.id === "players");
    expect(players).toBeDefined();
    expect(players!.label).toBe("Players");
  });

  it("contains Preferences entry", () => {
    const prefs = OPTIONS_ITEMS.find((item) => item.id === "preferences");
    expect(prefs).toBeDefined();
    expect(prefs!.requiresHost).toBe(false);
  });


  it("contains all expected entries in correct order", () => {
    const ids = OPTIONS_ITEMS.map((item) => item.id);
    expect(ids).toEqual([
      "settings", "players", "preferences",
      "gto", "stats", "log", "profile", "lobby",
    ]);
  });

  it("Game Settings and Players require host", () => {
    const settings = OPTIONS_ITEMS.find((item) => item.id === "settings")!;
    const players = OPTIONS_ITEMS.find((item) => item.id === "players")!;
    expect(settings.requiresHost).toBe(true);
    expect(players.requiresHost).toBe(true);
  });

  it("Preferences, GTO Coach, Stats, Log, Profile, Lobby do NOT require host", () => {
    const nonHostIds = ["preferences", "gto", "stats", "log", "profile", "lobby"];
    for (const id of nonHostIds) {
      const item = OPTIONS_ITEMS.find((i) => i.id === id);
      expect(item).toBeDefined();
      expect(item!.requiresHost).toBe(false);
    }
  });

  it("every item has a unique id", () => {
    const ids = OPTIONS_ITEMS.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("every item has an analyticsName", () => {
    for (const item of OPTIONS_ITEMS) {
      expect(item.analyticsName).toBeTruthy();
    }
  });

  it("settings items have settingsTab defined", () => {
    const settingsItems = OPTIONS_ITEMS.filter((item) => item.settingsTab);
    expect(settingsItems.length).toBeGreaterThanOrEqual(3);
    const tabs = settingsItems.map((item) => item.settingsTab);
    expect(tabs).toContain("game");
    expect(tabs).toContain("players");
    expect(tabs).toContain("preferences");
  });
});

describe("Drawer sections builder (host vs guest)", () => {
  function buildSections(isHostOrCoHost: boolean) {
    return OPTIONS_ITEMS.map((item) => {
      const isDisabled = item.requiresHost && !isHostOrCoHost;
      return {
        id: item.id,
        label: item.label,
        disabled: isDisabled,
        disabledLabel: isDisabled ? "Host only" : undefined,
      };
    });
  }

  it("host sees all items enabled", () => {
    const sections = buildSections(true);
    expect(sections.length).toBe(OPTIONS_ITEMS.length);
    for (const section of sections) {
      expect(section.disabled).toBe(false);
    }
  });

  it("guest sees all items present, host-only items disabled", () => {
    const sections = buildSections(false);
    expect(sections.length).toBe(OPTIONS_ITEMS.length);

    const settingsSection = sections.find((s) => s.id === "settings")!;
    expect(settingsSection.disabled).toBe(true);
    expect(settingsSection.disabledLabel).toBe("Host only");

    const playersSection = sections.find((s) => s.id === "players")!;
    expect(playersSection.disabled).toBe(true);

    const prefsSection = sections.find((s) => s.id === "preferences")!;
    expect(prefsSection.disabled).toBe(false);
    expect(prefsSection.disabledLabel).toBeUndefined();
  });

  it("Game Settings is NEVER removed from the list regardless of role", () => {
    for (const isHost of [true, false]) {
      const sections = buildSections(isHost);
      const found = sections.find((s) => s.id === "settings");
      expect(found).toBeDefined();
      expect(found!.label).toBe("Game Settings");
    }
  });
});
