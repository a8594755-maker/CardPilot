import { useMemo } from "react";
import type { RoomFullState } from "@cardpilot/shared-types";

export interface UserRole {
  isHost: boolean;
  isCoHost: boolean;
  isHostOrCoHost: boolean;
  isSeated: boolean;
  canEditGame: boolean;
  canEditPlayers: boolean;
  canEditPreferences: boolean;
}

/**
 * Stable role detection for the current user at a table.
 * Deterministic: returns consistent defaults when data is loading.
 * Does NOT flicker between renders — all values are memoized.
 */
export function useUserRole(
  roomState: RoomFullState | null | undefined,
  userId: string | null | undefined,
  seatIndex: number | null | undefined
): UserRole {
  return useMemo(() => {
    const isHost = !!(roomState && userId && roomState.ownership.ownerId === userId);
    const isCoHost = !!(roomState && userId && roomState.ownership.coHostIds.includes(userId));
    const isHostOrCoHost = isHost || isCoHost;
    const isSeated = seatIndex != null && seatIndex >= 0;

    return {
      isHost,
      isCoHost,
      isHostOrCoHost,
      isSeated,
      canEditGame: isHostOrCoHost,
      canEditPlayers: isHost,
      canEditPreferences: true, // everyone can edit their own preferences
    };
  }, [roomState, userId, seatIndex]);
}
