import { Dialog, DialogContent } from '../ui/Dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/Tabs';
import { useSolverConfig } from '../../stores/solver-config';
import { CashTab } from './CashTab';
import { SngTab } from './SngTab';
import { MttTab } from './MttTab';
import { DialogFooter } from './DialogFooter';

export function StacksDialog() {
  const {
    stacksDialogOpen,
    closeStacksDialog,
    gameType,
    setGameType,
    cashConfig,
    setCashConfig,
    sngConfig,
    updateSngPlayer,
    addSngPlayer,
    removeSngPlayer,
    setSngStartingPot,
    mttConfig,
    updateMttPlayer,
    addMttPlayer,
    removeMttPlayer,
    setMttStartingPot,
    syncTreeConfig,
  } = useSolverConfig();

  const handleBuildTree = () => {
    syncTreeConfig();
    closeStacksDialog();
  };

  return (
    <Dialog open={stacksDialogOpen} onOpenChange={(open) => !open && closeStacksDialog()}>
      <DialogContent title="Effective Stacks, Pot and Rake">
        <Tabs value={gameType} onValueChange={(v) => setGameType(v as 'cash' | 'sng' | 'mtt')}>
          <TabsList>
            <TabsTrigger value="cash">Cash Game</TabsTrigger>
            <TabsTrigger value="sng">SNG</TabsTrigger>
            <TabsTrigger value="mtt">MTT</TabsTrigger>
          </TabsList>

          <TabsContent value="cash">
            <CashTab config={cashConfig} onChange={setCashConfig} />
          </TabsContent>

          <TabsContent value="sng">
            <SngTab
              players={sngConfig.players}
              startingPot={sngConfig.startingPot}
              onUpdatePlayer={updateSngPlayer}
              onAdd={addSngPlayer}
              onRemove={removeSngPlayer}
              onStartingPotChange={setSngStartingPot}
            />
          </TabsContent>

          <TabsContent value="mtt">
            <MttTab
              players={mttConfig.players}
              startingPot={mttConfig.startingPot}
              onUpdatePlayer={updateMttPlayer}
              onAdd={addMttPlayer}
              onRemove={removeMttPlayer}
              onStartingPotChange={setMttStartingPot}
            />
          </TabsContent>
        </Tabs>

        <DialogFooter onClose={closeStacksDialog} onBuildTree={handleBuildTree} />
      </DialogContent>
    </Dialog>
  );
}
