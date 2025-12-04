# Flyto Core CLI Guide

Complete reference for the Flyto Core command-line interface.

---

## Quick Start

```bash
# Run a workflow
python -m cli.main workflow.yaml

# With parameters
python -m cli.main workflow.yaml --param.keyword=python

# With environment variables
export API_KEY=your_key
python -m cli.main workflow.yaml
```

---

## Installation

```bash
# Clone repository
git clone https://github.com/flytohub/flyto-core.git
cd flyto-core

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

---

## Basic Usage

### Running Workflows

**Syntax:**
```bash
python -m cli.main <workflow_file> [options]
```

**Examples:**
```bash
# Run workflow
python -m cli.main workflows/google_search.yaml

# Run with absolute path
python -m cli.main /path/to/my_workflow.yaml

# Run from different directory
cd /other/directory
python -m cli.main ~/flyto-core/workflows/api_pipeline.yaml
```

---

## Passing Parameters

### Method 1: Command Line Arguments

Use `--param.name=value` syntax:

```bash
python -m cli.main workflow.yaml \
  --param.keyword=python \
  --param.max_results=20 \
  --param.headless=true
```

**Parameter types:**
- **String:** `--param.url=https://example.com`
- **Number:** `--param.count=10`
- **Boolean:** `--param.headless=true` or `--param.headless=false`

### Method 2: Environment Variables

Reference in workflow with `${env.VAR_NAME}`:

```bash
# Set environment variables
export API_KEY=your_api_key
export SLACK_WEBHOOK=https://hooks.slack.com/...

# Run workflow
python -m cli.main workflow.yaml
```

**In workflow.yaml:**
```yaml
steps:
  - id: api_call
    module: api.http.get
    params:
      headers:
        Authorization: "Bearer ${env.API_KEY}"
```

### Method 3: .env File

Create `.env` file in project root:

```bash
# .env
API_KEY=your_api_key
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
GITHUB_TOKEN=ghp_xxxxx
OPENAI_API_KEY=sk-xxxxx
```

Flyto Core automatically loads `.env` file if it exists.

---

## CLI Options

### Verbose Logging

```bash
# Show detailed execution logs
python -m cli.main workflow.yaml --verbose

# Or set log level
python -m cli.main workflow.yaml --log-level=DEBUG
```

**Log levels:** DEBUG, INFO, WARNING, ERROR

### Dry Run (Validation Only)

```bash
# Validate workflow without executing
python -m cli.main workflow.yaml --dry-run
```

**Checks:**
- YAML syntax
- Required fields
- Module existence
- Parameter validation

### Output Format

```bash
# JSON output (default)
python -m cli.main workflow.yaml

# Pretty JSON
python -m cli.main workflow.yaml --pretty

# Minimal output
python -m cli.main workflow.yaml --quiet
```

---

## Environment Setup

### Required Environment Variables

Different modules require different environment variables:

**Notifications:**
```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
export TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
export TELEGRAM_CHAT_ID=@your_channel
```

**Email:**
```bash
export SMTP_SERVER=smtp.gmail.com
export SMTP_USERNAME=your_email@gmail.com
export SMTP_PASSWORD=your_app_password
```

**APIs:**
```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
export OPENAI_API_KEY=sk-xxxxxxxxxxxx
export API_TOKEN=your_api_token
```

### Using .env File (Recommended)

Create `.env` file:

```bash
# Notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Email
SMTP_SERVER=smtp.gmail.com
SMTP_USERNAME=bot@example.com
SMTP_PASSWORD=your_password

# APIs
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxx
```

**Security:** Add `.env` to `.gitignore`!

---

## Running Workflows

### Example 1: Google Search

```bash
python -m cli.main workflows/google_search.yaml \
  --param.keyword="workflow automation" \
  --param.max_results=10
```

### Example 2: GitHub to Slack

```bash
# Set environment variables first
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...

# Run workflow
python -m cli.main workflows/github_to_slack.yaml \
  --param.repo_owner=facebook \
  --param.repo_name=react
```

### Example 3: Daily Report Email

```bash
# Environment variables
export SMTP_SERVER=smtp.gmail.com
export SMTP_USERNAME=reports@company.com
export SMTP_PASSWORD=your_app_password
export API_TOKEN=your_api_token

# Run workflow
python -m cli.main workflows/daily_report_email.yaml \
  --param.recipient_email=manager@company.com
```

### Example 4: Multi-Channel Alert

```bash
# Set all notification channels
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...
export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
export TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
export TELEGRAM_CHAT_ID=@alerts
export SMTP_SERVER=smtp.gmail.com
export SMTP_USERNAME=alerts@company.com
export SMTP_PASSWORD=password
export ALERT_EMAIL=oncall@company.com

# Send alert
python -m cli.main workflows/multi_channel_alert.yaml \
  --param.alert_title="Production Down" \
  --param.alert_message="Server crashed" \
  --param.severity=critical
```

---

## Scheduling Workflows

