# Backup and restore

Git stores source code, tests, research indexes, and compact experiment records.
Weights, raw evidence, local credentials and frozen runtime snapshots require
the separate backup. Ignoring a file is not proof that it has been backed up.

## September 16, 2026 backup

Destination: `D:\Computer_Backup_2026-09-16\Projects\CardPilot\research`.
This preserves the entire research tree, not a reduced checkpoint selection.
Progress and per-file SHA-256 records are under
`D:\Computer_Backup_2026-09-16\Verification\research`.

The copy-only runner is `scripts/backup_research_to_d.py`. Its destination is
specific to the originating machine. It never deletes source files. Source
bytes are hashed while copying and independently hashed at the destination.
Interrupted copies can resume; failed and changing files require review.

A running backup or a pushed commit does not establish that deletion is safe.
Check final completion, errors, coverage and source changes first. Outside
`research`, model baselines, teacher datasets, ignored tools and `.env.local`
also need verified preservation. Never commit credentials to this public repo.

## Restore

1. Clone the repository and check out the recorded backup branch/commit.
2. Restore the research tree from the external drive to the project.
3. Restore supplemental local assets and private configuration if present.
4. Reinstall dependencies using project manifests and the experiment's recorded
   Python/PyTorch environment.
5. Verify checkpoint hashes and correct machine-specific absolute paths.
6. Follow the experiment resume contract. RAM and in-flight work are not
   preserved by a file backup.

`CardPilot_legacy_20260829` is outside this backup scope. Some historical
experiments refer to it. Do not delete it on the assumption that backing up the
current project's research directory also backs up that separate directory.
