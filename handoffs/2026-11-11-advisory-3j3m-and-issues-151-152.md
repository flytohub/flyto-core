# GHSA-3j3m-rp8w-pxpv, #152 agent.tool_use stop reasons, #151 Google CSE endpoint

Owner: claude
Branch: fix/core-advisory-and-issues-20261111 (from origin/main a417ba8)
Date: 2026-11-11

## What changed

- **GHSA-3j3m-rp8w-pxpv (image.download SSRF via redirect).** Root cause was
  shared, not module-local: aiohttp's `TCPConnector._resolve_host` returns IP
  literals without calling the resolver, so `_SSRFGuardedResolver` never saw
  `[::ffff:127.0.0.1]`, and any guarded session that let aiohttp follow
  redirects could be sent to an internal literal.
  - `core.utils.guarded_client_session` now installs a client middleware
    (`_ssrf_literal_ip_middleware` -> `_check_literal_connect_target`) that
    applies the resolver's policy (restricted hosts, metadata, private unless
    `FLYTO_ALLOW_PRIVATE_NETWORK` / `FLYTO_ALLOWED_HOSTS`) to IP-literal hosts.
    aiohttp runs client middlewares on every redirect hop. Hostnames are
    unchanged (still the resolver). Skipped when the guard is disabled.
  - `image.download` now uses `guarded_aiohttp_request`, like `http.get`, so
    every `Location` gets the full URL policy (ports included).
- **#152 agent.tool_use.** A declarative table `_COMPLETE_STOP_REASONS`
  (anthropic: end_turn/tool_use/stop_sequence; openai:
  stop/tool_calls/function_call). Any other stop reason, unknown ones included,
  returns the text so far with an INDETERMINATE envelope (effect
  `agent_reply_cut_off`, `stop_reason`, `skipped_tool_calls`) and runs none of
  that reply's tool calls. New `max_tokens` param (default 4096) sent as
  Anthropic `max_tokens` / OpenAI `max_completion_tokens`. OpenAI tool
  arguments that are not a JSON object are no longer run with `{}`; the error
  goes back to the model as the tool result.
- **#151 core.api.google_search.** Endpoint is read from env
  `GOOGLE_SEARCH_URL` (any `customsearch/v1`-compatible endpoint), defaulting
  to Google's. Env only, never step params, so the env key goes only where the
  operator points it. Setup guide and 403 message state the 2027-01-01
  discontinuation and point at `core.api.serpapi_search` /
  `core.api.tavily_search`. No vendor named in code.

## Not done

- i18n: `modules.agent.tool_use.params.max_tokens{,.description}` keys are not
  added to flyto-i18n (owner handles translations).
- No PyPI release. The fixes ship in the next release (pyproject is at the
  unreleased 2.41.0); the advisory's patched version is set when that ships.

## Verified

See the PR description for the exact commands and results.
