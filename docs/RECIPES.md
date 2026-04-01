# Recipes

Pre-built workflow templates. No code, no API key — just `flyto recipe <name>`.

```bash
pip install flyto-core[browser]
playwright install chromium
flyto recipes  # list all
```

---

## Audit & Testing

### competitor-intel

Competitor analysis — extract pricing data, desktop + mobile screenshots, Web Vitals, SEO meta, structured JSON report. One command, full competitive intelligence.

```bash
flyto recipe competitor-intel --url https://github.com/pricing
flyto recipe competitor-intel --url https://competitor.com/pricing --output comp-report.json
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | Competitor URL to analyze (e.g. a pricing page) |
| `--output` | no | `intel-report.json` | Output report file |

Output includes: pricing data (plan text + dollar amounts), desktop screenshot (`intel-desktop.png`), mobile screenshot (`intel-mobile.png`), Web Vitals performance metrics, SEO meta tags, technology hints. 12 steps, fully traced.

---

### full-audit

Comprehensive site audit — Web Vitals + SEO + accessibility + console errors + mobile/desktop screenshots + PDF. One command, complete report.

```bash
flyto recipe full-audit --url https://example.com
flyto recipe full-audit --url https://github.com --output github-audit.json
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to audit |
| `--output` | no | `audit-report.json` | Output report file |

Output includes: performance timing (TTFB, DOM loaded, fully loaded), SEO analysis (title, meta tags, OG tags, headings, canonical), accessibility check (missing alt tags, unlabeled inputs, empty buttons), page stats (links, scripts, stylesheets, iframes, forms). Also generates `audit-mobile.png`, `audit-desktop.png`, and `audit-page.pdf`.

---

### site-audit

SEO + performance audit — meta tags, headings, missing alt tags, Web Vitals, and a full-page screenshot, all in one command.

```bash
flyto recipe site-audit --url https://github.com
flyto recipe site-audit --url https://example.com --output report.json
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to audit |
| `--output` | no | `audit.json` | Output report file |

Output includes: page title, meta tags, h1/h2/h3 headings, image count, missing alt tags, link count, canonical URL. Also saves `audit-screenshot.png`.

---

### web-perf

Get Core Web Vitals from the terminal — LCP, FCP, CLS, TTFB, and more.

```bash
flyto recipe web-perf --url https://example.com
flyto recipe web-perf --url https://example.com --timeout 10000
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to measure |
| `--timeout` | no | `5000` | Time to wait for metrics (ms) |

---

### login-test

E2E login test — navigate to login page, fill credentials, submit, verify success element appears, screenshot the result.

```bash
flyto recipe login-test --url https://myapp.com/login --username user@example.com --password s3cret --success_selector .dashboard
flyto recipe login-test --url https://the-internet.herokuapp.com/login --username tomsmith --password SuperSecretPassword! --success_selector ".flash.success"
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | Login page URL |
| `--username` | yes | — | Username or email |
| `--password` | yes | — | Password |
| `--success_selector` | yes | — | CSS selector that appears after successful login |
| `--output` | no | `login-result.png` | Screenshot output path |

---

### form-fill

Auto-fill a web form with data and optionally submit it. Pass field:value pairs as JSON.

```bash
flyto recipe form-fill --url https://myapp.com/contact --data '{"email":"test@example.com","name":"John","message":"Hello"}'
flyto recipe form-fill --url https://httpbin.org/forms/post --data '{"custname":"Jane","custtel":"555-0123"}' --submit false
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | Page URL containing the form |
| `--data` | yes | — | JSON string of field:value pairs |
| `--submit` | no | `true` | Submit the form after filling |
| `--output` | no | `form-result.png` | Screenshot output path after submission |

---

## Browser

### screenshot

Take a full-page screenshot of any webpage.

```bash
flyto recipe screenshot --url https://example.com
flyto recipe screenshot --url https://example.com --output home.png --width 1920 --height 1080
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to screenshot |
| `--output` | no | `screenshot.png` | Output file path |
| `--width` | no | `1280` | Viewport width |
| `--height` | no | `720` | Viewport height |

---

### responsive-report

Screenshot a page at 3 breakpoints — mobile (390px), tablet (768px), desktop (1440px). Perfect for responsive design review.

```bash
flyto recipe responsive-report --url https://example.com
flyto recipe responsive-report --url https://github.com --prefix github
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to capture |
| `--prefix` | no | `responsive` | Output file prefix (creates prefix-mobile.png, prefix-tablet.png, prefix-desktop.png) |

---

### page-to-pdf

Render any webpage as a PDF file.

