# Workflow Templates (Level 1)

Ready-to-use workflow templates for beginners. These templates require minimal configuration and can be run immediately with just a few parameters.

## Available Templates

| Template | Description | Required Params |
|----------|-------------|-----------------|
| `google_search_to_slack.yaml` | Search Google and send results to Slack | `query` |
| `github_repo_monitor.yaml` | Monitor GitHub repo and send digest | `owner`, `repo` |
| `webpage_screenshot.yaml` | Screenshot any webpage | `url`, `output_path` |
| `multi_channel_alert.yaml` | Send alerts to Slack/Discord/Telegram | `title`, `message` |
| `web_scraper.yaml` | Scrape data from webpage to JSON | `url`, `title_selector` |
| `api_monitor.yaml` | Monitor API health and alert on failure | `api_url` |

## Quick Start

### 1. Set Environment Variables

Create a `.env` file or export variables:

```bash
# Notifications (at least one required for notification workflows)
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
export TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
export TELEGRAM_CHAT_ID=@your_channel

# GitHub (optional, for public repos)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

### 2. Run a Template

```bash
# Google search to Slack
python -m cli.main workflows/templates/google_search_to_slack.yaml \
  --param.query="python tutorial"

# GitHub repo monitor
python -m cli.main workflows/templates/github_repo_monitor.yaml \
  --param.owner=facebook \
  --param.repo=react

# Webpage screenshot
python -m cli.main workflows/templates/webpage_screenshot.yaml \
  --param.url="https://example.com" \
  --param.output_path="./screenshot.png"

# Multi-channel alert
python -m cli.main workflows/templates/multi_channel_alert.yaml \
  --param.title="Production Alert" \
  --param.message="Server is down"

# Web scraper
python -m cli.main workflows/templates/web_scraper.yaml \
  --param.url="https://news.ycombinator.com" \
  --param.title_selector=".titleline > a"

# API monitor
python -m cli.main workflows/templates/api_monitor.yaml \
  --param.api_url="https://api.github.com/status"
```

## Template Structure

Each template follows this structure:

```yaml
id: template_id
name: Human-readable Name
version: 1.0.0
description: What this template does
author: Flyto Core Team
license: MIT
level: 1  # Indicates beginner-friendly

tags:
  - relevant
  - tags

params:
  - name: param_name
    type: string|number|boolean|object
    required: true|false
    default: optional_default
    label: Human Label
    description: What this param does

steps:
  - id: step_id
    module: category.subcategory.action
    params:
      key: value
    on_error: continue|fail

output:
  key: ${step_id.result}
```

## Customization

These templates are designed to be customized. You can:

1. **Copy and modify** - Copy a template and adjust parameters
2. **Chain templates** - Use output of one as input to another
3. **Add steps** - Extend templates with additional modules

## Module Levels

Flyto Core uses a four-level architecture:

| Level | Type | User | Description |
|-------|------|------|-------------|
| **1** | Workflow Templates | Beginners | Ready-to-use, minimal config |
| **2** | Atomic Modules | AI/Developers | Fine-grained, 127+ modules |
| **3** | Composite Modules | Normal Users | Like n8n nodes, 3-10 steps |
| **4** | Advanced Patterns | Enterprise | retry_backoff, parallel_map |

## More Information

- [DSL Specification](../../docs/DSL.md) - Learn workflow syntax
- [Module Registry](../../docs/MODULES.md) - All available modules
- [CLI Guide](../../docs/CLI.md) - Command-line options
- [Module Specification](../../docs/MODULE_SPECIFICATION.md) - Creating modules

---

**Need help?** Open an issue on [GitHub](https://github.com/flytohub/flyto-core/issues).
