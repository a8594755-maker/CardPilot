# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Sit Out / Sit In**: Players can toggle sit-out status from the table controls. Sitting-out players keep their seat and stack but are excluded from dealing. Server enforces hand-boundary deferral. "SIT OUT" badge shown on seat chip.
- **Host Self-Rebuy**: Hosts and co-hosts can rebuy themselves without waiting for approval. Rebuy requests are auto-approved server-side; UI shows "Top Up" instead of "Request".
- **Table Switching**: "Change Table" button in table header navigates to lobby. Confirms and defers stand-up if a hand is in progress.
- **Club V2 UX**: Club overview tab upgraded with stats strip (members, active tables, total tables), active-table quick-join cards, and restructured layout.
- 4 new sit-out regression tests in `rules-room-controls.test.ts`.

### Changed
- **Footer**: `AppLegalFooter` hidden during table view to prevent overlap with action bar. Rendered once at app shell level on all other views.
- **Green Felt Table**: Replaced 5 MB `poker-table.png` with CSS-drawn `.poker-table-surface` ellipse (radial gradient + subtle felt noise texture + wood border/shadow).
- Enhanced `.poker-table-surface` CSS with inner glow and refined box-shadow.

### Fixed
- Host self-rebuy deadlock: hosts no longer get stuck with infinite pending deposits when they are the only admin online.

---

### Added (previous)
- Runtime config module with validation for server environment and operational timeouts.
- `/healthz` endpoint for operational health reporting.
- Graceful shutdown handling for `SIGINT`/`SIGTERM`.
- Structured JSON logging helper for key server lifecycle and hand events.
- GitHub Actions CI for lint/typecheck/tests/build plus non-blocking security checks.
- Privacy and Terms pages (`/privacy`, `/terms`) with visible play-money disclaimer links.
- Governance docs: `SECURITY.md`, `CONTRIBUTING.md`, `RELEASE.md`, `CODEOWNERS`.
- Issue template and pull request template.
- Game-engine smoke test for start-to-settlement lifecycle invariants.

### Changed
- Root scripts standardized for CI parity (`lint`, `test`, `build:web`, `build:server`, `ci:verify`).
- Environment examples expanded with required web/server/runtime variables.
- README updated with run/test/build guidance and product-readiness docs.
