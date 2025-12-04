# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet

### Changed
- Nothing yet

### Deprecated
- Nothing yet

### Removed
- Nothing yet

### Fixed
- Nothing yet

### Security
- Nothing yet

---

## [1.5.0] - 2025-12-04

### Added
- **Level 4: Advanced Patterns** - Enterprise-grade execution patterns (`src/core/modules/patterns/`)
  - `BasePattern` base class for all patterns
  - `PatternRegistry` for managing patterns
  - `PatternExecutor` for unified pattern execution
  - `@register_pattern` decorator for easy registration
  - `PatternResult` and `PatternState` for execution tracking

- **Retry Patterns**
  - `pattern.retry.exponential_backoff` - Exponential backoff with jitter
  - `pattern.retry.linear_backoff` - Linear delay increase

- **Parallel Patterns**
  - `pattern.parallel.map` - Parallel execution with concurrency control
  - `pattern.parallel.race` - Execute multiple functions, return first success

- **Resilience Patterns**
  - `pattern.circuit_breaker` - Circuit breaker with CLOSED/OPEN/HALF_OPEN states

- **Rate Limiting Patterns**
  - `pattern.rate_limiter.token_bucket` - Token bucket algorithm
  - `pattern.rate_limiter.sliding_window` - Sliding window algorithm

- **Batch Patterns**
  - `pattern.batch.processor` - Batch processing with chunking
  - `pattern.batch.aggregator` - Aggregate items and flush on threshold

### Changed
- Four-Level Module Architecture now complete:
  - Level 1: Workflow Templates (6 templates)
  - Level 2: Atomic Modules (127+ modules)
  - Level 3: Composite Modules (9 modules)
  - Level 4: Advanced Patterns (9 patterns)

---

## [1.4.0] - 2025-12-04

### Added
- **Four-Level Module Architecture Implementation**
  - Level 3: Composite Modules (9 modules across 4 categories)
  - Level 1: Workflow Templates (6 marketplace-ready templates)

- **Composite Module System** (`src/core/modules/composite/`)
  - `CompositeModule` base class for high-level workflows
  - `CompositeRegistry` for managing composite modules
  - `CompositeExecutor` for executing composite workflows
  - `@register_composite` decorator for easy module registration

- **Browser Composites**
  - `composite.browser.search_and_notify` - Web search with notification
  - `composite.browser.scrape_to_json` - Web scraping to JSON
  - `composite.browser.screenshot_and_save` - Screenshot capture

- **Developer Composites**
  - `composite.developer.github_daily_digest` - GitHub repo monitoring
  - `composite.developer.api_to_notification` - API to notification pipeline

- **Notification Composites**
  - `composite.notification.multi_channel_alert` - Multi-channel alerts
  - `composite.notification.scheduled_report` - Scheduled report delivery

- **Data Composites**
  - `composite.data.csv_to_json` - CSV to JSON conversion
  - `composite.data.json_transform_notify` - JSON transform with notification

- **Level 1 Workflow Templates** (`workflows/templates/`)
  - `google_search_to_slack.yaml` - Google search to Slack
  - `github_repo_monitor.yaml` - GitHub repository monitoring
  - `webpage_screenshot.yaml` - Webpage screenshot capture
  - `multi_channel_alert.yaml` - Multi-channel alert system
  - `web_scraper.yaml` - Web scraping workflow
  - `api_monitor.yaml` - API health monitoring

### Changed
- Updated `composite/__init__.py` to export all composite modules
- Composite modules now support variable resolution with `${params.*}`, `${steps.*}`, `${env.*}`

---

## [1.3.0] - 2025-12-04

### Added
- New constants for AI models: `DEFAULT_ANTHROPIC_MODEL`, `DEFAULT_GEMINI_MODEL`
- Environment variable constants: `GOOGLE_AI_API_KEY`, `SLACK_WEBHOOK_URL`, `DISCORD_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`
- Logging to all third-party integration modules

### Changed
- **third_party/ai/agents.py**: Use `OLLAMA_DEFAULT_URL`, `APIEndpoints.DEFAULT_OPENAI_MODEL`, `EnvVars.OPENAI_API_KEY`, `DEFAULT_LLM_MAX_TOKENS`
- **third_party/ai/local_ollama.py**: Use `OLLAMA_DEFAULT_URL` instead of hardcoded URL
- **third_party/ai/openai_integration.py**: Use `APIEndpoints.DEFAULT_OPENAI_MODEL`, `EnvVars.OPENAI_API_KEY`
- **third_party/ai/services.py**: Use centralized API endpoints for Anthropic and Google Gemini
- **third_party/communication/twilio.py**: Use `APIEndpoints.twilio_messages()`, `EnvVars.TWILIO_*`
- **third_party/communication/messaging.py**: Use `EnvVars` for Slack, Discord, Telegram
- **third_party/developer/github.py**: Use `APIEndpoints.github_*()`, `EnvVars.GITHUB_TOKEN`
- **third_party/payment/stripe.py**: Use `APIEndpoints.STRIPE_*`, `EnvVars.STRIPE_API_KEY`
- **third_party/productivity/airtable.py**: Use `APIEndpoints.airtable_table()`, `EnvVars.AIRTABLE_API_KEY`
- **third_party/productivity/tools.py**: Use `APIEndpoints.notion_*()`, `EnvVars.NOTION_API_KEY`
- Moved all inline `import os` statements to file-level imports
- All error messages now use f-strings with constant names for clarity

