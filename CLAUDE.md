# Claude Notes

@AGENTS.md

The rules above are shared with Codex and are the single source of truth. Do not
restate or paraphrase them here — a second copy drifts, and the two agents then
work from different instructions. Repo rules go in `AGENTS.md`; only the
Claude-specific handoff rules below belong in this file.

## Cross-agent handoff

This repo is edited by both Codex and Claude, sometimes on the same day.

- Before starting, read the newest `handoffs/_registry.md` entry and check its
  `Owner` and `Branch`.
- If an `Active` entry is owned by the other agent, do not edit the same files on
  the shared branch. Work on `claude/<topic>` or pick up different work.
- When you finish something durable, write a handoff with `Owner: claude` and the
  branch you worked on. Conversation-only context is not a release record.
- State what you actually verified and what you did not. The other agent will
  treat your handoff as fact.

## Shared code intelligence

Both agents query the same index through the `flyto-indexer` MCP server —
registered in `.mcp.json` for Claude and `~/.codex/config.toml` for Codex.

- A `post-commit` hook reindexes this repo automatically, so committed work by the
  other agent is visible to you. Uncommitted work is not.
- If `search` or `impact` results look stale, run `flyto-index scan .` first.
- Agent scratch checkouts under `.claude/worktrees/` are excluded from the index.
  Delete them when the work is merged; they are full copies of the repo.
