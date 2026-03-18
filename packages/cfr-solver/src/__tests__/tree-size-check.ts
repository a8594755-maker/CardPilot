import { buildTree, countNodes } from '../tree/tree-builder.js';
import { COACHING_BET_SIZES } from '../tree/tree-config.js';

for (const cap of [0, 1, 2]) {
  const tree = buildTree({
    startingPot: 5,
    effectiveStack: 97.5,
    betSizes: COACHING_BET_SIZES,
    raiseCapPerStreet: cap,
    numPlayers: 2,
    advancedConfig: {
      oop: {
        noDonkBet: false,
        allInThresholdEnabled: true,
        allInThresholdPct: 30,
        remainingBetAllIn: true,
        remainingBetPct: 25,
      },
      ip: {
        noDonkBet: false,
        allInThresholdEnabled: true,
        allInThresholdPct: 30,
        remainingBetAllIn: true,
        remainingBetPct: 25,
      },
    },
  });
  const counts = countNodes(tree);
  console.log(`raiseCap=${cap}: ${counts.action} action, ${counts.terminal} terminal`);
}
