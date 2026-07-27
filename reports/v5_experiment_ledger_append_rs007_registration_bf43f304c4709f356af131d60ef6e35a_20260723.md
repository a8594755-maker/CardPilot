# V5 experiment ledger append — RS007 registration

Timestamp: 2026-07-23 01:23 EDT  
Goal: ACTIVE  
Strength: L0  
Official hands: 0  
Route exhausted: false

## Empirical transition-domain census

A read-only recomputation over all four frozen H11 quick5k decision dumps classified
each observed exact increment against the current H11 nine-slot table and an independent
basic poker-legality predicate.

- Total actions: 29,878
- Source-scoped hands: 5,000
- Adjacent prefix transitions: 24,878
- Hero actions: 12,564; exact policy-slot membership: 12,564; external: 0
- Opponent actions: 17,314; exact policy-slot membership: 15,656
- Poker-legal opponent bet/raise targets outside the policy table: 1,658
- Basic poker-illegal observed actions: 0
- External targets span preflop/flop/turn/river: 852/442/196/168

The out-of-slot rate is 5.5492% of all actions and 9.5761% of opponent actions. This
proves a material two-domain boundary. It does not authorize nearest-slot projection:
projection would alter commitments, pot, stack, later legality and terminal utility.

- Census SHA:
  `1e8dcf9488c287d5409dac9ad8304ebd835c1a6ce70e590b42e1d53ce1d5810a`
- Census audit SHA:
  `82ff469aad769e6e61cf88270d8472844a95b711c4ef5258169f7354ed9b73fb`
- Audit result:
  `RS007_TRANSITION_DOMAIN_CENSUS_PASS_PUBLIC_AND_POLICY_DOMAINS_DISTINCT`

## RS007 frozen design

Fresh identity/token:

`bf43f304c4709f356af131d60ef6e35a52a7456d215987abce8180419c4ed6d0` /
`bf43f304c4709f356af131d60ef6e35a`

Preregistration SHA:

`0b881b6b5651a23dea03f625cb0e8d4880752e5286f7f2cd145eda46980beeeb`

Independent preregistration audit SHA:

`aa0f6582ac80a814f7d116a736d245440121ddcf1cc46b126a0adf67adff7a97`

Audit result: PASS 167/167,
`RS007_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_LATER_ONLY`.

The design freezes two non-overlapping APIs:

1. `apply_public_increment` accepts exact raw `k/c/f/b<street-target>` from source
   replay, external opponent play, or an already-resolved policy slot. It applies
   poker legality directly and may not inspect the policy table.
2. `apply_policy_slot` accepts only slot 0–8, requires an exact non-null one-to-one
   table entry that is public-legal, and delegates the unchanged increment to the
   public API. External actions may never enter through this API.

Exact legality includes initial blind/BB-option state, check/call/fold requirements,
minimum full bet/raise, short all-in, raise reopening and non-reopening, opponent-all-in
no-raise, street closure, 3/1/1 chance dealing and terminal closure.

The future qualification must prove:

- all 29,878 preaction rows and all 24,878 adjacent transitions;
- all 1,658 external targets accepted bit-exact with projection count zero;
- all 12,564 hero actions identical through policy-slot and public paths;
- a 4 streets × 2 actors × 16 scenarios × 32 repeats = 4,096 boundary matrix;
- 6,921 live postflop observation/logit interfaces;
- 1,280 terminal rows, 8,192 comparator deals, 1,280 MC32 resolutions;
- 192 exact repeats, 128 fault fallbacks, frozen latency/resource gates;
- unchanged H11 checkpoint before/after.

RS007 must be implemented from scratch. RS005/RS006 import, copy, wrapper, monkeypatch,
partial output or result authority is forbidden.

## Stop boundary

No runner, launcher, auditor, implementation audit, qualification root, quick5k root,
GPU process, checkpoint, network hand, Slumbot hand or official hand exists for RS007.
Next later only is one fresh combined implementation, ledger-derived deep self-test,
exactly two launcher-bound zero-file probes, implementation audit, one qualification,
one result audit and exact judgment. Stop before quick5k even after a full qualification
PASS.
