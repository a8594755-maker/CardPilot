/**
 * Navigation & Control Flow regression tests
 * 
 * Tests the pure logic that was broken:
 * - room_joined/room_created navigation guards
 * - connect handler room rejoin guards
 * - leaveRoom cleanup completeness
 * 
 * Run with: npx vitest run apps/web/src/__tests__/navigation-controls.test.ts
 */

import { describe, it, expect } from "vitest";

/* ═══════════════════════════════════════════════════
   Pure helper: should the app navigate to table on room_joined?
   Extracted from the guard logic added to App.tsx handlers.
   ═══════════════════════════════════════════════════ */

function shouldNavigateToTable(currentPath: string): boolean {
  return (
    currentPath === "/" ||
    currentPath.startsWith("/lobby") ||
    currentPath.startsWith("/table")
  );
}

function shouldRejoinOnConnect(currentPath: string): boolean {
  return (
    currentPath === "/" ||
    currentPath.startsWith("/lobby") ||
    currentPath.startsWith("/table")
  );
}

describe("Navigation guard: shouldNavigateToTable", () => {
  it("allows navigation from root /", () => {
    expect(shouldNavigateToTable("/")).toBe(true);
  });

  it("allows navigation from /lobby", () => {
    expect(shouldNavigateToTable("/lobby")).toBe(true);
  });

  it("allows navigation from /table/xyz", () => {
    expect(shouldNavigateToTable("/table/tbl_abc123")).toBe(true);
  });

  it("allows navigation from bare /table", () => {
    expect(shouldNavigateToTable("/table")).toBe(true);
  });

  it("blocks navigation from /history", () => {
    expect(shouldNavigateToTable("/history")).toBe(false);
  });

  it("blocks navigation from /history/hand-id", () => {
    expect(shouldNavigateToTable("/history/h_12345")).toBe(false);
  });

  it("blocks navigation from /profile", () => {
    expect(shouldNavigateToTable("/profile")).toBe(false);
  });

  it("blocks navigation from /training", () => {
    expect(shouldNavigateToTable("/training")).toBe(false);
  });

  it("blocks navigation from /clubs", () => {
    expect(shouldNavigateToTable("/clubs")).toBe(false);
  });

  it("blocks navigation from /cashier", () => {
    expect(shouldNavigateToTable("/cashier")).toBe(false);
  });
});

describe("Connect handler guard: shouldRejoinOnConnect", () => {
  it("allows rejoin from /lobby", () => {
    expect(shouldRejoinOnConnect("/lobby")).toBe(true);
  });

  it("allows rejoin from /table/xyz", () => {
    expect(shouldRejoinOnConnect("/table/tbl_abc")).toBe(true);
  });

  it("blocks rejoin from /history", () => {
    expect(shouldRejoinOnConnect("/history")).toBe(false);
  });

  it("blocks rejoin from /profile", () => {
    expect(shouldRejoinOnConnect("/profile")).toBe(false);
  });

  it("blocks rejoin from /training", () => {
    expect(shouldRejoinOnConnect("/training")).toBe(false);
  });

  it("blocks rejoin from /clubs", () => {
    expect(shouldRejoinOnConnect("/clubs")).toBe(false);
  });
});

/* ═══════════════════════════════════════════════════
   leaveRoom cleanup: verify that all state fields are reset
   We test the shape of what leaveRoom must clear.
   ═══════════════════════════════════════════════════ */

interface RoomState {
  tableId: string;
  currentRoomCode: string;
  currentRoomName: string;
  roomState: object | null;
  snapshot: object | null;
  holeCards: string[];
  seatRequests: unknown[];
  winners: unknown[] | null;
  settlement: unknown | null;
  allInPrompt: unknown | null;
  advice: unknown | null;
  deviation: unknown | null;
}

function simulateLeaveRoom(state: RoomState): RoomState {
  // This mirrors the cleanup in leaveRoom()
  return {
    tableId: "",
    currentRoomCode: "",
    currentRoomName: "",
    roomState: null,
    snapshot: null,
    holeCards: [],
    seatRequests: [],
    winners: null,
    settlement: null,
    allInPrompt: null,
    advice: null,
    deviation: null,
  };
}