```bash
flyto recipe page-to-pdf --url https://example.com
flyto recipe page-to-pdf --url https://en.wikipedia.org/wiki/YAML --output yaml-wiki.pdf --size Letter
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to convert |
| `--output` | no | `page.pdf` | Output PDF file path |
| `--size` | no | `A4` | Page size (A4, Letter, Legal) |

---

### visual-snapshot

Screenshot a page at both mobile (390×844) and desktop (1440×900) viewports.

```bash
flyto recipe visual-snapshot --url https://github.com
flyto recipe visual-snapshot --url https://example.com --mobile_output m.png --desktop_output d.png
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to capture |
| `--mobile_output` | no | `mobile.png` | Mobile screenshot output |
| `--desktop_output` | no | `desktop.png` | Desktop screenshot output |

---

### webpage-archive

Archive a webpage in 3 formats — screenshot (PNG), PDF, and HTML snapshot.

```bash
flyto recipe webpage-archive --url https://example.com
flyto recipe webpage-archive --url https://news.ycombinator.com --prefix hn-2024
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to archive |
| `--prefix` | no | `archive` | Output file prefix (creates prefix.png, prefix.pdf, prefix.html) |

---

### scrape-page

Extract text content from a webpage using a CSS selector.

```bash
flyto recipe scrape-page --url https://example.com --selector h1
flyto recipe scrape-page --url https://news.ycombinator.com --selector .titleline --output titles.json
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to scrape |
| `--selector` | yes | — | CSS selector (e.g. `h1`, `.title`, `#content`) |
| `--output` | no | `scraped.json` | Output file path |

---

### scrape-links

Extract all links from a webpage.

```bash
flyto recipe scrape-links --url https://example.com
flyto recipe scrape-links --url https://news.ycombinator.com --output hn-links.json
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to scrape links from |
| `--output` | no | `links.json` | Output file path |

---

### scrape-table

Extract an HTML table from a webpage and save as CSV.

```bash
flyto recipe scrape-table --url https://en.wikipedia.org/wiki/Python_(programming_language) --selector .wikitable
flyto recipe scrape-table --url https://example.com/data --selector "#results" --output table.csv
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL containing the table |
| `--selector` | no | `table` | CSS selector for the table element |
| `--output` | no | `table.csv` | Output file path |

---

### scrape-to-csv

Scrape structured data from a webpage and save as CSV. Configure row selector and column field selectors.

```bash
flyto recipe scrape-to-csv --url https://en.wikipedia.org/wiki/List_of_largest_companies_by_revenue --selector "table.wikitable tbody tr" --fields "td:nth-child(2),td:nth-child(3),td:nth-child(4)"
flyto recipe scrape-to-csv --url https://example.com/products --selector ".product" --fields ".name,.price,.rating" --output products.csv
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to scrape |
| `--selector` | yes | — | CSS selector for rows (e.g. `tr`, `.item`, `.product`) |
| `--fields` | yes | — | Comma-separated child selectors for columns |
| `--output` | no | `scraped.csv` | Output CSV file path |

---

### stock-price

Fetch current stock price from Yahoo Finance.

```bash
flyto recipe stock-price --symbol AAPL
flyto recipe stock-price --symbol TSLA --output tesla.json
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--symbol` | yes | — | Stock ticker symbol (e.g. AAPL, TSLA, NVDA) |
| `--output` | no | `stock.json` | Output file path |

---

## Data & OCR

### ocr

Extract text from an image using Tesseract OCR.

```bash
flyto recipe ocr --input scan.png
flyto recipe ocr --input receipt.jpg --lang eng --output receipt.txt
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--input` | yes | — | Path to image file |
| `--lang` | no | `eng` | Language code (`eng`, `chi_tra`, `jpn`, `deu`, `fra`, `spa`) |
| `--output` | no | `ocr-result.txt` | Output text file path |

Requires: `pip install pytesseract` and [Tesseract](https://github.com/tesseract-ocr/tesseract) installed.

---

### csv-to-json

Convert a CSV file to JSON format.

```bash
flyto recipe csv-to-json --input data.csv
flyto recipe csv-to-json --input users.csv --output users.json
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--input` | yes | — | Path to input CSV file |
| `--output` | no | `output.json` | Path to output JSON file |

---

### json-to-csv

Convert a JSON array file to CSV format.

```bash
flyto recipe json-to-csv --input data.json
flyto recipe json-to-csv --input records.json --output records.csv
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--input` | yes | — | Path to input JSON file |
| `--output` | no | `output.csv` | Path to output CSV file |

---

### pdf-extract

Extract text content from a PDF file.

```bash
flyto recipe pdf-extract --input report.pdf
flyto recipe pdf-extract --input contract.pdf --output contract.txt
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--input` | yes | — | Path to PDF file |
| `--output` | no | `extracted.txt` | Path to output text file |

---

## Image

### image-resize

Resize an image to specified dimensions.

```bash
flyto recipe image-resize --input photo.jpg --width 800
flyto recipe image-resize --input banner.png --width 1200 --output banner-sm.png
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--input` | yes | — | Path to input image |
| `--width` | yes | — | Target width in pixels |
| `--output` | no | `resized.png` | Path to output image |

---

### image-compress

Compress an image to reduce file size.

```bash
flyto recipe image-compress --input photo.jpg
flyto recipe image-compress --input photo.jpg --quality 60 --output small.jpg
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--input` | yes | — | Path to input image |
| `--quality` | no | `80` | Compression quality (1-100) |
| `--output` | no | `compressed.jpg` | Path to output image |

---

### image-convert

Convert an image between formats (PNG, JPG, WebP, BMP).

```bash
flyto recipe image-convert --input photo.png --format webp
flyto recipe image-convert --input logo.jpg --format png --output logo
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--input` | yes | — | Path to input image |
| `--format` | yes | — | Target format (`png`, `jpg`, `webp`, `bmp`) |
| `--output` | no | `converted` | Output path (extension auto-added) |

---

## Network & Security

### port-scan

Scan open ports on a host.

```bash
flyto recipe port-scan --host github.com
flyto recipe port-scan --host 192.168.1.1 --ports "80-443"
flyto recipe port-scan --host example.com --ports "22,80,443,3306,5432,8080"
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--host` | yes | — | Hostname or IP to scan |
| `--ports` | no | `22,80,443,3000,3306,5432,6379,8080,8443,9090` | Ports (comma-separated or range) |

---

### whois

Look up domain registration info — registrar, creation date, expiration, name servers.

```bash
flyto recipe whois --domain github.com
flyto recipe whois --domain example.com
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--domain` | yes | — | Domain name to look up |

---

## DevOps

### monitor-site

Check if a website is up and measure response time.

```bash
flyto recipe monitor-site --url https://myapp.com
flyto recipe monitor-site --url https://api.example.com --timeout 10000
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to check |
| `--timeout` | no | `5000` | Timeout in milliseconds |

