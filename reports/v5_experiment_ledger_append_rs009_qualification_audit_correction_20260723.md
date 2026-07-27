# Append-only ledger shard: RS009 qualification and audit correction

Timestamp: 2026-07-23T01:48:00-04:00  
Boundary: RS009 qualification audited; quick5k authorized  
Classification: `PASS / RS009_DERIVED_RESULT_AUDIT_CORRECTION_PASS`

The sole qualification nonce `RS009_QUALIFICATION_2036972301` completed once.
Invocation/result SHAs are
`d5925450f6a7840ce92a3b637cb2bb1ec9a1b3b102b2252f139d05e34df4ef70` /
`48473c7b7796fa4c337c9838fdb6c419b811597a15f178bc43a7aff4e1cb1e92`.
Qualification PASS23/23 covers 29,878 source rows, 24,878 adjacent transitions,
1,658 exact external opponent actions, 12,564 hero dual-path actions, 4,096
boundary rows, 6,921 live interfaces, 1,280 exact terminal rows, 8,192 comparator
deals, 1,280 MC32 resolutions, 192 repeats, and 128 faults. Fallback is0 and
selected-slot change rate is0.3734375. The checkpoint is unchanged.

The one frozen result audit SHA
`d4b5d79f59ed5b674a4f654bf490c01d21d55226a5e436da944cfaff575b3b99`
failed46/48 solely because its inherited RS007 constants expected the parent
preregistration/audit byte-count and SHA pairs. All46 scientific, manifest,
checkpoint, metric, resource, and classification checks passed.

Evidence-bundle recovery replayed no science and mutated no frozen artifact. Derived
correction audit SHA
`1fdfd02de68b4f39ed3210b8df6d5038c09aa4f621d7e65dc511a8b55b90e54f`
PASS22/22 pins the failed audit, validates the two actual RS009 preregistration
identities, and independently rehashes every raw gzip artifact and row count. It
authorizes the required quick5k.

Network/Slumbot/official hands0;new checkpoint0;behavior window0;strength L0;route
exhaustion false;goal ACTIVE. Next is one governed, independently audited
greedy-direct RS009 quick5k as4x1250 with complete hand+decision evidence and the
frozen directional/mechanism gates.
