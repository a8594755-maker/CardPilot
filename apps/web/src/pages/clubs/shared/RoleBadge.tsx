import type { ClubRole } from '@cardpilot/shared-types';

const ROLE_BADGE_COLORS: Record<string, string> = {
  owner: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  admin: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  member: 'bg-white/5 text-slate-400 border-white/10',
};

export function RoleBadge({ role, size = 'sm' }: { role: ClubRole | string; size?: 'xs' | 'sm' }) {
  const cls = ROLE_BADGE_COLORS[role] ?? ROLE_BADGE_COLORS.member;
  const sz = size === 'xs' ? 'text-[8px] px-1 py-0.5' : 'text-[9px] px-1.5 py-0.5';
  return <span className={`${sz} rounded border ${cls} uppercase font-semibold`}>{role}</span>;
}

export { ROLE_BADGE_COLORS };
