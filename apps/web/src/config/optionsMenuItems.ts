/**
 * Single source of truth for Options drawer menu items.
 * Rendered by OptionsDrawer — never hardcode menu items in JSX elsewhere.
 *
 * Permission model:
 * - requiresHost: item is disabled (not hidden) for non-host users
 * - requiresSeated: item is disabled (not hidden) when user is not seated
 * - Items are NEVER removed based on hand phase or table state.
 */

export type SettingsTab = 'game' | 'players' | 'preferences';

export type MenuGroup = 'player' | 'display' | 'host' | 'tools' | 'nav';

export const GROUP_LABELS: Record<MenuGroup, string> = {
  player: 'Player',
  display: 'Display',
  host: 'Host Controls',
  tools: 'Tools',
  nav: '',
};

export interface OptionsMenuItem {
  id: string;
  label: string;
  icon: string;
  group: MenuGroup;
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
  /* ── Player actions ── */
  {
    id: 'deal',
    label: 'Deal Hand',
    icon: '🃏',
    group: 'player',
    requiresHost: false,
    requiresSeated: true,
    action: 'deal_hand',
    analyticsName: 'drawer_deal',
  },
  {
    id: 'stand',
    label: 'Stand Up',
    icon: '🧍',
    group: 'player',
    requiresHost: false,
    requiresSeated: true,
    action: 'stand_up',
    analyticsName: 'drawer_stand',
  },
  {
    id: 'sit_toggle',
    label: 'Sit In / Sit Out',
    icon: '💺',
    group: 'player',
    requiresHost: false,
    requiresSeated: true,
    action: 'sit_toggle',
    analyticsName: 'drawer_sit_toggle',
  },
  {
    id: 'rebuy',
    label: 'Rebuy',
    icon: '💰',
    group: 'player',
    requiresHost: false,
    requiresSeated: true,
    action: 'rebuy',
    analyticsName: 'drawer_rebuy',
  },
  /* ── Display & audio toggles ── */
  {
    id: 'display_bb',
    label: 'Toggle BB / Chips',
    icon: '🔢',
    group: 'display',
    requiresHost: false,
    requiresSeated: false,
    action: 'toggle_display_bb',
    analyticsName: 'drawer_display_bb',
  },
  {
    id: 'anim_speed',
    label: 'Animation Speed',
    icon: '✨',
    group: 'display',
    requiresHost: false,
    requiresSeated: false,
    action: 'cycle_anim_speed',
    analyticsName: 'drawer_anim_speed',
  },
  {
    id: 'sound',
    label: 'Toggle Sound',
    icon: '🔊',
    group: 'display',
    requiresHost: false,
    requiresSeated: false,
    action: 'toggle_sound',
    analyticsName: 'drawer_sound',
  },
  {
    id: 'theme',
    label: 'Table Theme',
    icon: '🎨',
    group: 'display',
    requiresHost: false,
    requiresSeated: false,
    action: 'cycle_theme',
    analyticsName: 'drawer_theme',
  },
  /* ── Host controls ── */
  {
    id: 'bomb_pot',
    label: 'Bomb Pot',
    icon: '💣',
    group: 'host',
    requiresHost: true,
    requiresSeated: false,
    action: 'queue_bomb_pot',
    analyticsName: 'drawer_bomb_pot',
  },
  {
    id: 'pause_resume',
    label: 'Pause / Resume',
    icon: '⏸️',
    group: 'host',
    requiresHost: true,
    requiresSeated: false,
    action: 'pause_resume',
    analyticsName: 'drawer_pause_resume',
  },
  {
    id: 'end_game',
    label: 'End Auto-Deal',
    icon: '⏹️',
    group: 'host',
    requiresHost: true,
    requiresSeated: false,
    action: 'end_game',
    analyticsName: 'drawer_end_game',
  },
  {
    id: 'settings',
    label: 'Game Settings',
    icon: '⚙️',
    group: 'host',
    requiresHost: true,
    requiresSeated: false,
    settingsTab: 'game',
    analyticsName: 'drawer_game_settings',
  },
  {
    id: 'players',
    label: 'Players',
    icon: '👥',
    group: 'host',
    requiresHost: true,
    requiresSeated: false,
    settingsTab: 'players',
    analyticsName: 'drawer_players',
  },
  {
    id: 'close_room',
    label: 'Close Room',
    icon: '🔒',
    group: 'host',
    requiresHost: true,
    requiresSeated: false,
    action: 'close_room',
    analyticsName: 'drawer_close_room',
  },
  /* ── Tools & info ── */
  {
    id: 'gto',
    label: 'GTO Coach',
    icon: '🎯',
    group: 'tools',
    requiresHost: false,
    requiresSeated: false,
    action: 'toggle_gto',
    analyticsName: 'drawer_gto_coach',
  },
  {
    id: 'hand_history',
    label: 'Hand History',
    icon: '📜',
    group: 'tools',
    requiresHost: false,
    requiresSeated: false,
    action: 'toggle_hand_history',
    analyticsName: 'drawer_hand_history',
  },
  {
    id: 'stats',
    label: 'Session Stats',
    icon: '📊',
    group: 'tools',
    requiresHost: false,
    requiresSeated: false,
    action: 'toggle_stats',
    analyticsName: 'drawer_session_stats',
  },
  {
    id: 'log',
    label: 'Room Log',
    icon: '📋',
    group: 'tools',
    requiresHost: false,
    requiresSeated: false,
    action: 'toggle_log',
    analyticsName: 'drawer_room_log',
  },
  /* ── Navigation ── */
  {
    id: 'profile',
    label: 'Profile & Preferences',
    icon: '👤',
    group: 'nav',
    requiresHost: false,
    requiresSeated: false,
    action: 'open_profile',
    analyticsName: 'drawer_profile',
  },
  {
    id: 'lobby',
    label: 'Back to Lobby',
    icon: '🏠',
    group: 'nav',
    requiresHost: false,
    requiresSeated: false,
    action: 'back_to_lobby',
    analyticsName: 'drawer_back_to_lobby',
  },
] as const;
