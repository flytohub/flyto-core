# Handoff Registry

| Date | Topic | File | Status |
| --- | --- | --- | --- |
| 2026-08-29 | Browser popup ownership closure | `2026-08-29-browser-popup-ownership.md` | Pushed to `origin/main` and loaded by restarted flyto-cloud: click-opened tabs become the current controlled page before preview/hints/next nodes; immediate `browser.tab(index=1)` regression and real Chromium smoke pass. Cloud EVTEK rerun awaits credential-transmission confirmation. Owner: codex |
| 2026-08-28 | Semantic browser.click closure | `2026-08-28-browser-click-semantic-closure.md` | Implemented on `main`: Element Picker and click share visible accessible names; icon-only links execute without CSS/XPath; configured timeout and navigation detection fixed. `template.invoke` validation now accepts dynamic child inputs without false unknown-param warnings. Real EVTEK login-to-portal proof passed. No attendance action executed. Owner: codex |
| 2026-08-28 | Nested template authenticated-browser closure | `2026-08-28-template-invoke-browser-closure.md` | Implemented on `main`: child templates borrow browser state without owning cleanup, emitted error events enter normal failure handling, and visible waits accept any visible match. Real Cloud proof completed 3/3 parent steps and returned terminal API/UI state. No attendance action executed. Owner: codex |
| 2026-08-25 | verify.spec policy-gate bypass (GHSA-wmwj-g59x-c8px) | `2026-08-25-verify-spec-policy-gate.md` | Implemented on `claude/verify-spec-policy-gate`: child modules dispatch through `BaseModule.run()`, REST `/v1/execute` gained the nested-module pre-flight, registry-wide regression test added. Reporter PoC reproduces on PyPI 2.31.0 and is refused by the 2.31.1 wheel built here; offline suite 3,175 passed, 11 skipped, 63.67% coverage; strict Indexer 20/20. Not released, advisory not yet published. Owner: claude |
| 2026-08-24 | crypto.totp and browser launch diagnosability | `2026-08-24-crypto-totp-and-launch-diagnosis.md` | Implemented on `codex/totp-browser-flow` at `dad6ef4`: RFC 6238 module, launch failure causes surfaced, parameterised login/OTP/act/prove workflow. Full non-browser/non-E2E 3,166 passed, 11 skipped, 63.38% coverage; strict Indexer 19/19 clean. No run against a real 2FA site. Owner: claude |
| 2026-08-24 | JSON-to-CSV output and input-error contract | `2026-08-24-csv-output-contract.md` | Implemented locally: sandbox-safe default output, typed parameter failures, and no deterministic retries. Focused Core 109/109; full non-browser/non-E2E 3,070 passed, 11 skipped, 63.37% coverage. Owner: codex |
| 2026-08-24 | Runtime and module catalog convergence | `2026-08-24-runtime-and-catalog-convergence.md` | Implemented locally: browser fallback, truthful legacy failure, total label-key metadata, and optional response assertion metadata. Full suite 3,041 passed, 11 skipped, 63.36% coverage; targeted 171/171 and real installed-Chrome launch green. Owner: codex |
| 2026-08-12 | Four-repository capability, extension and runtime closure | `2026-08-12-four-repo-closure.md` | Complete — commit `0a353ff`, strict Indexer 19/19 |
| 2026-08-11 | Capability manifest `flyto.core.capability-manifest.v1`, `/v1/capabilities`, MCP `get_capability_manifest` | `2026-08-11-capability-manifest.md` | Superseded by 2026-08-12 closure; retained as rework history |
| 2026-08-11 | Registry plugin-load transaction: stale removal, foreign-row rollback, empty plugins | `2026-08-11-registry-plugin-load-transaction.md` | Completed |
| 2026-08-08 | Plugin contribution point, per-plugin policy scope, manifest draft | `2026-08-08-plugin-contribution-and-policy-scope.md` | Active |
| 2026-08-08 | Registry-wide filesystem and outbound boundary coverage enforcement | `2026-08-08-boundary-coverage-enforcement.md` | Active |
| 2026-08-02 | Private advisory network and filesystem hardening | `2026-08-02-private-advisory-boundary-hardening.md` | Active |
| 2026-08-02 | GitHub code-scanning security closure | `2026-08-02-code-scanning-security-closure.md` | Active |
| 2026-07-25 | Reverse-engineering toolkit, Phase 4 — reverse.deobfuscate | `2026-07-25-reverse-deobfuscate-phase4.md` | Active |
| 2026-07-25 | Reverse-engineering toolkit — request breakpoints + session-snapshot reuse | `2026-07-25-reverse-request-breakpoint-session-reuse.md` | Active |
| 2026-07-25 | Reverse-engineering toolkit — hook robustness + session reaper | `2026-07-25-reverse-hardening.md` | Active |
| 2026-07-25 | Reverse-engineering toolkit — source map resolution | `2026-07-25-reverse-sourcemap.md` | Active |
| 2026-07-25 | Reverse-engineering toolkit, Phase 3 | `2026-07-25-reverse-code-phase3.md` | Active |
| 2026-07-25 | Reverse-engineering debugger, Phase 2 | `2026-07-25-reverse-debugger-phase2.md` | Active |
| 2026-07-25 | Reverse-engineering debugger, Phase 1 | `2026-07-25-reverse-debugger-phase1.md` | Active |
| 2026-07-22 | Source-backed documentation and release gates | `2026-07-22-source-backed-documentation.md` | Active |
| 2026-06-23 | Product Verification 90-point evidence gate | `2026-06-23-product-verification-90-gate.md` | Active |
| 2026-06-23 | Automation test model evidence | `2026-06-23-automation-test-model.md` | Active |
| 2026-06-23 | Warroom hydration-aware replay assertions | `2026-06-23-warroom-hydration-aware-replay.md` | Active |
| 2026-06-23 | Verification Docker packaging | `2026-06-23-verification-docker-packaging.md` | Active |
| 2026-06-23 | Verification service image | `2026-06-23-verification-service-image.md` | Active |
| 2026-06-23 | Verification runner service | `2026-06-23-verification-runner-service.md` | Active |
| 2026-06-23 | Public site verification | `2026-06-23-public-site-verification.md` | Active |
| 2026-06-23 | Warroom deterministic verification | `2026-06-23-warroom-deterministic-verification.md` | Active |
| 2026-06-21 | Project memory bootstrap | `2026-06-21-project-memory-bootstrap.md` | Active |
