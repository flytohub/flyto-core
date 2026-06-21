# Architecture Map

## Core Areas

- `src/core`: module execution, recipe bundle support, browser and automation
  primitives.
- `workflows`: checked-in workflow assets, examples, and process notes.
- `tests`: recipe bundle and module regression checks.
- `scripts`: project-memory and release support gates.
- `docs` and `handoffs`: durable architecture and audit context.

## Cross-Repo Edges

- `flyto-code` uses core workflows for browser and frontend product-loop smoke.
- `flyto-engine` uses core workflows for backend/API release validation.
- `flyto-admin` can use core workflows for operator cockpit checks.
- `flyto-indexer` verifies core repository closure and architecture hygiene.
