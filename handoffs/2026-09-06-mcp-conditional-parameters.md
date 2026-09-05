# MCP conditional parameter validation

Owner: codex
Branch: codex/mcp-conditional-required

## Trigger and implementation

A real AI Space actor called browser.type with ordinary text. MCP preflight
rejected the call because sensitive_text was absent, then repeated failures
exhausted the agent's module retry budget. The installed module schema correctly
marks text and sensitive_text as conditionally required; MCP's independent
required-field loop ignored those conditions.

The MCP handler now combines schema defaults with explicit caller values,
reuses the existing workflow field-visibility predicate, and checks only active
required fields. Repair hints use the same active requirements. Module-specific
validation still runs, with effective values in a separate dictionary. Neither
the module schema nor caller parameters are changed.

## Verification

- Fifteen regressions cover real browser text, email, password-reference and
  invalid-selector contracts; conditional show/hide/displayOptions, explicit
  overrides, falsy defaults and caller-input preservation. Fourteen failed
  before the fix; all pass after it.
- The focused MCP/validation cohort passed 203 tests, including real HTTP and
  STDIO protocol tests and real module execution.
- Final repository and release-gate outcomes are recorded by the coordinating
  task; this handoff does not claim a live browser task completed.

## Local activation

The existing Cloud runtime's installed Core 2.31.2 matches all 905 other Core
Python source files in this checkout; mcp_handler.py is the only changed runtime
file. The host may prepend this checkout's src directory to its own process
import path before importing flyto-ai. This uses the committed source without
modifying site-packages, the main checkout, credentials or global environment.
Actual product UI acceptance remains separate from the parameter tests.
