## 2026-07-22T21:44:32Z - LG002 single recovery forbidden alternate-path CENSURE

- CENSURE SHA256:
  `78e46e590b349904f5019c69fd040100a62548040ff3cceae50f4ced97162f14`;
  embedded checks PASS22/22.
- The one permitted recovery token `2320b32682e51ba0e3781407b92d3d75` had a canonical
  preregistration/audit `ef41b731de6ad74f93d01cbb2f4ce245bcde9323335e331a6c31f0daf3e9eda9` /
  `318899d0b0f1bfbfe80867473cf5ad192500379f6e8cc23479de22c9ef29bdec`.
  The audit reported PASS100/100 and a pre-refresh snapshot/shard were written,but the
  registration shard was never appended to the main ledger.
- A later different-path,different-bytes preregistration using the same identity and
  token appeared at SHA
  `9f04a6005ccd8802846a42120032691ac0219632380e3b1396eb961dfab026b9`.
  This violates the canonical preregistration's explicit `alternate_path=FORBIDDEN`
  and `same_basis_existing_different_bytes=TERMINAL_FAIL_CLOSED_NO_SECOND_RECOVERY`.
- The canonical registration,audit,alternate file and unappended registration shard
  now have authority NONE. Preserve them without overwrite,merge,repair,
  reclassification or descendant use. Do not append the recovery-registration shard.
- No implementation,contract probe,training,output root,checkpoint,GPU,evaluator,
  Slumbot or official hand ran. The opponent-league hypothesis remains untested;
  all four scientific routes remain open;route exhaustion false/unjudged;L0.
- The single recovery is consumed and a second recovery is forbidden. Next later only:
  one simplified reporting-only route-review preregistration plus independent audit to
  select another ranked family or a non-recovery league route if supported. Stop before
  review result,implementation or execution.

