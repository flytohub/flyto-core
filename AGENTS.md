# flyto-core Agent Rules

- Do not store credentials, PATs, cookies, bearer tokens, or account passwords in recipe YAML, tests, logs, or generated artifacts.
- Recipe credentials must be runtime parameters only. Do not put real secrets in defaults, examples, manifests, screenshots, or committed smoke reports.
- Before changing module registration, browser automation, recipe execution, or recipe bundle behavior, use flyto-indexer impact/search to understand callers.
- After changing recipes or recipe bundles, run the focused recipe bundle tests and a flyto-core recipe smoke.
- Before finishing any code change, run the relevant verify/test/smoke checks and record any skipped gate.
- Keep `.flyto-index/`, run outputs, screenshots, and other generated artifacts out of commits.
