import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  fetchGtoPlusSamples,
  fetchGtoPlusGrid,
  fetchGtoPlusCombos,
  fetchGtoPlusPaired,
  fetchSolverGrid,
} from '../lib/api-client';
import { useStrategyBrowser } from '../stores/strategy-browser';
import { useWorkspace } from '../stores/workspace';
import { useSolverConfig } from '../stores/solver-config';
import { useSolveSession } from '../stores/solve-session';

/**
 * Auto-loads strategy data from either solver results or GTO+ samples.
 * Branches on workspace.dataSource:
 *   - 'solver': loads from solved JSONL via /strategy/grid/:config/:flop
 *   - 'gtoplus' | 'none': loads from GTO+ sample files (original behavior)
 */
export function useStrategyData() {
  const store = useStrategyBrowser();
  const dataSource = useWorkspace((s) => s.dataSource);
  const boardCards = useWorkspace((s) => s.boardCards);
  const configName = useSolverConfig((s) => s.configName);
  const solveStatus = useSolveSession((s) => s.status);
  const currentHistory = store.currentHistory;

  // Derive flopLabel from first 3 board cards
  const flopLabel =
    boardCards.length >= 3
      ? boardCards
          .slice(0, 3)
          .map((c) => c.toLowerCase())
          .join('')
      : '';

  const isSolverMode = dataSource === 'solver' && !!flopLabel && !!configName;
  const solverReady = isSolverMode && solveStatus === 'complete';

  // ─── SOLVER DATA ───

  const { data: solverGridData } = useQuery({
    queryKey: ['solverGrid', configName, flopLabel, currentHistory],
    queryFn: () => fetchSolverGrid(configName, flopLabel, 0, currentHistory),
    enabled: solverReady,
  });

  // Sync solver data to store
  useEffect(() => {
    if (!solverReady || !solverGridData) return;
    store.setDataSource('cfr');
    store.setNodeData({
      grid: solverGridData.grid,
      actions: solverGridData.actions,
      combos: [],
      context: solverGridData.context,
      summary: solverGridData.summary,
    });
    store.setSolverChildNodes(solverGridData.childNodes);
    store.clearIpData();
  }, [solverReady, solverGridData]);

  // ─── GTO+ DATA (original behavior, disabled in solver mode) ───

  const gtoPlusEnabled = !isSolverMode;

  // Auto-discover paired OOP/IP files
  const { data: pairedData } = useQuery({
    queryKey: ['gtoPlusPaired'],
    queryFn: () => fetchGtoPlusPaired(),
    enabled: gtoPlusEnabled,
  });

  // Fallback: list all sample files
  const { data: samplesData } = useQuery({
    queryKey: ['gtoPlusSamples'],
    queryFn: () => fetchGtoPlusSamples(),
    enabled: gtoPlusEnabled && !pairedData?.pairs?.length,
  });

  // Auto-select first pair or first file
  const activePair = pairedData?.pairs?.[0];
  const oopFile = gtoPlusEnabled ? activePair?.oopFile || samplesData?.files[0]?.name || '' : '';
  const ipFile = gtoPlusEnabled ? activePair?.ipFile || '' : '';

  // === OOP (primary) data ===
  const { data: gridData } = useQuery({
    queryKey: ['gtoPlusGrid', oopFile],
    queryFn: () => fetchGtoPlusGrid(oopFile),
    enabled: !!oopFile && gtoPlusEnabled,
  });

  const { data: allCombosData } = useQuery({
    queryKey: ['gtoPlusAllCombos', oopFile],
    queryFn: () => fetchGtoPlusCombos(oopFile),
    enabled: !!oopFile && gtoPlusEnabled,
  });

  const { data: handCombosData } = useQuery({
    queryKey: ['gtoPlusCombos', oopFile, store.selectedHandClass],
    queryFn: () => fetchGtoPlusCombos(oopFile, store.selectedHandClass || undefined),
    enabled: !!oopFile && !!store.selectedHandClass && gtoPlusEnabled,
  });

  // === IP (secondary) data ===
  const { data: ipGridData } = useQuery({
    queryKey: ['gtoPlusGrid', ipFile],
    queryFn: () => fetchGtoPlusGrid(ipFile),
    enabled: !!ipFile && gtoPlusEnabled,
  });

  const { data: ipAllCombosData } = useQuery({
    queryKey: ['gtoPlusAllCombos', ipFile],
    queryFn: () => fetchGtoPlusCombos(ipFile),
    enabled: !!ipFile && gtoPlusEnabled,
  });

  // Sync GTO+ OOP data to store
  useEffect(() => {
    if (!gtoPlusEnabled) return;
    if (gridData && allCombosData) {
      store.setDataSource('gtoplus');
      store.setNodeData({
        grid: gridData.grid,
        actions: gridData.actions,
        combos: allCombosData.combos,
        context: gridData.context,
        summary: gridData.summary,
      });
    }
  }, [gridData, allCombosData, gtoPlusEnabled]);

  // Sync GTO+ IP data to store
  useEffect(() => {
    if (!gtoPlusEnabled) return;
    if (ipGridData && ipAllCombosData) {
      store.setIpData({
        grid: ipGridData.grid,
        actions: ipGridData.actions,
        combos: ipAllCombosData.combos,
        context: ipGridData.context,
        summary: ipGridData.summary,
      });
    } else if (!ipFile) {
      store.clearIpData();
    }
  }, [ipGridData, ipAllCombosData, ipFile, gtoPlusEnabled]);

  const displayCombos =
    store.selectedHandClass && handCombosData ? handCombosData.combos : allCombosData?.combos || [];

  return {
    oopFile,
    ipFile,
    gridData: isSolverMode ? solverGridData : gridData,
    allCombosData,
    ipAllCombosData,
    displayCombos,
    hasData: isSolverMode ? !!solverGridData : !!gridData,
  };
}