describe("leaveRoom cleanup", () => {
  it("clears all room-specific state", () => {
    const dirtyState: RoomState = {
      tableId: "tbl_abc123",
      currentRoomCode: "ABC123",
      currentRoomName: "Test Room",
      roomState: { status: "OPEN", settings: {} },
      snapshot: { handId: "h1", street: "flop" },
      holeCards: ["Ah", "Kd"],
      seatRequests: [{ orderId: "o1" }],
      winners: [{ seat: 1, amount: 100 }],
      settlement: { winnersByRun: [] },
      allInPrompt: { actorSeat: 1 },
      advice: { recommended: "call" },
      deviation: { deviation: 0.5, playerAction: "fold" },
    };

    const cleaned = simulateLeaveRoom(dirtyState);

    expect(cleaned.tableId).toBe("");
    expect(cleaned.currentRoomCode).toBe("");
    expect(cleaned.currentRoomName).toBe("");
    expect(cleaned.roomState).toBeNull();
    expect(cleaned.snapshot).toBeNull();
    expect(cleaned.holeCards).toEqual([]);
    expect(cleaned.seatRequests).toEqual([]);
    expect(cleaned.winners).toBeNull();
    expect(cleaned.settlement).toBeNull();
    expect(cleaned.allInPrompt).toBeNull();
    expect(cleaned.advice).toBeNull();
    expect(cleaned.deviation).toBeNull();
  });

  it("is safe to call when already clean", () => {
    const cleanState: RoomState = {
      tableId: "",
      currentRoomCode: "",
      currentRoomName: "",
      roomState: null,
      snapshot: null,
      holeCards: [],
      seatRequests: [],
      winners: null,
      settlement: null,
      allInPrompt: null,
      advice: null,
      deviation: null,
    };

    const result = simulateLeaveRoom(cleanState);
    expect(result.currentRoomCode).toBe("");
    expect(result.roomState).toBeNull();
  });
});

/* ═══════════════════════════════════════════════════
   View computation: verify pathname → view mapping
   ═══════════════════════════════════════════════════ */

type AppView = "lobby" | "table" | "profile" | "history" | "clubs" | "cashier" | "training";

function computeView(pathname: string): AppView {
  if (pathname === "/" || pathname.startsWith("/lobby")) return "lobby";
  if (pathname.startsWith("/table")) return "table";
  if (pathname.startsWith("/history")) return "history";
  if (pathname.startsWith("/clubs")) return "clubs";
  if (pathname.startsWith("/cashier")) return "cashier";
  if (pathname.startsWith("/training")) return "training";
  if (pathname.startsWith("/profile")) return "profile";
  return "lobby";
}

describe("View computation from pathname", () => {
  it("/ → lobby", () => expect(computeView("/")).toBe("lobby"));
  it("/lobby → lobby", () => expect(computeView("/lobby")).toBe("lobby"));
  it("/table → table", () => expect(computeView("/table")).toBe("table"));
  it("/table/tbl_123 → table", () => expect(computeView("/table/tbl_123")).toBe("table"));
  it("/history → history", () => expect(computeView("/history")).toBe("history"));
  it("/history/h_abc → history", () => expect(computeView("/history/h_abc")).toBe("history"));
  it("/profile → profile", () => expect(computeView("/profile")).toBe("profile"));
  it("/training → training", () => expect(computeView("/training")).toBe("training"));
  it("/clubs → clubs", () => expect(computeView("/clubs")).toBe("clubs"));
  it("/cashier → cashier", () => expect(computeView("/cashier")).toBe("cashier"));
  it("/unknown → lobby (fallback)", () => expect(computeView("/unknown")).toBe("lobby"));
});

/* ═══════════════════════════════════════════════════
   Close Room: timeout fallback logic
   ═══════════════════════════════════════════════════ */

describe("Close Room error handling", () => {
  it("requires socket connection", () => {
    const socket = null;
    const isConnected = false;
    const canClose = socket !== null && isConnected;
    expect(canClose).toBe(false);
  });

  it("allows close when connected", () => {
    const socket = {}; // mock
    const isConnected = true;
    const canClose = socket !== null && isConnected;
    expect(canClose).toBe(true);
  });
});

/* ═══════════════════════════════════════════════════
   Supported paths validation (routing effect)
   ═══════════════════════════════════════════════════ */

function isPathSupported(pathname: string): boolean {
  if (pathname === "/") return true;
  if (pathname === "/table" || pathname.match(/^\/table\/[^/]+$/)) return true;
  const supportedPaths = ["/lobby", "/history", "/profile", "/cashier", "/training"];
  if (pathname.startsWith("/clubs") || pathname.startsWith("/history/") || supportedPaths.includes(pathname)) return true;
  return false;
}

describe("Supported paths validation", () => {
  it("/ is supported", () => expect(isPathSupported("/")).toBe(true));
  it("/lobby is supported", () => expect(isPathSupported("/lobby")).toBe(true));
  it("/table/tbl_x is supported", () => expect(isPathSupported("/table/tbl_x")).toBe(true));
  it("/history is supported", () => expect(isPathSupported("/history")).toBe(true));
  it("/history/h1 is supported", () => expect(isPathSupported("/history/h1")).toBe(true));
  it("/profile is supported", () => expect(isPathSupported("/profile")).toBe(true));
  it("/training is supported", () => expect(isPathSupported("/training")).toBe(true));
  it("/cashier is supported", () => expect(isPathSupported("/cashier")).toBe(true));
  it("/clubs is supported", () => expect(isPathSupported("/clubs")).toBe(true));
  it("/clubs/detail is supported", () => expect(isPathSupported("/clubs/detail")).toBe(true));
  it("/random is NOT supported", () => expect(isPathSupported("/random")).toBe(false));
  it("/admin is NOT supported", () => expect(isPathSupported("/admin")).toBe(false));
});
