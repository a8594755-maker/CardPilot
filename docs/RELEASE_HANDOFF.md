# CardPilot Release Handoff

Last updated: 2026-03-18

## Purpose

This document is the final delivery and release handoff for the current CardPilot closure pass.
It merges the verified release state from `docs/PROJECT_CLOSURE_CHECKLIST.md` with the defect log and prevention notes from `CODE_REVIEW_REPORT.md`.

## Current verified state

- `npm run ci:verify` passes
- `npm run format:check` passes
- `npm run lint` passes
- `npm run typecheck` passes
- `npm run test` passes
- `npm run build:web` passes
- `npm run build:server` passes

## Release change list

### 1. Quality gates restored

- Reduced lint warnings from `195` to `0`
- Re-established a passing full verification path through `npm run ci:verify`
- Brought the web, server, and shared package boundaries back to a buildable state

### 2. Active web app path stabilized

- Restored the active web entry path to:
  - `apps/web/src/main.tsx`
  - `apps/web/src/App.tsx`
  - `apps/web/src/AppContent.tsx`
  - `apps/web/src/providers/AppProviders.tsx`
- Removed or isolated stale duplicate files that were not part of the real app path
- Prevented recurring backup files from breaking validation by excluding:
  - `apps/web/src/**/*Final.ts`
  - `apps/web/src/**/*Final.tsx`
  - `apps/web/src/**/*.bak`

### 3. Contract and runtime alignment

- Updated socket contract coverage so tests validate the actual active web socket surface
- Realigned club access checks to the active frontend source path
- Added the missing frontend listener for the server `connected` handshake event

### 4. High-impact code fixes from review

- Rebuilt `packages/poker-evaluator/src/card-utils.ts` after source corruption broke typechecking
- Corrected React setter typing in `apps/web/src/hooks/useGameSocketEvents.ts`
- Simplified redundant state handling in `apps/web/src/contexts/GameContext.tsx`
- Removed dead code and unused imports/locals across the main warning clusters:
  - `apps/web`
  - `apps/game-server`
  - `packages/cfr-solver`
  - supporting shared packages

## Defects fixed and prevention rules

### Fixed defects

- Broken function body and syntax corruption in `packages/poker-evaluator/src/card-utils.ts`
- Incorrect hook setter typing that rejected `prev => ...` updater callbacks
- Redundant context state that existed only to satisfy a setter path
- Stale duplicate entry files causing drift between the active app and the files developers were editing
- Review noise from dead code, unused imports, and obsolete helpers

### Prevention rules

- Use `Dispatch<SetStateAction<T>>` for React state setters passed across hooks or context
- Run `typecheck + build` immediately after extracting hooks, context, or entry-path files
- Do not leave backup or experimental `*Final.tsx` files inside the active source tree unless they are ignored on purpose
- Remove dead imports, dead state, and dead helpers in the same change that makes them obsolete
- Do not leave command output or scratch files in the repo root

## Remaining known risk

- Some external or local workflow is recreating `*Final.tsx` backup files under `apps/web/src`
- These files are now excluded from Prettier, ESLint, and the web TypeScript project so they do not block release validation
- If active development resumes later, identify and remove the process that regenerates them

## Final commit and tag guidance

### Current working tree assessment

Based on the current `git status`, the repo does not show pending application code changes for release.
The visible pending items are:

- `CODE_REVIEW_REPORT.md` as a new documentation file
- `.claude/settings.local.json` as a local settings change
- `EZ-GTO/` as an untracked external workspace/artifact directory

### Safe to include in the final release commit

- `CODE_REVIEW_REPORT.md`
- `docs/PROJECT_CLOSURE_CHECKLIST.md`
- `docs/RELEASE_HANDOFF.md`

### Keep out of the final release commit

- `.claude/settings.local.json`
- `EZ-GTO/`
- local logs, caches, and generated folders such as `node_modules`, `dist`, `.data`, `logs`, `tmp`, `models`, and local env files

### Tag recommendation

- Cut the final tag from the commit that contains:
  - the already-verified application code
  - the release documentation listed above
- Do not include local workstation settings or external experiment directories in the tagged state

## Closure steps before tag

1. Stage only the release documentation files
2. Confirm `git status` no longer includes local config or external workspace paths in the staged set
3. Re-run `npm run ci:verify` if any code changes are introduced after this point
4. Create the release commit
5. Tag the verified commit
6. Record deployment URL, env ownership, and final commit SHA in the release notes or ops store

## Definition of done

The project is ready to close when:

- the release commit is created from the verified tree,
- the tag points to that verified commit,
- the deployment target matches the tagged code,
- operational ownership and runtime configuration are captured outside the repo,
- and no further code changes are required to pass `npm run ci:verify`.
