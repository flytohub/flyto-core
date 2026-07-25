# Flyto2 Roadmap

## Strategic Priorities

### 0. Warroom Deterministic Verification
- Deterministic graph, scenario generation, replay, report, and LLM-review
  boundary in `flyto-core`
- Multi-route BFS crawler for arbitrary sites
- Stronger state-machine inference, visual diff scoring, and Cloud Warroom UI
  integration

### 0.5. Reverse-Engineering Toolkit
- **Phase 1 (done, 2026-07-25):** `reverse.*` interactive JS debugger on CDP's
  Debugger domain — attach/detach, script list/get_source/search, set/remove
  breakpoints, pause/resume/step, call-frame inspection, and
  `evaluate_on_call_frame`. Gated behind the deny-by-default `browser.debug`
  permission. See `DECISIONS.md` (2026-07-25 entries) for the pause/resume and
  CDP-freeze design rationale.
- **Phase 2+ (not started, explicitly out of scope for Phase 1):** function
  hooking (intercept/rewrite calls without a paused breakpoint), network-
  initiator tracing (which JS call triggered a given request), WebSocket frame
  capture, and deobfuscation/AST tooling (variable renaming, control-flow
  simplification, static analysis of minified/obfuscated bundles). Each is a
  separate follow-up phase, not an extension of the Phase 1 module set.

### 1. Marketplace Ecosystem
- Template marketplace for buying/selling workflows
- Community-contributed modules
- Rating and review system
- Revenue sharing for creators

### 2. Cloud Execution & Scheduling
- Cloud-based workflow execution
- Cron scheduling (no local machine needed)
- Webhook triggers
- Execution history and logs in cloud

### 3. Team Collaboration
- Shared workspaces
- Role-based access control
- Real-time collaboration
- Version control for workflows

---

## Moat Analysis

| Feature | Moat Strength | Rationale |
|---------|---------------|-----------|
| Marketplace | Strong | Network effects, ecosystem lock-in |
| Cloud Sync | Strong | Cross-device, team collaboration |
| Webhook/Scheduling | Medium | Requires server infrastructure |
| Team Features | Medium | Multi-user permissions |

## Notes

- Core modules remain open source
- Cloud features provide sustainable moat
- Focus on ecosystem over feature parity

## Documentation Maintenance

- Keep generated source and runtime references deterministic and CI-enforced.
- Add real browser/E2E evidence when the required services and credentials are
  available; do not represent skipped integrations as verified.
- Resolve whether plugin HTTP management stays source-only or becomes an
  explicitly mounted authenticated product surface.
