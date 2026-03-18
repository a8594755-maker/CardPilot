# Project Closure Checklist

Last updated: 2026-03-18

## Current release state

- `npm run ci:verify` passes
- `npm run format:check` passes
- `npm run lint` passes
- `npm run typecheck` passes
- `npm run test` passes
- `npm run build:web` passes
- `npm run build:server` passes

## What was stabilized

- Removed or isolated stale duplicate entry files that were not part of the active app path
- Reduced lint warnings from 195 to 0
- Restored the active web entry path to:
  - `apps/web/src/main.tsx`
  - `apps/web/src/App.tsx`
  - `apps/web/src/AppContent.tsx`
  - `apps/web/src/providers/AppProviders.tsx`
- Updated contract tests to validate the actual active web socket surface instead of obsolete single-file assumptions
- Added ignore/exclude coverage for recurring backup files:
  - `apps/web/src/**/*Final.ts`
  - `apps/web/src/**/*Final.tsx`
  - `apps/web/src/**/*.bak`

## Remaining known risk

- Some external/local workflow is recreating `*Final.tsx` backup files under `apps/web/src`.
- These files are now excluded from Prettier, ESLint, and the web TypeScript project so they no longer block release validation.
- If active development continues later, identify and remove the process that regenerates them.

## Closure steps

1. Freeze scope.
   No new features, schema changes, or protocol changes without reopening validation.
2. Cut a release commit.
   Use the current passing tree as the baseline for the final tag or deployment branch.
3. Capture runtime configuration.
   Archive production env vars, deployment targets, Supabase/project settings, and any external tokens in your secure ops store.
4. Capture data ownership.
   Record where club data, training artifacts, CFR outputs, and model artifacts are stored, who owns them, and retention expectations.
5. Run deployment smoke checks.
   Verify login, lobby load, join room, table snapshot, action submit, club access gating, and web build artifact deployment.
6. Lock documentation.
   Keep `README.md`, deployment docs, and operational runbooks aligned with the final supported workflow.
7. Triage the backlog.
   Mark unfinished experiments, generated scripts, and non-release artifacts as either archived, deferred, or unsupported.
8. Tag handoff state.
   Record the exact commit/tag that passed `npm run ci:verify`.

## Recommended archive bundle

- Final commit SHA
- Deployment URL(s)
- Environment variable inventory
- Database/project identifiers
- Release notes / known limitations
- This closure checklist
- `CODE_REVIEW_REPORT.md`

## Definition of done

The project is ready to close when:

- the release commit is tagged,
- the deployed environment matches the verified branch,
- operational ownership is documented,
- backup/experimental files are either archived or explicitly unsupported,
- and no additional code changes are needed to pass `npm run ci:verify`.
