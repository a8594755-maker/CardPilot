import { Dialog, DialogContent } from '../ui/Dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/Tabs';
import { useSolverConfig } from '../../stores/solver-config';
import { GeometricBetTab } from './GeometricBetTab';
import { AdvancedBetTab } from './AdvancedBetTab';
import { LimitBetTab } from './LimitBetTab';
import { DialogFooter } from './DialogFooter';

export function DecisionTreeDialog() {
  const {
    treeDialogOpen,
    closeTreeDialog,
    geometricConfig,
    setAllInBetIndex,
    updateGeometricBetAmount,
    cashConfig,
    sngConfig,
    gameType,
    syncTreeConfig,
  } = useSolverConfig();

  const startingPot = gameType === 'cash' ? cashConfig.startingPot : sngConfig.startingPot;
  const effectiveStack =
    gameType === 'cash' ? cashConfig.effectiveStack : (sngConfig.players[0]?.chipCount ?? 1000);

  const handleBuildTree = () => {
    syncTreeConfig();
    closeTreeDialog();
  };

  return (
    <Dialog open={treeDialogOpen} onOpenChange={(open) => !open && closeTreeDialog()}>
      <DialogContent title="Build Decision Tree" className="!max-w-[720px] !w-[720px]">
        <Tabs defaultValue="basic">
          <TabsList>
            <TabsTrigger value="basic">Basic</TabsTrigger>
            <TabsTrigger value="rebuild">Rebuild</TabsTrigger>
            <TabsTrigger value="advanced">Advanced</TabsTrigger>
            <TabsTrigger value="limit">Limit</TabsTrigger>
          </TabsList>

          <TabsContent value="basic">
            <GeometricBetTab
              config={geometricConfig}
              startingPot={startingPot}
              effectiveStack={effectiveStack}
              onAllInBetIndexChange={setAllInBetIndex}
              onBetAmountChange={updateGeometricBetAmount}
            />
          </TabsContent>

          <TabsContent value="rebuild">
            <div style={{ padding: '60px 20px', textAlign: 'center' }}>
              <button
                onClick={handleBuildTree}
                className="gto-btn gto-btn-secondary"
                style={{ fontSize: 14, padding: '10px 24px' }}
              >
                Rebuild with current settings
              </button>
            </div>
          </TabsContent>

          <TabsContent value="advanced">
            <AdvancedBetTab />
          </TabsContent>

          <TabsContent value="limit">
            <LimitBetTab />
          </TabsContent>
        </Tabs>

        <DialogFooter
          onSaveDefault={() => {
            /* TODO: persist defaults */
          }}
          onClose={closeTreeDialog}
          onBuildTree={handleBuildTree}
        />
      </DialogContent>
    </Dialog>
  );
}
