/**
 * Single source of truth for Options drawer menu items.
 * Rendered by OptionsDrawer — never hardcode menu items in JSX elsewhere.
 *
 * Permission model:
 * - requiresHost: item is disabled (not hidden) for non-host users
 * - requiresSeated: item is disabled (not hidden) when user is not seated
 * - Items are NEVER removed based on hand phase or table state.
 */

export type SettingsTab = "game" | "players" | "preferences" | "video-audio";

export interface OptionsMenuItem {
  id: string;
  label: string;
  icon: string;
  /** If true, item is disabled (with "Host only" label) for non-host/co-host users */
  requiresHost: boolean;
  /** If true, item is disabled when user is not seated */
  requiresSeated: boolean;
  /** If set, clicking opens the settings modal at this tab */
  settingsTab?: SettingsTab;
  /** Action identifier for non-settings items */
  action?: string;
  /** Analytics event name for telemetry */
  analyticsName: string;
}

/**
 * Canonical menu item definitions.
 * Order here = render order in the drawer.
 */
export const OPTIONS_ITEMS: readonly OptionsMenuItem[] = [
  {
    id: "settings",
    label: "Game Settings",
    icon: "⚙️",
    requiresHost: true,
    requiresSeated: false,
    settingsTab: "game",
    analyticsName: "drawer_game_settings",
  },
  {
    id: "players",
    label: "Players",
    icon: "👥",
    requiresHost: true,
    requiresSeated: false,
    settingsTab: "players",
    analyticsName: "drawer_players",
  },
  {
    id: "preferences",
    label: "Preferences",
    icon: "🎨",
    requiresHost: false,
    requiresSeated: false,
    settingsTab: "preferences",
    analyticsName: "drawer_preferences",
  },
  {
    id: "video-audio",
    label: "Video / Audio",
    icon: "🎙️",
    requiresHost: false,
    requiresSeated: false,
    settingsTab: "video-audio",
    analyticsName: "drawer_video_audio",
  },
  {
    id: "gto",
    label: "GTO Coach",
    icon: "🎯",
    requiresHost: false,
    requiresSeated: false,
    action: "toggle_gto",
    analyticsName: "drawer_gto_coach",
  },
  {
    id: "stats",
    label: "Session Stats",
    icon: "📊",
    requiresHost: false,
    requiresSeated: false,
    action: "toggle_stats",
    analyticsName: "drawer_session_stats",
  },
  {
    id: "log",
    label: "Room Log",
    icon: "📋",
    requiresHost: false,
    requiresSeated: false,
    action: "toggle_log",
    analyticsName: "drawer_room_log",
  },
  {
    id: "profile",
    label: "Profile & Preferences",
    icon: "👤",
    requiresHost: false,
    requiresSeated: false,
    action: "open_profile",
    analyticsName: "drawer_profile",
  },
  {
    id: "lobby",
    label: "Back to Lobby",
    icon: "🏠",
    requiresHost: false,
    requiresSeated: false,
    action: "back_to_lobby",
    analyticsName: "drawer_back_to_lobby",
  },
] as const;
