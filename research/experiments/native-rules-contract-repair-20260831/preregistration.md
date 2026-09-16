# Versioned native rules/action/observation contract repair

Registered before implementation or validation trajectories on 2026-08-31.
Parent: native-state-contract-audit-20260831. This is infrastructure repair,
not a policy-strength experiment. The five saved counterexamples motivate it;
their frequency and causal contribution to external loss remain unknown.

## Scope and invariants

Create an explicit new contract/version; preserve legacy engine, environment,
checkpoint bytes, completed raw evidence and execution snapshots. Equal-stack
200bb HU NLHE uses 100 integer chips per bb, blinds 50/100, no rake and no raise
cap. Validate BB option after SB completion, full minimum bets/raises, short
all-ins, chip conservation, dealing without duplicates, street/actor/terminal
transitions and zero-sum payoff. Illegal actions must fail, never silently
substitute a passive action. Preserve input tensor shapes while recording true
street and BET-versus-RAISE semantics independently of all-in status. History
capacity may truncate within a street but cannot misassign subsequent streets.
One explicit versioned slot-to-physical-action contract must be shared by new
training, internal evaluation and deployment adapters before production use.

## Independent oracle and validation

Pin PokerKit 0.7.5 in this experiment's isolated oracle_vendor directory, retain
downloaded wheel and its SHA256. Expected wheel SHA256 from official PyPI:
3e1a0b2a8a9785369c86e2c1392dd2204ee536fbcbe77a779c875bd545eb63e8.
Use official TDA 2024 rules 34B,43,47,48 for heads-up order, full raises and no
raise cap, plus PokerKit independent state transitions/hand evaluation. Sources:
https://www.pokertda.com/view-poker-tda-rules/
https://pokerkit.readthedocs.io/en/stable/simulation.html
https://pypi.org/project/pokerkit/0.7.5/

First implement directed regressions for the five counterexamples and additional
boundary cases, then compare seeded complete trajectories against the oracle.
Fixed randomized validation budget: 4096 equal-stack 200bb hands, seed20260915;
further directed boundary fixtures are separately named. Every discrepancy is a
failure requiring retained evidence and repair, not a dropped hand or changed
seed. Record test attempts, exact commands, source hashes/copies, elapsed wall
time and completed validation-hand count separately from training/evaluation.
No policy training, model selection, benchmark outcomes, Slumbot or network calls
are allowed during validation (dependency fetch before validation is allowed).
Development tests may run repeatedly; retain distinct attempt reports and do not
count them as independent strength evidence. A separate full validation run and
source snapshot are required after implementation stabilizes.

## Decision gate

Require all directed tests and all4096 oracle trajectories to pass, matching
actor, street, cards, stacks, pot, legal physical actions and payoff as applicable.
Then require new environment and shared adapter mask/action/observation parity,
and trainer/evaluator/deployment integration tests before declaring the whole
contract ready. A core-only pass is explicitly insufficient for training or100k
qualification. Fail closed on unknown/missing contract metadata in new entry
points; legacy reproduction remains separately callable. Review artifacts and
finish this record only when its declared scope passes or is explicitly failed.
Start new corrected-environment strength experiments separately; never pool old
legacy mirror outcomes with new-contract results.

First exact command:
python -m pip download --no-deps --only-binary=:all: pokerkit==0.7.5 --dest research/experiments/native-rules-contract-repair-20260831/oracle_wheels
