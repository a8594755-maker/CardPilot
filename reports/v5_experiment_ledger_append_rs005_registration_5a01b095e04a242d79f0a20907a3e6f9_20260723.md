## 2026-07-23 00:12 EDT — RS005 fully-live terminal-utility resolver registered

- Classification: `PASS / RS005_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_LATER_ONLY`.
- Identity: `5a01b095e04a242d79f0a20907a3e6f9d59c61780cf9a73765138cdb1f205bde`;token `5a01b095e04a242d79f0a20907a3e6f9`.
- Preregistration: `70a232c8cbbef807e2530ba19e35f887b143d9e0f226cd443385d04e9a0a0c8c`, 22,175 bytes.
- Independent preregistration audit: `7f6b4800a7c22588f01fc02f8b1c632d8496fc2737fc8c0187faa39943d735c4`, 13,101 bytes, PASS170/170 with26/26 inputs exact.
- Pre-refresh snapshot: `ac4b514e7874ff3e7ef9ccba5cd26a7988ec1e37c23c51e904813d5d7343797b`, 3,100 bytes.

RS005 is a fresh non-descendant design. One fully-live state exclusively owns public
actions,exact-cent commitments,legal executable slots,street/chance advance,board
runout,terminal class,uncalled-excess refund and zero-sum payout. HUNLGameState,
HUNL Action/chance/`is_terminal()`/`payoff()` and RS004 runtime imports are forbidden.
The sole permitted deep-CFR runtime primitive is pure
`compare_hands(hole0,hole1,five-card board)`.

Payout is frozen in integer cents. On fold,the folder loses its own total contribution
and the winner gains the same amount. At showdown `M=min(total0,total1)`:player0 win
is `[+M,-M]`,player1 win is `[-M,+M]`,tie is `[0,0]`;unmatched excess is returned.
The independent audit checked worked unequal-contribution and full-stack examples and
all sums are zero.

Qualification freezes29,878 ledger rows,584 prefixes,24,878 within-hand transitions,
6,921 live hero interfaces,8,192 synthetic states,20x64=1,280 terminal-utility rows,
1,280 resolution rows,192 repeats and128 faults. It requires32 distinct hidden pairs,
strict positive paired one-sided LCB95 else baseline,fallback<=0.02,action-change>=0.01,
fixed latency/resource bounds,checkpoint immutability and complete result audit.

One later implementation boundary may create four fresh files,run a deep self-test,
exactly two launcher-bound zero-file probes,an implementation audit,one qualification,
one result audit and exact judgment. Full qualification PASS then mandates one complete
greedy-direct4x1,250 quick5k;quick5k remains directional only.

All implementation/output paths are absent. No implementation,probe,qualification,
training,GPU behavior work,checkpoint,network,evaluation or Slumbot hand occurred.
Behavior0;control49;official0;L0;route exhaustion false;goal active.

Next later only:the combined RS005 implementation-through-qualification boundary;stop
before quick5k.
