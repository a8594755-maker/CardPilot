import type { ClubRules } from '@cardpilot/shared-types';

export function RulesSummary({ rules }: { rules: ClubRules }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-[11px]">
      <div>
        <span className="text-slate-500">Stakes:</span>{' '}
        <span className="text-slate-300">
          {rules.stakes.smallBlind}/{rules.stakes.bigBlind}
        </span>
      </div>
      <div>
        <span className="text-slate-500">Seats:</span>{' '}
        <span className="text-slate-300">{rules.maxSeats}</span>
      </div>
      <div>
        <span className="text-slate-500">Buy-in:</span>{' '}
        <span className="text-slate-300">
          {rules.buyIn.minBuyIn}–{rules.buyIn.maxBuyIn}
        </span>
      </div>
      <div>
        <span className="text-slate-500">Timer:</span>{' '}
        <span className="text-slate-300">
          {rules.time.actionTimeSec}s + {rules.time.timeBankSec}s bank
        </span>
      </div>
      <div>
        <span className="text-slate-500">Variant:</span>{' '}
        <span className="text-slate-300">{rules.extras.gameType === 'omaha' ? 'PLO' : 'NLH'}</span>
      </div>
      <div>
        <span className="text-slate-500">Run-it-twice:</span>{' '}
        <span className="text-slate-300">{rules.runit.allowRunItTwice ? 'Yes' : 'No'}</span>
      </div>
      <div>
        <span className="text-slate-500">Spectators:</span>{' '}
        <span className="text-slate-300">{rules.moderation.allowSpectators ? 'Yes' : 'No'}</span>
      </div>
      <div>
        <span className="text-slate-500">Auto-deal:</span>{' '}
        <span className="text-slate-300">
          {rules.dealing.autoDealEnabled ? `${rules.dealing.autoDealDelaySec}s` : 'Off'}
        </span>
      </div>
      <div>
        <span className="text-slate-500">Chat:</span>{' '}
        <span className="text-slate-300">{rules.moderation.chatEnabled ? 'On' : 'Off'}</span>
      </div>
      <div>
        <span className="text-slate-500">7-2 Bounty:</span>{' '}
        <span className="text-slate-300">
          {rules.extras.sevenTwoBounty > 0 ? rules.extras.sevenTwoBounty : 'Off'}
        </span>
      </div>
    </div>
  );
}
