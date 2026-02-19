/**
 * Single source of truth for Options drawer menu items.
 * Rendered by OptionsDrawer — never hardcode menu items in JSX elsewhere.
 *
 * Permission model:
 * - requiresHost: item is disabled (not hidden) for non-host users
 * - requiresSeated: item is disabled (not hidden) when user is not seated
 * - Items are NEVER removed based on hand phase or table state.
 */

export type SettingsTab = "game" | "players" | "preferences";

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
  /* ── Table controls (moved from pill toolbar) ── */
  {
    id: "deal",
    label: "Deal Hand",
    icon: "🃏",
    requiresHost: false,
    requiresSeated: true,
    action: "deal_hand",
    analyticsName: "drawer_deal",
  },
  {
    id: "stand",
    label: "Stand Up",
    icon: "🧍",
    requiresHost: false,
    requiresSeated: true,
    action: "stand_up",
    analyticsName: "drawer_stand",
  },
  {
    id: "sit_toggle",
    label: "Sit In / Sit Out",
    icon: "💺",
    requiresHost: false,
    requiresSeated: true,
    action: "sit_toggle",
    analyticsName: "drawer_sit_toggle",
  },
  {
    id: "rebuy",
    label: "Rebuy",
    icon: "💰",
    requiresHost: false,
    requiresSeated: true,
    action: "rebuy",
    analyticsName: "drawer_rebuy",
  },
  {
    id: "bomb_pot",
    label: "Bomb Pot",
    icon: "💣",
    requiresHost: true,
    requiresSeated: false,
    action: "queue_bomb_pot",
    analyticsName: "drawer_bomb_pot",
  },
  /* ── Display & audio toggles ── */
  {
    id: "display_bb",
    label: "Toggle BB / Chips",
    icon: "🔢",
    requiresHost: false,
    requiresSeated: false,
    action: "toggle_display_bb",
    analyticsName: "drawer_display_bb",
  },
  {
    id: "anim_speed",
    label: "Animation Speed",
    icon: "✨",
    requiresHost: false,
    requiresSeated: false,
    action: "cycle_anim_speed",
    analyticsName: "drawer_anim_speed",
  },
  {
    id: "sound",
    label: "Toggle Sound",
    icon: "🔊",
    requiresHost: false,
    requiresSeated: false,
    action: "toggle_sound",
    analyticsName: "drawer_sound",
  },
  {
    id: "theme",
    label: "Table Theme",
    icon: "🎨",
    requiresHost: false,
    requiresSeated: false,
    action: "cycle_theme",
    analyticsName: "drawer_theme",
  },
  /* ── Host game controls ── */
  {
    id: "pause_resume",
    label: "Pause / Resume",
    icon: "⏸️",
    requiresHost: true,
    requiresSeated: false,
    action: "pause_resume",
    analyticsName: "drawer_pause_resume",
  },
  {
    id: "end_game",
    label: "End Auto-Deal",
    icon: "⏹️",
    requiresHost: true,
    requiresSeated: false,
    action: "end_game",
    analyticsName: "drawer_end_game",
  },
  {
    id: "close_room",
    label: "Close Room",
    icon: "🔒",
    requiresHost: true,
    requiresSeated: false,
    action: "close_room",
    analyticsName: "drawer_close_room",
  },
  /* ── Original settings & navigation ── */
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
