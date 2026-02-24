# Recipes

Pre-built workflow templates. No code, no API key — just `flyto recipe <name>`.

```bash
pip install flyto-core[browser]
playwright install chromium
flyto recipes  # list all
```

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

Extract an HTML table from a webpage and save the data.

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

Output:
```json
{
  "symbol": "AAPL",
  "price": "274.08",
  "change": "+7.90",
  "change_pct": "(+2.97%)"
}
```

---

## Data

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

Generate a changelog from git commit history.

```bash
flyto recipe git-changelog
flyto recipe git-changelog --since "30 days ago" --output CHANGELOG.md
flyto recipe git-changelog --repo /path/to/repo --since v1.0.0
```

| Arg | Required | Default | Description |
|-----|----------|---------|-------------|
| `--repo` | no | `.` | Path to git repository |
| `--since` | no | `7 days ago` | Show commits since (date, tag, or relative) |
| `--output` | no | `CHANGELOG.txt` | Output file path |

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
- Steps use any of the [412 built-in modules](TOOL_CATALOG.md)
