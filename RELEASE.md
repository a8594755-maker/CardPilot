# Release Process

## Versioning Policy

CardPilot follows SemVer:

- `MAJOR`: breaking API/protocol/contract changes
- `MINOR`: backward-compatible features
- `PATCH`: backward-compatible fixes

## Pre-release Checklist

1. Confirm CI is green on `main`.
2. Update `CHANGELOG.md` under `[Unreleased]` with final release notes.
3. Run local verification:
   - `npm run ci:verify`
4. Confirm docs are current (`README.md`, `docs/OPERATIONS.md`, `SECURITY.md`).

## Cut a Release

1. Create release PR (if needed) for changelog/version docs.
2. Merge to `main`.
3. Tag the release:
   ```bash
   git checkout main
   git pull
   git tag -a vX.Y.Z -m "CardPilot vX.Y.Z"
   git push origin vX.Y.Z
   ```
4. Create GitHub Release notes from the tag and copy key entries from `CHANGELOG.md`.

## Hotfixes

- Branch from the latest release tag: `fix/<hotfix-name>`.
- Keep scope minimal and include risk notes.
- Bump PATCH version and publish a dedicated release tag.