### Fixed
- Removed duplicate `import json` statements
- Consistent logging pattern across all modules

---

## [1.2.0] - 2025-12-04

### Added
- Browser constants: `DEFAULT_BROWSER_TIMEOUT_MS`, `DEFAULT_VIEWPORT_WIDTH`, `DEFAULT_VIEWPORT_HEIGHT`, `DEFAULT_USER_AGENT`
- LLM constants: `DEFAULT_LLM_MAX_TOKENS`, `OLLAMA_DEFAULT_URL`, `OLLAMA_EMBEDDINGS_ENDPOINT`
- Validation constants: `MIN_DESCRIPTION_LENGTH`, `MAX_DESCRIPTION_LENGTH`, `MAX_TIMEOUT_LIMIT`, `MAX_RETRIES_LIMIT`
- Extended `APIEndpoints` class with Anthropic, Notion, Twilio, OpenAI endpoints
- Extended `EnvVars` class with database and cloud storage variables
- New utility functions: `truncate_string()`, `ensure_list()`, `ensure_dict()`, `safe_execute()`, `log_execution()`

### Changed
- **browser/driver.py**: Use constants instead of hardcoded timeouts and viewport sizes
- **vector/auto_archive.py**: Replace `print()` with `logger.debug()`/`logger.error()`
- **vector/embeddings.py**: Use constants and improved exception handling
- **string/*.py**: Convert absolute imports to relative imports
- **cli/main.py**: Extract constants, use logging, remove `os.system()`

### Fixed
- **utility/not.py**: Implement complete logical negation (was TODO placeholder)
- Security issue: Replaced `os.system('clear')` with ANSI escape sequence

---

## [1.1.0] - 2025-12-04

### Added
- `src/core/constants.py` - Centralized constants management
  - `DEFAULT_MAX_RETRIES`, `DEFAULT_RETRY_DELAY_MS`, `DEFAULT_TIMEOUT_SECONDS`
  - `EXPONENTIAL_BACKOFF_BASE`, `MAX_LOG_RESULT_LENGTH`
  - `WorkflowStatus` enum class
  - `APIEndpoints` class for API URL management
  - `EnvVars` class for environment variable names
  - `ErrorMessages` class for error message templates
- `src/core/utils.py` - Shared utility functions
  - `get_api_key()` - Retrieve API keys from environment
  - `validate_api_key()` - Validate API key presence
  - `validate_required_param()` - Validate required parameters
  - `get_param()` - Get parameter with default value
  - `auto_convert_type()` - Automatic type conversion

### Changed
- **base.py**: Added `get_param()` and `require_param()` methods
- **workflow_engine.py**: Use constants and relative imports
- **registry.py**: Use logger instead of print statements
- All hardcoded magic numbers moved to constants
- Unified relative import paths across modules

---

## [1.0.0] - 2025-12-04

### Added
- Initial release of Flyto Core
- YAML workflow automation engine
- 127+ atomic modules across categories:
  - `string.*` - Text manipulation (8 modules)
  - `array.*` - Array operations (10 modules)
  - `object.*` - Object manipulation (5 modules)
  - `file.*` - File system operations (6 modules)
  - `datetime.*` - Date/time operations (4 modules)
  - `math.*` - Mathematical operations (7 modules)
  - `data.*` - Data parsing (5 modules)
  - `browser.*` - Browser automation (9 modules)
  - `utility.*` - Utilities (7 modules)
  - `ai.*` - AI integrations (4 modules)
- CLI interface with interactive mode
- Variable resolution with `${step_id.field}` syntax
- Error handling with retry support
- Internationalization (en, zh, ja)
- Playwright integration for browser automation
- Third-party integrations:
  - AI: OpenAI, Anthropic, Ollama
  - Communication: Twilio, Slack, Discord, Telegram
  - Developer: GitHub, HTTP APIs
  - Payment: Stripe
  - Productivity: Notion, Airtable, Google Sheets

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| 1.5.0 | 2025-12-04 | Level 4 Advanced Patterns (Enterprise) |
| 1.4.0 | 2025-12-04 | Level 3 Composite Modules + Level 1 Templates |
| 1.3.0 | 2025-12-04 | Third-party module refactoring |
| 1.2.0 | 2025-12-04 | Browser/LLM constants, utility functions |
| 1.1.0 | 2025-12-04 | Constants and utils infrastructure |
| 1.0.0 | 2025-12-04 | Initial release |

---

[Unreleased]: https://github.com/flytohub/flyto-core/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/flytohub/flyto-core/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/flytohub/flyto-core/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/flytohub/flyto-core/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/flytohub/flyto-core/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/flytohub/flyto-core/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/flytohub/flyto-core/releases/tag/v1.0.0