---

### http-get

Fetch data from a URL and save the response.

```bash
flyto recipe http-get --url https://api.github.com/users/octocat
flyto recipe http-get --url https://jsonplaceholder.typicode.com/posts/1 --output post.json
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to fetch |
| `--output` | no | `response.json` | Path to save response |

---

### docker-ps

List running Docker containers.

```bash
flyto recipe docker-ps
flyto recipe docker-ps --all true
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--all` | no | `false` | Show all containers (including stopped) |

---

### git-changelog

Show git diff with file change statistics.

```bash
flyto recipe git-changelog
flyto recipe git-changelog --repo /path/to/repo --ref HEAD~5
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--repo` | no | `.` | Path to git repository |
| `--ref` | no | `HEAD` | Reference to diff against (commit, branch, tag) |

---

## Integrations

### scrape-to-slack

Extract data from a webpage and send it to Slack.

```bash
flyto recipe scrape-to-slack --url https://example.com --selector h1 --webhook $SLACK_WEBHOOK_URL
flyto recipe scrape-to-slack --url https://news.ycombinator.com --selector .titleline --webhook $SLACK_WEBHOOK_URL
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to scrape |
| `--selector` | yes | — | CSS selector to extract text from |
| `--webhook` | yes | — | Slack incoming webhook URL |

---

### github-issue

Screenshot a page and create a GitHub issue with the screenshot attached.

```bash
flyto recipe github-issue --url https://example.com --owner myorg --repo myapp --title "Homepage bug" --token $GITHUB_TOKEN
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--url` | yes | — | URL to screenshot |
| `--owner` | yes | — | GitHub repository owner |
| `--repo` | yes | — | GitHub repository name |
| `--title` | yes | — | Issue title |
| `--token` | yes | — | GitHub personal access token |

---

## Writing Your Own Recipes

Recipes are YAML files in `src/recipes/`. Format:

```yaml
name: My Recipe
description: What this recipe does

args:
  url:
    type: string
    required: true
    description: The target URL
  output:
    type: string
    default: result.json
    description: Where to save output

steps:
  - id: step1
    module: http.get
    params:
      url: "{{url}}"

  - id: step2
    module: file.write
    params:
      path: "{{output}}"
      content: "${step1.data}"
```

- `{{arg}}` — substituted with CLI `--arg` value before execution
- `${step.field}` — resolved at runtime from previous step output
- Args with `default` are optional; args with `required: true` must be provided
- Steps use any of the [467 built-in modules](TOOL_CATALOG.md)
