# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
