import { useSolverConfig } from '../../stores/solver-config';

export function LimitBetTab() {
  const { limitConfig, setLimitConfig } = useSolverConfig();

  return (
    <div style={{ padding: '24px 32px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Flop */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span
            className="gto-label"
            style={{ width: 80, textAlign: 'right', color: '#1a7a7a', fontWeight: 600 }}
          >
            Flop bet
          </span>
          <input
            type="number"
            value={limitConfig.flopBet}
            onChange={(e) => setLimitConfig({ flopBet: Number(e.target.value) })}
            className="gto-input"
            style={{ width: 80, textAlign: 'center' }}
            min={0}
          />
          <span
            className="gto-label"
            style={{ width: 30, textAlign: 'right', color: '#1a7a7a', fontWeight: 600 }}
          >
            Cap
          </span>
          <input
            type="number"
            value={limitConfig.flopCap}
            onChange={(e) => setLimitConfig({ flopCap: Number(e.target.value) })}
            className="gto-input"
            style={{ width: 80, textAlign: 'center' }}
            min={0}
          />
        </div>

        {/* Turn */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span
            className="gto-label"
            style={{ width: 80, textAlign: 'right', color: '#1a7a7a', fontWeight: 600 }}
          >
            Turn bet
          </span>
          <input
            type="number"
            value={limitConfig.turnBet}
            onChange={(e) => setLimitConfig({ turnBet: Number(e.target.value) })}
            className="gto-input"
            style={{ width: 80, textAlign: 'center' }}
            min={0}
          />
          <span
            className="gto-label"
            style={{ width: 30, textAlign: 'right', color: '#1a7a7a', fontWeight: 600 }}
          >
            Cap
          </span>
          <input
            type="number"
            value={limitConfig.turnCap}
            onChange={(e) => setLimitConfig({ turnCap: Number(e.target.value) })}
            className="gto-input"
            style={{ width: 80, textAlign: 'center' }}
            min={0}
          />
        </div>

        {/* River */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span
            className="gto-label"
            style={{ width: 80, textAlign: 'right', color: '#1a7a7a', fontWeight: 600 }}
          >
            River bet
          </span>
          <input
            type="number"
            value={limitConfig.riverBet}
            onChange={(e) => setLimitConfig({ riverBet: Number(e.target.value) })}
            className="gto-input"
            style={{ width: 80, textAlign: 'center' }}
            min={0}
          />
          <span
            className="gto-label"
            style={{ width: 30, textAlign: 'right', color: '#1a7a7a', fontWeight: 600 }}
          >
            Cap
          </span>
          <input
            type="number"
            value={limitConfig.riverCap}
            onChange={(e) => setLimitConfig({ riverCap: Number(e.target.value) })}
            className="gto-input"
            style={{ width: 80, textAlign: 'center' }}
            min={0}
          />
        </div>
      </div>

      {/* Memory estimate */}
      <div style={{ marginTop: 32 }}>
        <div className="gto-summary">
          Estimated memory:{' '}
          {estimateMemory(limitConfig.flopCap, limitConfig.turnCap, limitConfig.riverCap)} GB
        </div>
      </div>
    </div>
  );
}

function estimateMemory(flopCap: number, turnCap: number, riverCap: number): string {
  // Rough estimate based on tree complexity
  const nodes = flopCap * turnCap * riverCap * 1326 * 2;
  const bytesPerNode = 64;
  const gb = (nodes * bytesPerNode) / (1024 * 1024 * 1024);
  return gb.toFixed(1);
}
