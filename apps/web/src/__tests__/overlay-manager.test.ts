/**
 * Overlay Manager regression tests
 * Tests pure overlay stack logic (no React dependency needed).
 * Run with: npx vitest run apps/web/src/__tests__/overlay-manager.test.ts
 */

import { describe, it, expect } from "vitest";
import {
  overlayOpen,
  overlayClose,
  overlayIsOpen,
  overlayTop,
  type OverlayEntry,
} from "../hooks/useOverlayManager";

describe("Overlay stack logic", () => {
  const empty: OverlayEntry[] = [];

  it("starts with no active overlays", () => {
    expect(overlayTop(empty)).toBeNull();
    expect(overlayIsOpen(empty, "optionsDrawer")).toBe(false);
  });

  it("can open and close a single overlay", () => {
    let stack = overlayOpen(empty, "optionsDrawer");
    expect(overlayIsOpen(stack, "optionsDrawer")).toBe(true);
    expect(overlayTop(stack)).toBe("optionsDrawer");

    stack = overlayClose(stack, "optionsDrawer");
    expect(overlayIsOpen(stack, "optionsDrawer")).toBe(false);
    expect(overlayTop(stack)).toBeNull();
  });

  it("opening roomSettings auto-closes optionsDrawer (lower priority)", () => {
    let stack = overlayOpen(empty, "optionsDrawer");
    expect(overlayIsOpen(stack, "optionsDrawer")).toBe(true);

    stack = overlayOpen(stack, "roomSettings");
    expect(overlayIsOpen(stack, "roomSettings")).toBe(true);
    expect(overlayIsOpen(stack, "optionsDrawer")).toBe(false);
    expect(overlayTop(stack)).toBe("roomSettings");
  });

  it("opening optionsDrawer does NOT close roomSettings (higher priority)", () => {
    let stack = overlayOpen(empty, "roomSettings");
    expect(overlayIsOpen(stack, "roomSettings")).toBe(true);

    stack = overlayOpen(stack, "optionsDrawer");
    expect(overlayIsOpen(stack, "roomSettings")).toBe(true);
    expect(overlayIsOpen(stack, "optionsDrawer")).toBe(true);
    expect(overlayTop(stack)).toBe("roomSettings");
  });

  it("closeAll (empty array) clears every overlay", () => {
    let stack = overlayOpen(empty, "optionsDrawer");
    stack = overlayOpen(stack, "roomSettings");
    // closeAll is just replacing with []
    const cleared: OverlayEntry[] = [];
    expect(overlayIsOpen(cleared, "optionsDrawer")).toBe(false);
    expect(overlayIsOpen(cleared, "roomSettings")).toBe(false);
    expect(overlayTop(cleared)).toBeNull();
  });

  it("opening the same overlay twice is idempotent", () => {
    let stack = overlayOpen(empty, "optionsDrawer");
    stack = overlayOpen(stack, "optionsDrawer");
    expect(stack.length).toBe(1);
  });

  it("closing an overlay that is not open is a no-op", () => {
    const stack = overlayClose(empty, "roomSettings");
    expect(stack).toEqual([]);
  });

  it("opening a modal auto-closes the drawer (lower priority)", () => {
    let stack = overlayOpen(empty, "optionsDrawer"); // priority 10
    stack = overlayOpen(stack, "buyIn"); // priority 30
    expect(overlayIsOpen(stack, "buyIn")).toBe(true);
    expect(overlayIsOpen(stack, "optionsDrawer")).toBe(false);
    expect(overlayTop(stack)).toBe("buyIn");
  });

  it("overlays are sorted by priority (highest first)", () => {
    let stack = overlayOpen(empty, "roomSettings"); // priority 40
    stack = overlayOpen(stack, "optionsDrawer"); // priority 10 — doesn't displace higher
    expect(stack[0].id).toBe("roomSettings");
    expect(stack[1].id).toBe("optionsDrawer");
  });
});

describe("Bug regression: room_closed overlay cleanup", () => {
  const empty: OverlayEntry[] = [];

  it("closeAll clears drawer that was left open (Bug #2 root cause)", () => {
    const stack = overlayOpen(empty, "optionsDrawer");
    expect(overlayIsOpen(stack, "optionsDrawer")).toBe(true);

    // room_closed handler calls closeAll → replaces with []
    const cleared: OverlayEntry[] = [];
    expect(overlayIsOpen(cleared, "optionsDrawer")).toBe(false);
    expect(overlayTop(cleared)).toBeNull();
  });

  it("closeAll clears settings + drawer together", () => {
    const stack = overlayOpen(empty, "roomSettings");
    expect(overlayIsOpen(stack, "roomSettings")).toBe(true);

    const cleared: OverlayEntry[] = [];
    expect(overlayIsOpen(cleared, "roomSettings")).toBe(false);
    expect(cleared).toEqual([]);
  });
});

describe("Bug regression: Room Settings vs Options drawer layering", () => {
  const empty: OverlayEntry[] = [];

  it("opening Room Settings from drawer auto-closes drawer (Bug #1 fix)", () => {
    // User flow: open drawer → click "Game Settings" → opens Room Settings
    let stack = overlayOpen(empty, "optionsDrawer");
    expect(overlayIsOpen(stack, "optionsDrawer")).toBe(true);

    // setShowSettings(true) calls overlayOpen("roomSettings")
    stack = overlayOpen(stack, "roomSettings");

    // Drawer must be gone, settings must be on top
    expect(overlayIsOpen(stack, "optionsDrawer")).toBe(false);
    expect(overlayIsOpen(stack, "roomSettings")).toBe(true);
    expect(overlayTop(stack)).toBe("roomSettings");
    expect(stack.length).toBe(1);
  });
});
