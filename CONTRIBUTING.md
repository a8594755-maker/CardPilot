# Contributing

## Prerequisites

- Node.js `>=20` (see `.nvmrc`)
- npm (workspace-aware, lockfile is `package-lock.json`)

## Setup

```bash
npm install
cp .env.example .env.local
```

## Local Development

```bash
npm run dev
```

## Required Quality Checks

Before opening a PR, run:

```bash
npm run lint
npm run typecheck
npm run test
npm run build:web
npm run build:server
```

## Branch Naming

Use predictable prefixes:

- `feat/<short-description>`
- `fix/<short-description>`
- `chore/<short-description>`
- `docs/<short-description>`

## Pull Request Standards

- Keep scope focused and reviewable.
- Include risk notes and rollback notes for behavior changes.
- Include screenshots for UI changes.
- Include manual test steps for multiplayer/poker flows when applicable.
- Do not change poker rules/settlement logic unless the PR explicitly targets engine correctness.

## Commit Guidance

- Use clear imperative messages.
- Group related changes.
- Avoid mixing refactors with behavior changes unless required.
