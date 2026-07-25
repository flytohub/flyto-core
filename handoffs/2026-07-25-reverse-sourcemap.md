# Reverse-Engineering Toolkit — Source Map Resolution

## Scope

Adds `reverse.sourcemap` to the `reverse.*` category (see the Phase 1-3
handoffs: `2026-07-25-reverse-debugger-phase1.md`, `-phase2.md`,
`-reverse-code-phase3.md`). This is a strengthening pass, not a new numbered
phase — it fills a real gap called out when reviewing the toolkit's overall
state: a call-frame, breakpoint, or stack-trace location from a minified
bundle had no way to be mapped back to the original (pre-build) file/line/
column, even though CDP already hands us the pointer to do it
(`Debugger.scriptParsed`'s `sourceMapURL` field).

## What Changed

- `src/core/modules/atomic/reverse/sourcemap.py`: `reverse.sourcemap`
  (resolve/list_sources/get_original_source). Implements its own Source Map
  v3 base64-VLQ decoder and mapping-segment parser (`_decode_vlq_value`,
  `_parse_mappings`, `_SourceMapIndex` with a `bisect`-based
  nearest-preceding-segment lookup) — no pip dependency. `resolve` takes a
  `source_map` (JSON text or a `data:` URI, auto-detected) plus
  `generated_line`/`generated_column` and returns the original
  `source`/`originalLine`/`originalColumn`/`name`, or a graceful
  all-`null` result if no segment covers that location. `list_sources`
  returns the source paths (with `sourceRoot` prepended). `get_original_source`
  returns `sourcesContent` for a source (by path or index), or a clear
  "not embedded" result if that source's content wasn't inlined.
- **No changes to `ReverseSession`** — `sourceMapURL` was already captured
  by `_on_script_parsed` and already returned by `reverse.scripts`
  (action=list) before this change; the discovery step needed no work.
- **No changes anywhere else** — no new transport wiring (generic
  `is_reverse` prefix handling already covers it), no new npm/pip CI
  surface, no SSRF-sensitive code (fetching an external `.map` URL is left
  to the caller's own `http.get` step, which is already SSRF-guarded).
- Session-independent and permission-free, exactly like `reverse.code`:
  `required_permissions=[]`, no `reverse.attach` dependency.
- Catalog reconciled to 466 modules across 85 categories; same doc/citation
  sweep as prior phases.

## Key Design Decision (see DECISIONS.md)

Two things fell out of research before writing any code:

1. The only plausible pip package (`sourcemap` on PyPI) hasn't had a release
   since 2017 despite its GitHub being alive — hand-rolling the decoder
   (~150 LOC against a stable, decade-old spec) was judged the lower-risk
   choice, consistent with why `tree-sitter`/`jsbeautifier` were chosen for
   Phase 3 over less-current alternatives.
2. SSRF protection in this codebase is not ambient — `http.get` wires it in
   explicitly. Rather than duplicate that security-sensitive code inside a
   new module, `reverse.sourcemap` never fetches anything itself; resolving
   an external `.map` URL becomes a normal `http.get` step upstream in the
   workflow.

## Verification

- The VLQ decoder was verified against hand-computed test vectors *before*
  writing the module: round-tripping an independent test-only encoder
  through the decoder across positive/negative/multi-continuation-byte
  values, plus a full 2-line mappings string with manually-tracked deltas
  (confirming `generatedColumn` resets per line while
  `sourceIndex`/`sourceLine`/`sourceColumn`/`nameIndex` accumulate across
  the entire mappings string) — the same "verify empirically first"
  discipline used for Phase 1's CDP line-number semantics and Phase 2's
  hook/network/WebSocket mechanics.
- `tests/modules/test_reverse_sourcemap.py` (new, 18 tests): registration,
  `resolve` (exact segment match, same-line nearest-preceding match,
  cross-line segment, before-any-segment null case, inline `data:` URI,
  default `generated_column`), `list_sources` (with `sourceRoot`),
  `get_original_source` (by path, by index, not-embedded, unknown source),
  and validation errors. No `@pytest.mark.browser` — runs in the plain
  offline suite, like `reverse.code`.
- `python scripts/check_documentation.py` passes.
- `bash scripts/lint-project-memory.sh` passes.
- `tests/test_public_metadata.py` (citation contract) passes.