### Using Cron (Linux/Mac)

Edit crontab:
```bash
crontab -e
```

Add scheduled workflows:
```bash
# Run every day at 9 AM
0 9 * * * cd /path/to/flyto-core && python -m cli.main workflows/daily_report_email.yaml

# Run every hour
0 * * * * cd /path/to/flyto-core && python -m cli.main workflows/monitor.yaml

# Run every 15 minutes
*/15 * * * * cd /path/to/flyto-core && python -m cli.main workflows/check_status.yaml
```

### Using systemd Timer (Linux)

Create service file: `/etc/systemd/system/flyto-core-daily.service`

```ini
[Unit]
Description=Flyto Core Daily Report

[Service]
Type=oneshot
WorkingDirectory=/path/to/flyto-core
EnvironmentFile=/path/to/flyto-core/.env
ExecStart=/usr/bin/python3 -m cli.main workflows/daily_report_email.yaml
User=your_user
```

Create timer: `/etc/systemd/system/flyto-core-daily.timer`

```ini
[Unit]
Description=Run Flyto Core Daily Report

[Timer]
OnCalendar=daily
OnCalendar=09:00

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl enable flyto-core-daily.timer
sudo systemctl start flyto-core-daily.timer
```

### Using Task Scheduler (Windows)

Create batch file `run_workflow.bat`:
```batch
@echo off
cd C:\path\to\flyto-core
python -m cli.main workflows\daily_report_email.yaml
```

Schedule in Task Scheduler:
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (daily at 9 AM)
4. Action: Start a program
5. Program: `C:\path\to\flyto-core\run_workflow.bat`

---

## Docker Usage

### Build Image

```dockerfile
# Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install Playwright dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copy files
COPY requirements.txt .
RUN pip install -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

CMD ["python", "-m", "cli.main", "workflows/example.yaml"]
```

Build and run:
```bash
# Build
docker build -t flyto-core .

# Run with environment variables
docker run --rm \
  -e SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL \
  -e API_TOKEN=$API_TOKEN \
  flyto-core

# Run with custom workflow
docker run --rm \
  -v $(pwd)/workflows:/app/workflows \
  -e SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL \
  flyto-core python -m cli.main workflows/my_workflow.yaml

# Run with .env file
docker run --rm \
  --env-file .env \
  flyto-core
```

---

## Debugging

### Enable Debug Logging

```bash
python -m cli.main workflow.yaml --log-level=DEBUG
```

**Shows:**
- Step execution details
- Variable resolution
- Module parameters
- Error stack traces

### Validate Workflow

```bash
# Check syntax without running
python -m cli.main workflow.yaml --dry-run
```

### Common Issues

**Issue: Module not found**
```bash
# Error: Module 'core.browser.launch' not found

# Solution: Check module ID spelling
# Correct: core.browser.launch
# Wrong: core.browser.start
```

**Issue: Missing environment variable**
```bash
# Error: SLACK_WEBHOOK_URL not found

# Solution: Set environment variable
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...

# Or use .env file
echo "SLACK_WEBHOOK_URL=https://..." >> .env
```

**Issue: Playwright browser not installed**
```bash
# Error: Executable doesn't exist

# Solution: Install browsers
playwright install chromium
```

---

## CI/CD Integration

### GitHub Actions

`.github/workflows/workflow.yml`:

```yaml
name: Run Flyto Core Workflow

on:
  schedule:
    - cron: '0 9 * * *'  # Daily at 9 AM
  workflow_dispatch:

jobs:
  run-workflow:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium
          playwright install-deps chromium

      - name: Run workflow
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python -m cli.main workflows/daily_report_email.yaml
```

### GitLab CI

`.gitlab-ci.yml`:

```yaml
run-workflow:
  image: python:3.10

  before_script:
    - pip install -r requirements.txt
    - playwright install chromium
    - playwright install-deps chromium

  script:
    - python -m cli.main workflows/daily_report_email.yaml

  only:
    - schedules
```

---

## Best Practices

1. **Use .env for secrets** - Never commit API keys
2. **Use --dry-run first** - Validate before running
3. **Enable logging in production** - `--log-level=INFO`
4. **Set timeouts** - Prevent hanging workflows
5. **Use absolute paths** - When running from cron
6. **Version your workflows** - Use Git tags
7. **Test with small data** - Use `limit` parameters during development
8. **Close browsers** - Always use `core.browser.close` with `on_error: continue`

---

## Getting Help

- **Documentation:** [docs/DSL.md](DSL.md), [docs/MODULES.md](MODULES.md)
- **Examples:** [workflows/](../workflows/)
- **Issues:** [GitHub Issues](https://github.com/flytohub/flyto-core/issues)

---

## Next Steps

- Read [DSL Specification](DSL.md) to learn workflow syntax
- Browse [Module Registry](MODULES.md) for available modules
- Check [Example Workflows](../workflows/) for real-world use cases
- Learn [Module Development](WRITING_MODULES.md) to create custom modules
