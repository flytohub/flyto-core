# Tool Catalog

> Auto-generated from flyto-core module registry. **451 modules** across **84 categories**.
>
> Generated from the active `ModuleRegistry`; do not edit manually.

## Categories

- [agent](#agent) (3)
- [ai](#ai) (10)
- [analysis](#analysis) (6)
- [api](#api) (13)
- [archive](#archive) (6)
- [array](#array) (15)
- [auth](#auth) (1)
- [aws](#aws) (4)
- [browser](#browser) (54)
- [cache](#cache) (4)
- [check](#check) (7)
- [cloud](#cloud) (6)
- [communication](#communication) (2)
- [compare](#compare) (1)
- [convert](#convert) (5)
- [core](#core) (4)
- [crypto](#crypto) (7)
- [data](#data) (13)
- [database](#database) (3)
- [datetime](#datetime) (4)
- [db](#db) (6)
- [decode](#decode) (3)
- [dns](#dns) (1)
- [docker](#docker) (6)
- [element](#element) (3)
- [email](#email) (2)
- [encode](#encode) (4)
- [env](#env) (3)
- [error](#error) (3)
- [excel](#excel) (2)
- [file](#file) (8)
- [flow](#flow) (24)
- [format](#format) (5)
- [git](#git) (3)
- [google](#google) (4)
- [graphql](#graphql) (2)
- [hash](#hash) (2)
- [http](#http) (7)
- [image](#image) (9)
- [k8s](#k8s) (5)
- [llm](#llm) (3)
- [logic](#logic) (5)
- [markdown](#markdown) (3)
- [math](#math) (6)
- [mcp](#mcp) (1)
- [meta](#meta) (4)
- [monitor](#monitor) (1)
- [network](#network) (4)
- [notification](#notification) (6)
- [notify](#notify) (1)
- [object](#object) (10)
- [output](#output) (1)
- [path](#path) (6)
- [payment](#payment) (3)
- [pdf](#pdf) (4)
- [port](#port) (2)
- [process](#process) (3)
- [productivity](#productivity) (3)
- [queue](#queue) (3)
- [random](#random) (4)
- [regex](#regex) (5)
- [sandbox](#sandbox) (3)
- [scheduler](#scheduler) (3)
- [set](#set) (4)
- [shell](#shell) (1)
- [slack](#slack) (1)
- [ssh](#ssh) (3)
- [stats](#stats) (8)
- [storage](#storage) (3)
- [string](#string) (11)
- [template](#template) (1)
- [test](#test) (8)
- [testing](#testing) (10)
- [text](#text) (6)
- [training](#training) (4)
- [ui](#ui) (1)
- [utility](#utility) (5)
- [validate](#validate) (7)
- [verification](#verification) (4)
- [verify](#verify) (9)
- [vision](#vision) (2)
- [warroom](#warroom) (6)
- [webhook](#webhook) (1)
- [word](#word) (2)

---

## agent

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `agent.autonomous` | Self-directed AI agent with memory and goal-oriented behavior | `goal` string *(required)*, `context` string, `max_iterations` number (default: `5`), `llm_provider` select (default: `openai`), `model` string (default: `gpt-4o`), `ollama_url` string (default: `http://localhost:11434`), `temperature` number (default: `0.7`) | `result` (string), `thoughts` (array), `iterations` (number), `goal_achieved` (boolean) |
| `agent.chain` | Sequential AI processing chain with multiple steps | `input` string *(required)*, `chain_steps` array *(required)*, `llm_provider` select (default: `openai`), `model` string (default: `gpt-4o`), `ollama_url` string (default: `http://localhost:11434`), `temperature` number (default: `0.7`) | `result` (string), `intermediate_results` (array), `steps_completed` (number) |
| `agent.tool_use` | AI Agent that can call tools/functions | `prompt` string *(required)*, `tools` array *(required)*, `provider` select (default: `openai`), `model` string (default: `gpt-4o`), `api_key` string, `max_iterations` number (default: `10`), `system_prompt` string | `result` (string), `tool_calls` (array), `iterations` (number), `model` (string) |

## ai

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `ai.embed` | Generate embeddings from text | `text` string *(required)*, `provider` select (default: `openai`), `model` string (default: `text-embedding-3-small`), `api_key` string, `dimensions` number | `embeddings` (array), `model` (string), `dimensions` (number), `token_count` (number) |
| `ai.extract` | Extract structured data from text using LLM | `text` string *(required)*, `schema` object *(required)*, `instructions` string, `provider` select (default: `openai`), `model` string (default: `gpt-4o-mini`), `api_key` string, `temperature` number (default: `0`) | `extracted` (object), `model` (string), `raw_response` (string) |
| `ai.local_ollama.chat` | Chat with local LLM via Ollama (completely offline) | `prompt` string *(required)*, `model` select (default: `llama2`), `temperature` number (default: `0.7`), `system_message` string, `ollama_url` string (default: `http://localhost:11434`), `max_tokens` number | `response` (string), `model` (string), `context` (array), `total_duration` (number), `load_duration` (number), `prompt_eval_count` (number), `eval_count` (number) |
| `ai.memory` | Conversation memory for AI Agent | `memory_type` select *(required)*, `window_size` number (default: `10`), `session_id` string (default: ``), `initial_messages` array (default: `[]`) | `memory_type` (string), `session_id` (string), `messages` (array), `config` (object) |
| `ai.memory.entity` | Extract and track entities (people, places, concepts) from conversations | `entity_types` multiselect (default: `['person', 'organization', ...`), `extraction_model` select *(required)*, `session_id` string (default: ``), `track_relationships` boolean (default: `True`), `max_entities` number (default: `100`) | `memory_type` (string), `session_id` (string), `entities` (object), `relationships` (array), `config` (object) |
| `ai.memory.redis` | Persistent conversation memory using Redis storage | `redis_url` string *(required)*, `key_prefix` string (default: `flyto:memory:`), `session_id` string *(required)*, `ttl_seconds` number (default: `86400`), `max_messages` number (default: `100`), `load_on_start` boolean (default: `True`) | `memory_type` (string), `session_id` (string), `messages` (array), `connected` (boolean), `config` (object) |
| `ai.memory.vector` | Semantic memory using vector embeddings for relevant context retrieval | `embedding_model` select *(required)*, `top_k` number (default: `5`), `similarity_threshold` number (default: `0.7`), `session_id` string (default: ``), `include_metadata` boolean (default: `True`) | `memory_type` (string), `session_id` (string), `embedding_model` (string), `config` (object) |
| `ai.model` | LLM model configuration for AI Agent | `provider` select (default: `openai`), `model` string (default: `gpt-4o`), `temperature` number (default: `0.7`), `api_key` string, `base_url` string, `max_tokens` number (default: `4096`) | `provider` (string), `model` (string), `config` (object) |
| `ai.tool` | Expose a module as a tool for AI Agent | `module_id` string *(required)*, `tool_description` string | `module_id` (string) |
| `ai.vision.analyze` | Analyze images using LLM vision capabilities | `image_path` string, `image_url` string, `prompt` string (default: `Describe this image in detail`), `provider` select (default: `openai`), `model` string (default: `gpt-4o`), `api_key` string, `max_tokens` number (default: `1000`), `detail` select (default: `auto`) | `analysis` (string), `model` (string), `provider` (string), `tokens_used` (number) |

## analysis

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `analysis.html.analyze_readability` | Analyze content readability | `html` string *(required)* | `type` (object), `properties` (any) |
| `analysis.html.extract_forms` | Extract form data from HTML | `html` string *(required)* | `type` (object), `properties` (any) |
| `analysis.html.extract_metadata` | Extract metadata from HTML | `html` string *(required)* | `type` (object), `properties` (any) |
| `analysis.html.extract_tables` | Extract table data from HTML | `html` string *(required)* | `type` (object), `properties` (any) |
| `analysis.html.find_patterns` | Find repeating data patterns in HTML | `html` string *(required)* | `type` (object), `properties` (any) |
| `analysis.html.structure` | Analyze HTML DOM structure | `html` string *(required)* | `type` (object), `properties` (any) |

## api

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `api.anthropic.chat` | Send a chat message to Anthropic Claude AI and get a response | `api_key` string, `model` string (default: `claude-sonnet-4-6`), `messages` array *(required)*, `max_tokens` number (default: `1024`), `temperature` number (default: `1.0`), `system` string | `content` (string), `model` (string), `stop_reason` (string), `usage` (object) |
| `api.github.create_issue` | Create a new issue in a GitHub repository | `owner` string *(required)*, `repo` string *(required)*, `title` string *(required)*, `body` text, `labels` array, `assignees` array, `token` string *(required)* | `status` (string), `issue` (object), `number` (number), `url` (string) |
| `api.github.create_pr` | Create a new pull request in a GitHub repository | `owner` string *(required)*, `repo` string *(required)*, `title` string *(required)*, `body` text, `head` string *(required)*, `base` string (default: `main`), `draft` boolean (default: `False`), `token` string *(required)* | `status` (string), `pr` (object), `number` (number), `url` (string) |
| `api.github.get_repo` | Get information about a GitHub repository | `owner` string *(required)*, `repo` string *(required)*, `token` string | `status` (string), `repo` (object), `name` (string), `full_name` (string), `description` (string), `stars` (number), `forks` (number), `url` (string) |
| `api.github.list_issues` | List issues from a GitHub repository | `owner` string *(required)*, `repo` string *(required)*, `state` select (default: `open`), `labels` string, `limit` number (default: `30`), `token` string | `status` (string), `issues` (array), `count` (number) |
| `api.github.list_repos` | List repositories for a GitHub user or the authenticated user | `owner` string *(required)*, `type` select (default: `all`), `sort` select (default: `updated`), `limit` number (default: `30`), `token` string | `status` (string), `repos` (array), `count` (number) |
| `api.google_gemini.chat` | Send a chat message to Google Gemini AI and get a response | `api_key` string, `model` string (default: `gemini-2.5-pro`), `prompt` string *(required)*, `temperature` number (default: `1.0`), `max_output_tokens` number (default: `2048`) | `text` (string), `model` (string), `candidates` (array) |
| `api.google_sheets.read` | Read data from Google Sheets spreadsheet | `credentials` object, `spreadsheet_id` string *(required)*, `range` string *(required)*, `include_header` boolean (default: `True`) | `values` (array), `data` (array), `row_count` (number) |
| `api.google_sheets.write` | Write data to Google Sheets spreadsheet | `credentials` object, `spreadsheet_id` string *(required)*, `range` string *(required)*, `values` array *(required)*, `value_input_option` string (default: `USER_ENTERED`) | `updated_range` (string), `updated_rows` (number), `updated_columns` (number), `updated_cells` (number) |
| `api.notion.create_page` | Create a new page in Notion database | `api_key` string, `database_id` string *(required)*, `properties` object *(required)*, `content` array | `page_id` (string), `url` (string), `created_time` (string) |
| `api.notion.query_database` | Query pages from Notion database with filters and sorting | `api_key` string, `database_id` string *(required)*, `filter` object, `sorts` array, `page_size` number (default: `100`) | `results` (array), `count` (number), `has_more` (boolean) |
| `api.openai.chat` | Send a chat message to OpenAI GPT models | `prompt` string *(required)*, `model` select (default: `gpt-4o`), `temperature` number (default: `0.7`), `max_tokens` number (default: `1000`), `system_message` string | `response` (string), `model` (string), `usage` (object) |
| `api.openai.image` | Generate images using DALL-E | `prompt` string *(required)*, `size` select (default: `1024x1024`), `model` select (default: `dall-e-3`), `quality` select (default: `standard`), `n` number (default: `1`) | `images` (array), `model` (string) |

## archive

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `archive.gunzip` | Decompress a gzip-compressed file | `input_path` string *(required)*, `output_path` string | `path` (string), `size` (number) |
| `archive.gzip` | Compress a single file using gzip | `input_path` string *(required)*, `output_path` string | `path` (string), `original_size` (number), `compressed_size` (number), `ratio` (number) |
| `archive.tar_create` | Create a TAR archive with optional gzip/bz2/xz compression | `output_path` string *(required)*, `files` array *(required)*, `compression` select (default: `gzip`) | `path` (string), `size` (number), `file_count` (number) |
| `archive.tar_extract` | Extract files from a TAR archive (auto-detects compression) | `archive_path` string *(required)*, `output_dir` string *(required)* | `extracted_files` (array), `total_size` (number) |
| `archive.zip_create` | Create a ZIP archive from a list of files | `output_path` string *(required)*, `files` array *(required)*, `compression` select (default: `deflated`), `password` string | `path` (string), `size` (number), `file_count` (number) |
| `archive.zip_extract` | Extract files from a ZIP archive | `archive_path` string *(required)*, `output_dir` string *(required)*, `password` string | `extracted_files` (array), `total_size` (number) |

## array

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `array.chunk` | Split array into chunks of specified size | `array` array *(required)*, `size` number *(required)* | `result` (array), `chunks` (number) |
| `array.compact` | Remove null/empty values from array | `array` array *(required)*, `remove_empty_strings` boolean (default: `True`), `remove_zero` boolean (default: `False`), `remove_false` boolean (default: `False`) | `result` (array), `removed` (number) |
| `array.difference` | Find elements in first array not in others | `array` array *(required)*, `subtract` array *(required)* | `result` (array), `length` (number) |
| `array.drop` | Drop first N elements from array | `array` array *(required)*, `count` number *(required)* | `result` (array), `dropped` (number) |
| `array.filter` | Filter array elements by condition | `array` array *(required)*, `condition` select *(required)*, `value` string *(required)* | `filtered` (array), `count` (number) |
| `array.flatten` | Flatten nested arrays into single array | `array` array *(required)*, `depth` number (default: `1`) | `result` (array), `length` (number) |
| `array.group_by` | Group array elements by a key | `array` array *(required)*, `key` string *(required)* | `groups` (object), `keys` (array), `count` (number) |
| `array.intersection` | Find common elements between arrays | `arrays` array *(required)* | `result` (array), `length` (number) |
| `array.join` | Join array elements into string | `array` array *(required)*, `separator` select (default: `,`) | `result` (string) |
| `array.map` | Transform each element in an array | `array` array *(required)*, `operation` select *(required)*, `value` any | `result` (array), `length` (number) |
| `array.reduce` | Reduce array to single value | `array` array *(required)*, `operation` select *(required)*, `separator` select (default: `,`) | `result` (any), `operation` (string) |
| `array.sort` | Sort array elements in ascending or descending order | `array` array *(required)*, `order` select (default: `asc`) | `sorted` (array), `count` (number) |
| `array.take` | Take first N elements from array | `array` array *(required)*, `count` number *(required)* | `result` (array), `length` (number) |
| `array.unique` | Remove duplicate values from array | `array` array *(required)*, `preserve_order` boolean (default: `True`) | `unique` (array), `count` (number), `duplicates_removed` (number) |
| `array.zip` | Combine multiple arrays element-wise | `arrays` array *(required)*, `fill_value` any | `result` (array), `length` (number) |

## auth

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `auth.oauth2` | Exchange authorization code, refresh token, or client credentials for an access token | `token_url` string *(required)*, `grant_type` string (default: `authorization_code`), `client_id` string *(required)*, `client_secret` string, `code` string, `redirect_uri` string, `refresh_token` string, `scope` string, `code_verifier` string, `client_auth_method` string (default: `body`), `extra_params` object (default: `{}`), `timeout` number (default: `15`) | `ok` (boolean), `access_token` (string), `token_type` (string), `expires_in` (number), `refresh_token` (string), `scope` (string), `raw` (object), `duration_ms` (number) |

## aws

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `aws.s3.delete` | Delete an object from an AWS S3 bucket | `bucket` string *(required)*, `key` string *(required)*, `region` string (default: `us-east-1`), `access_key_id` string, `secret_access_key` string | `bucket` (string), `key` (string), `deleted` (boolean) |
| `aws.s3.download` | Download a file from an AWS S3 bucket to a local path | `bucket` string *(required)*, `key` string *(required)*, `output_path` string *(required)*, `region` string (default: `us-east-1`), `access_key_id` string, `secret_access_key` string | `path` (string), `size` (number), `content_type` (string) |
| `aws.s3.list` | List objects in an AWS S3 bucket with optional prefix filter | `bucket` string *(required)*, `prefix` string, `max_keys` number (default: `100`), `region` string (default: `us-east-1`), `access_key_id` string, `secret_access_key` string | `objects` (array), `count` (number), `truncated` (boolean) |
| `aws.s3.upload` | Upload a local file to an AWS S3 bucket | `bucket` string *(required)*, `key` string *(required)*, `file_path` string *(required)*, `region` string (default: `us-east-1`), `access_key_id` string, `secret_access_key` string, `content_type` string | `bucket` (string), `key` (string), `url` (string), `size` (number) |

## browser

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `browser.challenge` | Auto-detect and handle anti-bot challenges (Cloudflare, CAPTCHA). Waits for auto-resolution, falls back to human-in-the-loop. | `auto_wait_seconds` number (default: `15`), `captcha_provider` select (default: ``), `captcha_api_key` string, `human_fallback` boolean (default: `True`), `human_timeout_seconds` number (default: `120`) | `status` (string), `challenge_type` (string), `wait_seconds` (number), `required_human` (boolean) |
| `browser.click` | Click an element on the page. Run browser.snapshot first to find the correct selector from the real page DOM. | `click_method` select (default: `text`), `target` string, `selector` string, `button` select (default: `left`), `click_count` number (default: `1`), `force` boolean (default: `False`), `modifiers` array, `timeout` number (default: `30000`) | `browser` (object), `status` (string), `selector` (string), `method` (string) |
| `browser.close` | Close the browser instance and release resources | `_no_params` boolean (default: `True`) | `status` (string), `message` (string) |
| `browser.connect` | Connect to a remote browser service (Browserless, BrowserBase, CDP). Real fingerprints, residential IPs. | `ws_endpoint` string *(required)*, `viewport_width` number (default: `1280`), `viewport_height` number (default: `720`), `locale` string (default: `en-US`), `timeout_ms` number (default: `30000`) | `connected` (boolean), `browser_type` (string), `endpoint` (string) |
| `browser.console` | Capture browser console logs (errors, warnings, info) | `level` select (default: `all`), `timeout` number (default: `5000`), `clear_existing` boolean (default: `False`) | `status` (string), `messages` (array), `count` (number) |
| `browser.cookies` | Get, set, or clear browser cookies | `action` select *(required)*, `name` string, `value` string, `domain` string, `path` string (default: `/`), `secure` boolean (default: `False`), `httpOnly` boolean (default: `False`), `expires` number | `status` (string), `cookies` (array), `count` (number) |
| `browser.cookies_file` | Import or export browser cookies to/from a JSON file for session persistence. | `action` select *(required)*, `file_path` string *(required)*, `domain_filter` string (default: ``) | `action` (string), `cookie_count` (number), `file_path` (string), `domains` (array) |
| `browser.detect` | Smart element detection with multi-strategy matching. Finds elements using text, selector, role, proximity, and fuzzy matching with automatic fallbacks. | `text` string, `selector` string, `alternatives` string, `role` select (default: `any`), `near_text` string, `match_mode` select (default: `best`), `action` select (default: `none`), `action_value` string, `timeout` number (default: `10000`) | `status` (string), `found` (boolean), `selector` (string), `strategy` (string), `confidence` (number), `element` (object), `candidates` (array), `action_result` (string) |
| `browser.detect_list` | Auto-detect repeating items on any page (articles, products, search results). No selectors needed. | `min_items` number (default: `3`), `max_items` number (default: `200`), `include_text` boolean (default: `True`), `selector` string (default: ``) | `items` (array), `count` (number), `selector` (string), `auto_detected` (boolean), `content_found` (boolean), `consistency` (number) |
| `browser.dialog` | Handle alert, confirm, and prompt dialogs | `action` select *(required)*, `prompt_text` string, `timeout` number (default: `30000`) | `status` (string), `message` (string), `type` (string), `default_value` (string) |
| `browser.download` | Download file from browser | `selector` string, `save_path` string *(required)*, `timeout_ms` number (default: `60000`) | `status` (string), `path` (string), `filename` (string), `size` (number) |
| `browser.drag` | Drag and drop elements | `source` string *(required)*, `target` string *(required)*, `source_position` object, `target_position` object, `timeout` number (default: `30000`) | `status` (string), `source` (string), `target` (string) |
| `browser.emulate` | Emulate mobile devices, tablets, and custom viewports | `device` select *(required)*, `width` number, `height` number, `user_agent` string, `device_scale_factor` number, `is_mobile` boolean, `has_touch` boolean | `status` (string), `device` (string), `viewport` (object), `is_mobile` (boolean) |
| `browser.ensure` | Ensure a browser session exists (reuse or launch) | `headless` boolean (default: `False`), `width` number (default: `1280`), `height` number (default: `720`) | `status` (string), `message` (string), `is_owner` (boolean) |
| `browser.evaluate` | Execute JavaScript code in page context | `script` string *(required)*, `args` array | `status` (string), `result` (any) |
| `browser.extract` | Extract structured data from the page. Run browser.snapshot first to find the correct selector from the real page DOM. | `selector` string *(required)*, `limit` number, `fields` object | `status` (string), `data` (array), `count` (number) |
| `browser.extract_nested` | Extract tree/nested data (comments, threads, folders). Returns hierarchical structure with children. | `root_selector` string *(required)*, `children_selector` string (default: ``), `fields` object (default: `{}`), `max_depth` number (default: `10`), `limit` number (default: `0`) | `items` (array), `count` (number), `total_nodes` (number) |
| `browser.find` | Find elements in page and return element ID list. Run browser.snapshot first to find the correct selector from the real page DOM. | `selector` string *(required)*, `limit` number | `status` (string), `count` (number), `element_ids` (array) |
| `browser.form` | Smart form filling with automatic field detection. Run browser.snapshot first to find the correct selectors from the real page DOM. | `form_selector` string, `data` object *(required)*, `field_mapping` object, `clear_before_fill` boolean (default: `True`), `submit` boolean (default: `False`), `submit_selector` string, `delay_between_fields_ms` number (default: `100`) | `filled_fields` (array), `failed_fields` (array), `submitted` (boolean) |
| `browser.frame` | Switch to iframe or frame context | `selector` string, `name` string, `url` string, `action` string (default: `enter`), `timeout` number (default: `30000`) | `status` (string), `frame_url` (string), `frame_name` (string), `frames` (array) |
| `browser.geolocation` | Mock browser geolocation | `latitude` number *(required)*, `longitude` number *(required)*, `accuracy` number (default: `100`) | `status` (string), `location` (object) |
| `browser.goto` | Navigate to a specific URL | `url` string *(required)*, `wait_until` select (default: `domcontentloaded`), `timeout_ms` number (default: `30000`), `ssrf_protection` boolean (default: `True`) | `status` (string), `url` (string) |
| `browser.hover` | Hover mouse over an element | `selector` string *(required)*, `timeout_ms` number (default: `30000`), `position` object | `status` (string), `selector` (string) |
| `browser.interact` | Pause for user to interact with the browser page. Shows page elements in a dialog for the user to choose an action. | `title` string (default: `Browser Interaction`), `description` string, `timeout_seconds` number (default: `0`) | `status` (string), `action` (string), `selector` (string), `value` (string), `url` (string) |
| `browser.launch` | Launch a new browser instance with Playwright | `headless` boolean (default: `False`), `width` number (default: `1280`), `height` number (default: `720`), `browser_type` select (default: `chromium`), `channel` select (default: ``), `behavior` select (default: `fast`), `stealth` boolean (default: `True`), `proxy` string, `user_agent` string, `locale` string (default: `en-US`), `slow_mo` number (default: `0`), `record_video_dir` string | `status` (string), `message` (string), `browser_type` (string), `headless` (boolean), `viewport` (object), `behavior` (string) |
| `browser.login` | Auto-detect and fill login forms. Handles username + password + submit with post-login verification. | `username` string *(required)*, `password` string *(required)*, `success_indicator` string (default: ``), `username_selector` string (default: ``), `password_selector` string (default: ``), `submit_selector` string (default: ``), `wait_ms` number (default: `5000`) | `logged_in` (boolean), `url_after` (string), `url_changed` (boolean), `fields_found` (object) |
| `browser.navigation` | Navigate back, forward, or reload the page | `action` select *(required)*, `wait_until` select (default: `domcontentloaded`), `timeout_ms` number (default: `30000`) | `status` (string), `action` (string), `url` (string) |
| `browser.network` | Monitor and intercept network requests | `action` select *(required)*, `url_pattern` string, `resource_type` string, `timeout` number (default: `30000`), `mock_response` object, `include_headers` boolean (default: `True`), `strip_query` boolean (default: `False`) | `status` (string), `requests` (array), `blocked_count` (number) |
| `browser.pages` | List all open browser pages/tabs with details | `include_details` boolean (default: `True`), `include_content_info` boolean (default: `False`) | `status` (string), `pages` (array), `count` (number), `current_index` (number) |
| `browser.pagination` | Auto-paginate through pages and extract data. Supports retry and checkpoint resume. | `mode` select (default: `next_button`), `item_selector` string *(required)*, `next_selector` string, `load_more_selector` string, `fields` object, `max_pages` number (default: `10`), `max_items` number (default: `0`), `wait_between_pages_ms` number (default: `1000`), `retry_on_error` boolean (default: `True`), `max_retries` number (default: `3`), `checkpoint_path` string, `wait_for_selector` string, `scroll_amount` number (default: `1000`), `no_more_indicator` string | `items` (array), `total_items` (integer), `pages_processed` (integer), `stopped_reason` (string), `retries_used` (integer), `resumed` (boolean) |
| `browser.pdf` | Generate PDF from current page | `path` string (default: ``), `page_size` select (default: `A4`), `orientation` select (default: `portrait`), `print_background` boolean (default: `True`), `scale` number (default: `1`), `margin` number (default: `20`), `header` string, `footer` string | `status` (string), `path` (string), `size` (number) |
| `browser.performance` | Collect Web Vitals (LCP, FCP, CLS, TTFB) and performance metrics | `metrics` array (default: `['all']`), `timeout_ms` number (default: `3000`), `setup_observers` boolean (default: `True`) | `status` (string), `metrics` (object) |
| `browser.pool` | Manage multiple named browser instances for parallel automation. | `action` select *(required)*, `name` string (default: `default`), `headless` boolean (default: `True`), `stealth` boolean (default: `True`) | `action` (string), `name` (string), `pool` (array), `count` (number) |
| `browser.press` | Press a keyboard key | `key` string *(required)* | `status` (string), `key` (string) |
| `browser.proxy_rotate` | Rotate through a list of proxies. Relaunches browser with the next proxy. | `action` select *(required)*, `proxies` array (default: `[]`), `strategy` select (default: `round_robin`), `provider_url` string (default: ``), `provider_token` string (default: ``), `headless` boolean (default: `True`), `preserve_cookies` boolean (default: `True`) | `action` (string), `current_proxy` (string), `pool_size` (number), `alive` (number), `dead` (number) |
| `browser.readability` | Smart article extraction — extracts title, author, date, and main content from any webpage. Works like Firefox Reader Mode. | `include_images` boolean (default: `True`), `include_links` boolean (default: `False`), `wait_ms` number (default: `0`), `selector` string (default: ``), `title_selector` string (default: ``), `min_content_length` number (default: `80`), `clean_selectors` array (default: `[]`), `ai_fallback` boolean (default: `False`) | `title` (string), `author` (string), `date` (string), `content` (string), `html` (string), `excerpt` (string), `site_name` (string), `image` (string), `images` (array), `videos` (array), `links` (array), `word_count` (number), `language` (string), `url` (string), `content_found` (boolean) |
| `browser.record` | Record user actions as workflow | `action` string *(required)*, `output_format` string (default: `yaml`), `output_path` string (default: ``) | `status` (string), `recording` (array), `workflow` (string) |
| `browser.release` | Release browser session (close only if owned) | `force` boolean (default: `False`) | `status` (string), `message` (string), `was_owner` (boolean) |
| `browser.response` | Capture API response bodies (XHR/fetch). Filter by URL pattern, extract JSON data from page API calls. | `url_pattern` string *(required)*, `wait_ms` number (default: `5000`), `max_responses` number (default: `0`), `resource_types` string (default: `xhr,fetch`), `include_headers` boolean (default: `False`) | `responses` (array), `count` (number) |
| `browser.robots` | Check robots.txt compliance and discover sitemaps. Verify if a URL is allowed for scraping. | `check_url` string (default: ``), `user_agent` string (default: `*`) | `exists` (boolean), `allowed` (boolean), `matched_rule` (string), `crawl_delay` (number), `sitemaps` (array), `rule_count` (number) |
| `browser.screenshot` | Take a screenshot of the current page | `path` string (default: `screenshot.png`), `full_page` boolean (default: `False`), `format` select (default: `png`), `quality` number | `status` (string), `filepath` (string) |
| `browser.scroll` | Scroll page to element, position, or direction. Run browser.snapshot first to find the correct selector from the real page DOM. | `selector` string, `direction` select (default: `down`), `amount` number (default: `500`), `behavior` select (default: `smooth`) | `status` (string), `scrolled_to` (object) |
| `browser.select` | Select option from dropdown element. Run browser.snapshot first to find the correct selector from the real page DOM. | `selector` string *(required)*, `select_method` select (default: `value`), `target` string, `index` number, `timeout` number (default: `30000`) | `status` (string), `selected` (array), `selector` (string) |
| `browser.sitemap` | Parse sitemap.xml and extract URLs. Supports sitemap index files and URL filtering. | `sitemap_url` string (default: ``), `url_pattern` string (default: ``), `max_urls` number (default: `0`), `follow_index` boolean (default: `True`) | `urls` (array), `count` (number), `is_index` (boolean), `child_sitemaps` (number) |
| `browser.snapshot` | Capture DOM snapshot in HTML, MHTML, or text format | `format` select (default: `html`), `selector` string, `path` string (default: ``) | `status` (string), `format` (string), `content` (string), `path` (string), `size_bytes` (number) |
| `browser.storage` | Access localStorage and sessionStorage | `action` select *(required)*, `type` select (default: `local`), `key` string, `value` string | `status` (string), `value` (any), `keys` (array), `length` (number) |
| `browser.tab` | Create, switch, and close browser tabs | `action` string *(required)*, `url` string, `index` number, `ssrf_protection` boolean (default: `True`) | `status` (string), `tab_count` (number), `current_index` (number), `tabs` (array) |
| `browser.table` | Extract HTML tables as structured data. Auto-detects headers from thead/th. | `selector` string (default: `table`), `table_index` number (default: `0`), `max_rows` number (default: `0`), `include_html` boolean (default: `False`) | `rows` (array), `headers` (array), `count` (number), `tables_found` (number) |
| `browser.throttle` | Per-domain rate limiting. Waits between requests to the same domain to avoid bans. | `strategy` select (default: `fixed`), `min_interval_ms` number (default: `2000`), `max_interval_ms` number (default: `15000`), `url` string (default: ``), `signal` select (default: `none`) | `domain` (string), `waited_ms` (number), `interval_ms` (number), `strategy` (string) |
| `browser.trace` | Start/stop Chrome DevTools performance tracing (Chromium only) | `action` string *(required)*, `categories` array (default: `['devtools.timeline']`), `screenshots` boolean (default: `True`), `path` string (default: ``) | `status` (string), `tracing` (boolean), `path` (string), `size_bytes` (number) |
| `browser.type` | Type text into an input field. Run browser.snapshot first to find the correct selector from the real page DOM. | `type_method` select (default: `placeholder`), `target` string, `selector` string, `input_type` select (default: `text`), `text` string *(required)*, `sensitive_text` string *(required)*, `delay` number (default: `0`), `clear` boolean (default: `False`), `timeout` number (default: `30000`) | `browser` (object), `status` (string), `selector` (string), `method` (string) |
| `browser.upload` | Upload file to file input element | `selector` string *(required)*, `file_path` string *(required)*, `timeout_ms` number (default: `30000`) | `status` (string), `filename` (string), `size` (number), `selector` (string) |
| `browser.viewport` | Resize browser viewport to specific dimensions | `width` number *(required)*, `height` number *(required)* | `status` (string), `viewport` (object), `previous_viewport` (object) |
| `browser.wait` | Wait for a duration or until an element appears | `duration_ms` number (default: `1000`), `selector` string, `state` select (default: `visible`), `timeout_ms` number (default: `30000`) | `status` (string), `selector` (string), `duration_ms` (number) |

## cache

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `cache.clear` | Clear all cache entries or filter by pattern | `pattern` string (default: `*`), `backend` string (default: `memory`), `redis_url` string (default: `redis://localhost:6379`) | `cleared_count` (number), `backend` (string) |
| `cache.delete` | Delete a cache entry by key | `key` string *(required)*, `backend` string (default: `memory`), `redis_url` string (default: `redis://localhost:6379`) | `key` (string), `deleted` (boolean), `backend` (string) |
| `cache.get` | Get a value from cache by key | `key` string *(required)*, `backend` string (default: `memory`), `redis_url` string (default: `redis://localhost:6379`) | `key` (string), `value` (any), `hit` (boolean), `backend` (string) |
| `cache.set` | Set a value in cache with optional TTL | `key` string *(required)*, `value` string *(required)*, `ttl` number (default: `0`), `backend` string (default: `memory`), `redis_url` string (default: `redis://localhost:6379`) | `key` (string), `stored` (boolean), `ttl` (number), `backend` (string) |

## check

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `check.is_array` | Check if a value is an array | `value` any *(required)* | `is_array` (boolean), `length` (number) |
| `check.is_empty` | Check if a value is empty | `value` any *(required)*, `trim_strings` boolean (default: `True`) | `is_empty` (boolean), `type` (string) |
| `check.is_null` | Check if a value is null/None | `value` any | `is_null` (boolean) |
| `check.is_number` | Check if a value is a number | `value` any *(required)*, `parse_string` boolean (default: `False`), `integer_only` boolean (default: `False`) | `is_number` (boolean), `is_integer` (boolean), `is_float` (boolean) |
| `check.is_object` | Check if a value is an object | `value` any *(required)* | `is_object` (boolean), `keys` (array) |
| `check.is_string` | Check if a value is a string | `value` any *(required)* | `is_string` (boolean), `length` (number) |
| `check.type_of` | Get the type of a value | `value` any | `type` (string), `is_primitive` (boolean) |

## cloud

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `cloud.aws_s3.download` | Download a file from AWS S3 bucket | `aws_access_key_id` string, `aws_secret_access_key` string, `region` string (default: `us-east-1`), `bucket` string *(required)*, `key` string *(required)*, `file_path` string | `content` (string), `file_path` (string), `size` (number), `content_type` (string) |
| `cloud.aws_s3.upload` | Upload a file or data to AWS S3 bucket | `aws_access_key_id` string, `aws_secret_access_key` string, `region` string (default: `us-east-1`), `bucket` string *(required)*, `key` string *(required)*, `file_path` string, `content` string, `content_type` string, `acl` string (default: `private`) | `url` (string), `bucket` (string), `key` (string), `etag` (string) |
| `cloud.azure.download` | Download file from Azure Blob Storage | `connection_string` string, `container` string *(required)*, `blob_name` string *(required)*, `destination_path` string *(required)* | `file_path` (string), `size` (number), `container` (string), `blob_name` (string) |
| `cloud.azure.upload` | Upload file to Azure Blob Storage | `file_path` string *(required)*, `connection_string` string, `container` string *(required)*, `blob_name` string, `content_type` string | `url` (string), `container` (string), `blob_name` (string), `size` (number) |
| `cloud.gcs.download` | Download file from Google Cloud Storage | `bucket` string *(required)*, `object_name` string *(required)*, `destination_path` string *(required)* | `file_path` (string), `size` (number), `bucket` (string), `object_name` (string) |
| `cloud.gcs.upload` | Upload file to Google Cloud Storage | `file_path` string *(required)*, `bucket` string *(required)*, `object_name` string, `content_type` string, `public` boolean (default: `False`) | `url` (string), `bucket` (string), `object_name` (string), `size` (number), `public_url` (string) |

## communication

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `communication.twilio.make_call` | Make a voice call via Twilio | `account_sid` string, `auth_token` string, `from_number` string *(required)*, `to_number` string *(required)*, `twiml_url` string *(required)* | `sid` (string), `status` (string), `to` (string), `from` (string) |
| `communication.twilio.send_sms` | Send SMS message via Twilio | `account_sid` string, `auth_token` string, `from_number` string *(required)*, `to_number` string *(required)*, `message` string *(required)* | `sid` (string), `status` (string), `to` (string), `from` (string) |

## compare

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `compare.change` | Detect if a value has changed beyond threshold (by amount or percentage) | `current_value` number *(required)*, `previous_value` number *(required)*, `mode` select (default: `percent`), `threshold` number (default: `5`), `direction` select (default: `both`) | `ok` (boolean), `changed` (boolean), `direction` (string), `change_percent` (number), `change_absolute` (number), `current_value` (number), `previous_value` (number), `summary` (string) |

## convert

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `convert.to_array` | Convert value to array | `value` any *(required)*, `split_string` boolean (default: `False`), `delimiter` string (default: ``) | `result` (array), `length` (number), `original_type` (string) |
| `convert.to_boolean` | Convert value to boolean | `value` any *(required)*, `strict` boolean (default: `False`) | `result` (boolean), `original_type` (string) |
| `convert.to_number` | Convert value to number | `value` any *(required)*, `default` number (default: `0`), `integer` boolean (default: `False`) | `result` (number), `success` (boolean), `original_type` (string) |
| `convert.to_object` | Convert value to object | `value` any *(required)*, `key_name` string (default: `value`) | `result` (object), `keys` (array), `original_type` (string) |
| `convert.to_string` | Convert any value to string | `value` any *(required)*, `pretty` boolean (default: `False`) | `result` (string), `original_type` (string) |

## core

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `core.api.google_search` | Use Google Custom Search API to search keywords | `keyword` string *(required)*, `limit` number (default: `10`) | `status` (string), `data` (array), `count` (number), `total_results` (number) |
| `core.api.http_get` | Send HTTP GET request to any URL | `url` string *(required)*, `headers` object (default: `{}`), `params` object (default: `{}`), `timeout` number (default: `30`), `verify_ssl` boolean (default: `True`) | `status_code` (number), `headers` (object), `body` (string), `json` (object) |
| `core.api.http_post` | Send HTTP POST request to any URL | `url` string *(required)*, `headers` object (default: `{}`), `body` string, `json` any, `timeout` number (default: `30`), `verify_ssl` boolean (default: `True`) | `status_code` (number), `headers` (object), `body` (string), `json` (object) |
| `core.api.serpapi_search` | Use SerpAPI to search keywords (100 free searches/month) | `keyword` string *(required)*, `limit` number (default: `10`) | `status` (string), `data` (array), `count` (number) |
| `core.api.tavily_search` | Use Tavily API to search the web (1000 free credits/month) | `keyword` string *(required)*, `limit` number (default: `10`) | `status` (string), `data` (array), `count` (number) |

## crypto

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `crypto.decrypt` | AES symmetric decryption | `ciphertext` string *(required)*, `key` string *(required)*, `mode` select (default: `GCM`), `input_format` select (default: `base64`) | `plaintext` (string), `algorithm` (string) |
| `crypto.encrypt` | AES symmetric encryption | `plaintext` string *(required)*, `key` string *(required)*, `mode` select (default: `GCM`), `output_format` select (default: `base64`) | `ciphertext` (string), `algorithm` (string), `mode` (string) |
| `crypto.hmac` | Generate HMAC signature | `message` string *(required)*, `key` string *(required)*, `algorithm` select (default: `sha256`), `encoding` select (default: `hex`) | `signature` (string), `algorithm` (string) |
| `crypto.jwt_create` | Create JWT (JSON Web Token) tokens | `payload` object *(required)*, `secret` string *(required)*, `algorithm` select (default: `HS256`), `expires_in` number, `issuer` string, `audience` string | `token` (string), `algorithm` (string), `expires_at` (string) |
| `crypto.jwt_verify` | Verify and decode JWT tokens | `token` string *(required)*, `secret` string *(required)*, `algorithms` array (default: `['HS256']`), `verify_exp` boolean (default: `True`), `audience` string, `issuer` string | `valid` (boolean), `payload` (object), `header` (object) |
| `crypto.random_bytes` | Generate cryptographically secure random bytes | `length` number *(required)*, `encoding` string (default: `hex`) | `bytes` (string), `length` (number) |
| `crypto.random_string` | Generate cryptographically secure random string | `length` number *(required)*, `charset` string (default: `alphanumeric`), `uppercase` boolean (default: `False`) | `string` (string), `length` (number) |

## data

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `data.csv.read` | Read and parse CSV file into array of objects | `path` string *(required)*, `delimiter` select (default: `,`), `encoding` select (default: `utf-8`), `skip_header` boolean (default: `False`) | `status` (string), `data` (array), `rows` (number), `columns` (array) |
| `data.csv.write` | Write array of objects to CSV file | `path` string *(required)*, `data` array *(required)*, `delimiter` select (default: `,`), `encoding` select (default: `utf-8`) | `status` (string), `file_path` (string), `rows_written` (number) |
| `data.dedup` | Remove duplicate records from an array by key fields. Optionally persists seen hashes to disk or execution context for cross-run dedup. Use storage=context in cloud/stateless environments where disk is ephemeral. | `items` array *(required)*, `keys` array (default: `[]`), `storage` select (default: `disk`), `hash_file` string, `max_hashes` number (default: `100000`) | `items` (array), `total_in` (integer), `total_out` (integer), `duplicates` (integer), `hash_count` (integer) |
| `data.json.parse` | Parse JSON string into object | `json_string` string *(required)* | `status` (string), `data` (object) |
| `data.json.stringify` | Convert object to JSON string | `data` object *(required)*, `pretty` boolean (default: `False`), `indent` number (default: `2`) | `status` (string), `json` (string) |
| `data.json_to_csv` | Convert JSON data or files to CSV format | `input_data` any *(required)*, `output_path` string (default: `/tmp/output.csv`), `delimiter` select (default: `,`), `include_header` boolean (default: `True`), `flatten_nested` boolean (default: `True`), `columns` array (default: `[]`) | `output_path` (string), `row_count` (number), `column_count` (number), `columns` (array) |
| `data.pipeline` | Chain multiple data transformations in a single step | `input` any *(required)*, `steps` array *(required)* | `result` (any), `original_count` (integer), `result_count` (integer), `steps_applied` (integer) |
| `data.text.template` | Fill text template with variables | `template` string *(required)*, `variables` object *(required)* | `status` (string), `result` (string) |
| `data.validate_records` | Validate extracted records against field rules. Splits output into valid and invalid arrays. | `items` array *(required)*, `rules` object *(required)*, `mode` select (default: `filter`), `drop_fields` array (default: `[]`) | `items` (array), `invalid` (array), `total_in` (integer), `valid_count` (integer), `invalid_count` (integer) |
| `data.xml.generate` | Generate XML string from Python dict | `data` object *(required)*, `root_tag` string (default: `root`), `pretty` boolean (default: `True`), `encoding` string (default: `utf-8`), `declaration` boolean (default: `True`) | `xml` (string) |
| `data.xml.parse` | Parse XML string or file into Python dict | `content` string, `file_path` string, `preserve_attributes` boolean (default: `True`) | `result` (object), `root_tag` (string) |
| `data.yaml.generate` | Generate YAML string from Python object | `data` any *(required)*, `default_flow_style` boolean (default: `False`), `sort_keys` boolean (default: `False`), `indent` number (default: `2`), `allow_unicode` boolean (default: `True`) | `yaml` (string) |
| `data.yaml.parse` | Parse YAML string or file into Python object | `content` string, `file_path` string, `multi_document` boolean (default: `False`) | `result` (any), `type` (string) |

## database

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `database.insert` | Insert data into database tables | `table` string *(required)*, `data` object *(required)*, `database_type` select (default: `postgresql`), `connection_string` string, `host` string, `port` number, `database` string, `user` string, `password` string, `returning` array | `inserted_count` (number), `returning_data` (array) |
| `database.query` | Execute SQL queries on PostgreSQL, MySQL, or SQLite databases | `query` string *(required)*, `params` array (default: `[]`), `database_type` select (default: `postgresql`), `connection_string` string, `host` string, `port` number, `database` string, `user` string, `password` string, `fetch` select (default: `all`) | `rows` (array), `row_count` (number), `columns` (array) |
| `database.update` | Update data in database tables | `table` string *(required)*, `data` object *(required)*, `where` object *(required)*, `database_type` select (default: `postgresql`), `connection_string` string, `host` string, `port` number, `database` string, `user` string, `password` string | `updated_count` (number) |

## datetime

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `datetime.add` | Add time to datetime | `datetime` string (default: `now`), `days` number (default: `0`), `hours` number (default: `0`), `minutes` number (default: `0`), `seconds` number (default: `0`) | `result` (string), `timestamp` (number) |
| `datetime.format` | Format datetime to string | `datetime` string (default: `now`), `format` select (default: `%Y-%m-%d %H:%M:%S`) | `result` (string), `timestamp` (number) |
| `datetime.parse` | Parse string to datetime | `datetime_string` string *(required)*, `format` select (default: `%Y-%m-%d %H:%M:%S`) | `result` (string), `timestamp` (number), `year` (number), `month` (number), `day` (number), `hour` (number), `minute` (number), `second` (number) |
| `datetime.subtract` | Subtract time from datetime | `datetime` string (default: `now`), `days` number (default: `0`), `hours` number (default: `0`), `minutes` number (default: `0`), `seconds` number (default: `0`) | `result` (string), `timestamp` (number) |

## db

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `db.mongodb.find` | Query documents from MongoDB collection | `connection_string` string, `database` string *(required)*, `collection` string *(required)*, `filter` object (default: `{}`), `projection` object, `limit` number (default: `100`), `sort` object | `documents` (array), `count` (number) |
| `db.mongodb.insert` | Insert one or more documents into MongoDB collection | `connection_string` string, `database` string *(required)*, `collection` string *(required)*, `document` object, `documents` array | `inserted_count` (number), `inserted_ids` (array) |
| `db.mysql.query` | Execute a SQL query on MySQL database and return results | `host` string, `port` number (default: `3306`), `user` string, `password` string, `database` string, `query` string *(required)*, `params` array (default: `[]`) | `rows` (array), `row_count` (number), `columns` (array) |
| `db.postgresql.query` | Execute a SQL query on PostgreSQL database and return results | `connection_string` string, `query` string *(required)*, `params` array (default: `[]`) | `rows` (array), `row_count` (number), `columns` (array) |
| `db.redis.get` | Get a value from Redis cache | `key` string *(required)*, `host` string, `port` number (default: `6379`), `db` number (default: `0`) | `value` (any), `exists` (boolean), `key` (string) |
| `db.redis.set` | Set a value in Redis cache | `key` string *(required)*, `value` any *(required)*, `ttl` number, `host` string, `port` number (default: `6379`), `db` number (default: `0`) | `success` (boolean), `key` (string) |

## decode

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `decode.base64` | Decode Base64 encoded text | `text` text *(required)*, `encoding` string (default: `utf-8`), `url_safe` boolean (default: `False`) | `result` (string), `original` (string), `valid` (boolean) |
| `decode.hex` | Decode hexadecimal to text | `text` text *(required)*, `encoding` string (default: `utf-8`) | `result` (string), `original` (string), `valid` (boolean) |
| `decode.url` | Decode URL encoded text | `text` text *(required)*, `plus_spaces` boolean (default: `False`) | `result` (string), `original` (string) |

## dns

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `dns.lookup` | DNS lookup for domain records | `domain` string *(required)*, `record_type` select (default: `A`), `timeout` number (default: `10`) | `ok` (boolean), `data` (object) |

## docker

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `docker.build` | Build a Docker image from a Dockerfile | `path` string *(required)*, `tag` string *(required)*, `dockerfile` string, `build_args` object, `no_cache` boolean (default: `False`) | `image_id` (string), `tag` (string), `size` (string) |
| `docker.inspect_container` | Get detailed information about a Docker container | `container` string *(required)* | `id` (string), `name` (string), `state` (object), `image` (string), `network_settings` (object), `mounts` (array), `config` (object) |
| `docker.logs` | Get logs from a Docker container | `container` string *(required)*, `tail` number (default: `100`), `follow` boolean (default: `False`), `timestamps` boolean (default: `False`) | `logs` (string), `lines` (number) |
| `docker.ps` | List Docker containers | `all` boolean (default: `False`), `filters` object | `containers` (array), `count` (number) |
| `docker.run` | Run a Docker container from an image | `image` string *(required)*, `command` string, `name` string, `ports` object, `volumes` object, `env` object, `detach` boolean (default: `True`), `remove` boolean (default: `False`), `network` string | `container_id` (string), `status` (string) |
| `docker.stop` | Stop a running Docker container | `container` string *(required)*, `timeout` number (default: `10`) | `container_id` (string), `stopped` (boolean) |

## element

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `element.attribute` | Get element's attribute value | `element_id` string *(required)*, `name` string *(required)* | `status` (string), `value` (string) |
| `element.query` | Find child elements within element | `element_id` string *(required)*, `selector` string *(required)*, `all` boolean (default: `False`) | `status` (string), `element_id` (string), `element_ids` (array), `count` (number) |
| `element.text` | Get element's text content | `element_id` string *(required)* | `status` (string), `text` (string) |

## email

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `email.read` | Read emails from IMAP server | `folder` string (default: `INBOX`), `limit` number (default: `10`), `unread_only` boolean (default: `False`), `since_date` string, `from_filter` string, `subject_filter` string, `imap_host` string, `imap_port` number (default: `993`), `imap_user` string, `imap_password` string | `emails` (array), `count` (number) |
| `email.send` | Send email via SMTP server | `to` string *(required)*, `subject` string *(required)*, `body` string *(required)*, `html` boolean (default: `False`), `from_email` string, `cc` string, `bcc` string, `attachments` array (default: `[]`), `smtp_host` string, `smtp_port` number (default: `587`), `smtp_user` string, `smtp_password` string, `use_tls` boolean (default: `True`) | `sent` (boolean), `message_id` (string), `recipients` (array) |

## encode

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `encode.base64` | Encode text to Base64 | `text` text *(required)*, `encoding` string (default: `utf-8`), `url_safe` boolean (default: `False`) | `result` (string), `original` (string), `length` (number) |
| `encode.hex` | Encode text to hexadecimal | `text` text *(required)*, `encoding` string (default: `utf-8`), `uppercase` boolean (default: `False`), `separator` string (default: ``) | `result` (string), `original` (string), `byte_count` (number) |
| `encode.html` | Encode text to HTML entities | `text` text *(required)*, `quote` boolean (default: `True`) | `result` (string), `original` (string) |
| `encode.url` | URL encode text (percent encoding) | `text` text *(required)*, `plus_spaces` boolean (default: `False`), `safe` string (default: ``) | `result` (string), `original` (string) |

## env

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `env.get` | Get the value of an environment variable | `name` string *(required)*, `default` string | `name` (string), `value` (string), `exists` (boolean) |
| `env.load_dotenv` | Load environment variables from a .env file | `path` string *(required)*, `override` boolean (default: `False`) | `loaded_count` (number), `variables` (array) |
| `env.set` | Set an environment variable in the current process | `name` string *(required)*, `value` string *(required)* | `name` (string), `value` (string), `previous_value` (string) |

## error

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `error.circuit_breaker` | Protect against cascading failures with circuit breaker pattern | `action` object *(required)*, `circuit_id` string *(required)*, `failure_threshold` number (default: `5`), `failure_window_ms` number (default: `60000`), `recovery_timeout_ms` number (default: `30000`), `success_threshold` number (default: `3`), `fallback` object, `fallback_value` any, `track_errors` array (default: `[]`) | `__event__` (string), `result` (any), `circuit_state` (string), `failure_count` (number), `last_failure_time` (string), `circuit_opened_at` (string) |
| `error.fallback` | Provide fallback value when operation fails | `operation` object, `fallback_value` any, `fallback_operation` object, `fallback_on` array (default: `[]`), `include_error_info` boolean (default: `True`), `log_fallback` boolean (default: `True`) | `result` (any), `used_fallback` (boolean), `source` (string), `original_error` (object) |
| `error.retry` | Wrap operations with configurable retry logic | `operation` object *(required)*, `max_retries` number (default: `3`), `initial_delay_ms` number (default: `1000`), `max_delay_ms` number (default: `30000`), `backoff_multiplier` number (default: `2.0`), `jitter` boolean (default: `True`), `retry_on` array (default: `[]`), `timeout_per_attempt_ms` number (default: `0`) | `__event__` (string), `result` (any), `attempts` (number), `total_delay_ms` (number), `errors` (array) |

## excel

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `excel.read` | Read data from Excel files (xlsx, xls) | `path` string *(required)*, `sheet` string, `header_row` number (default: `1`), `range` string, `as_dict` boolean (default: `True`) | `data` (array), `headers` (array), `row_count` (number), `sheet_names` (array) |
| `excel.write` | Write data to Excel files (xlsx) | `path` string *(required)*, `data` array *(required)*, `headers` array, `sheet_name` string (default: `Sheet1`), `auto_width` boolean (default: `True`) | `path` (string), `row_count` (number), `size` (number) |

## file

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `file.copy` | Copy a file to another location | `source` string *(required)*, `destination` string *(required)*, `overwrite` boolean (default: `False`) | `copied` (boolean), `source` (string), `destination` (string), `size` (number) |
| `file.delete` | Delete a file from the filesystem | `path` string *(required)*, `ignore_missing` boolean (default: `False`) | `deleted` (boolean), `file_path` (string) |
| `file.diff` | Generate unified diff between original and modified content | `original` string *(required)*, `modified` string *(required)*, `context_lines` number (default: `3`), `filename` string (default: `file`) | `diff` (string), `changed` (boolean), `additions` (number), `deletions` (number) |
| `file.edit` | Replace a string in a file (targeted edit, not full overwrite) | `path` string *(required)*, `old_string` string *(required)*, `new_string` string *(required)*, `replace_all` boolean (default: `False`), `encoding` select (default: `utf-8`) | `path` (string), `replacements` (number), `diff` (string) |
| `file.exists` | Check if a file or directory exists | `path` string *(required)* | `exists` (boolean), `is_file` (boolean), `is_directory` (boolean) |
| `file.move` | Move or rename a file | `source` string *(required)*, `destination` string *(required)* | `moved` (boolean), `source` (string), `destination` (string) |
| `file.read` | Read content from a file | `path` string *(required)*, `encoding` select (default: `utf-8`) | `content` (string), `size` (number) |
| `file.write` | Write content to a file | `path` string *(required)*, `content` string *(required)*, `encoding` select (default: `utf-8`), `mode` select (default: `overwrite`) | `path` (string), `bytes_written` (number) |

## flow

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `flow.batch` | Process items in batches with configurable size | `items` array *(required)*, `batch_size` number *(required)*, `delay_ms` number (default: `0`), `continue_on_error` boolean (default: `False`), `parallel_batches` number (default: `1`) | `__event__` (string), `batch` (array), `batch_index` (number), `total_batches` (number), `total_items` (number), `is_last_batch` (boolean), `progress` (object) |
| `flow.branch` | Conditional branching based on expression evaluation | `condition` string *(required)* | `__event__` (string), `outputs` (object), `result` (boolean), `condition` (string), `resolved_condition` (string) |
| `flow.breakpoint` | Pause workflow execution for human approval or input | `title` string (default: `Approval Required`), `description` string, `timeout_seconds` number (default: `0`), `required_approvers` array *(required)*, `approval_mode` select (default: `single`), `custom_fields` array *(required)*, `include_context` boolean (default: `True`), `auto_approve_condition` string | `__event__` (string), `breakpoint_id` (string), `status` (string), `approved_by` (array), `rejected_by` (array), `custom_inputs` (object), `comments` (array), `resolved_at` (string), `wait_duration_ms` (integer) |
| `flow.circuit_breaker` | Circuit breaker pattern for fault tolerance | `failure_threshold` number *(required)*, `reset_timeout_ms` number (default: `60000`), `half_open_max` number (default: `1`) | `__event__` (string), `state` (string), `failure_count` (number), `last_failure_time_ms` (number), `time_until_half_open_ms` (number) |
| `flow.container` | Embedded subflow container for organizing complex workflows | `subflow` object (default: `{'nodes': [], 'edges': []}`), `inherit_context` boolean (default: `True`), `isolated_variables` array *(required)*, `export_variables` array *(required)* | `__event__` (string), `outputs` (object), `subflow_result` (object), `exported_variables` (object), `node_count` (integer), `execution_time_ms` (number) |
| `flow.debounce` | Debounce execution to prevent rapid repeated calls | `delay_ms` number *(required)*, `leading` boolean (default: `False`), `trailing` boolean (default: `True`) | `__event__` (string), `last_call_ms` (number), `calls_debounced` (number), `time_since_last_ms` (number), `edge` (string) |
| `flow.end` | Explicit workflow end node | `output_mapping` object (default: `{}`), `success_message` string | `__event__` (string), `ended_at` (string), `workflow_result` (object) |
| `flow.error_handle` | Catches and handles errors from upstream nodes | `action` string *(required)*, `include_traceback` boolean (default: `True`), `error_code_mapping` object (default: `{}`), `fallback_value` any | `__event__` (string), `outputs` (object), `error_info` (object), `action_taken` (string) |
| `flow.error_workflow_trigger` | Entry point for error workflows - triggered when another workflow fails | `description` string (default: ``) | `__event__` (string), `error_context` (object), `triggered_at` (string) |
| `flow.foreach` | Iterate over a list and execute steps for each item | `items` string *(required)*, `steps` array, `item_var` string (default: `item`), `index_var` string (default: `index`), `output_mode` string (default: `collect`) | `__event__` (string), `__set_context` (object), `outputs` (object), `iteration` (number), `status` (string), `results` (array), `count` (number) |
| `flow.fork` | Split execution into parallel branches | `branch_count` number (default: `2`) | `__event__` (string), `input_data` (any), `branch_count` (integer) |
| `flow.goto` | Unconditional jump to another step | `target` string *(required)*, `max_iterations` number (default: `100`) | `__event__` (string), `target` (string), `iteration` (number) |
| `flow.invoke` | Execute an external workflow file | `workflow_source` string *(required)*, `workflow_params` object *(required)*, `timeout_seconds` number (default: `300`), `output_mapping` object (default: `{}`) | `__event__` (string), `result` (any), `workflow_id` (string), `execution_time_ms` (number) |
| `flow.join` | Wait for parallel branches to complete | `strategy` select (default: `all`), `input_count` number (default: `2`), `timeout` number (default: `60000`), `cancel_pending` boolean (default: `True`) | `__event__` (string), `joined_data` (array), `completed_count` (integer), `strategy` (string) |
| `flow.loop` | Repeat steps N times using output port routing | `times` number *(required)*, `target` string, `steps` array, `index_var` string (default: `index`) | `__event__` (string), `outputs` (object), `iteration` (number), `status` (string), `results` (array), `count` (number) |
| `flow.merge` | Merge multiple inputs into a single output | `strategy` select (default: `all`), `input_count` number (default: `2`) | `__event__` (string), `merged_data` (any), `input_count` (integer), `strategy` (string) |
| `flow.parallel` | Execute multiple tasks in parallel with different strategies | `tasks` array *(required)*, `mode` string (default: `all`), `timeout_ms` number (default: `60000`), `fail_fast` boolean (default: `True`), `concurrency_limit` number (default: `0`) | `__event__` (string), `results` (array), `completed_count` (number), `failed_count` (number), `total_count` (number), `mode` (string), `duration_ms` (number) |
| `flow.rate_limit` | Rate limiter with token bucket strategy | `max_requests` number *(required)*, `window_ms` number (default: `60000`), `strategy` string (default: `token_bucket`), `queue_overflow` string (default: `wait`) | `__event__` (string), `tokens_remaining` (number), `window_reset_ms` (number), `requests_in_window` (number), `wait_ms` (number) |
| `flow.retry` | Retry with exponential backoff | `max_retries` number *(required)*, `initial_delay_ms` number (default: `1000`), `backoff_multiplier` number (default: `2.0`), `max_delay_ms` number (default: `30000`), `retry_on_errors` array (default: `[]`) | `__event__` (string), `attempt` (number), `max_retries` (number), `delay_ms` (number), `total_elapsed_ms` (number), `last_error` (object) |
| `flow.start` | Explicit workflow start node | — | `__event__` (string), `started_at` (string), `workflow_id` (string) |
| `flow.subflow` | Reference and execute an external workflow | `workflow_ref` string *(required)*, `execution_mode` select (default: `inline`), `input_mapping` object *(required)*, `output_mapping` object (default: `{}`), `timeout` number (default: `300000`) | `__event__` (string), `result` (any), `execution_id` (string), `workflow_ref` (string) |
| `flow.switch` | Multi-way branching based on value matching | `expression` string *(required)*, `cases` array *(required)* | `__event__` (string), `outputs` (object), `matched_case` (string), `value` (any) |
| `flow.throttle` | Throttle execution rate with minimum interval | `interval_ms` number *(required)*, `leading` boolean (default: `True`) | `__event__` (string), `last_execution_ms` (number), `calls_throttled` (number), `time_since_last_ms` (number), `remaining_ms` (number) |
| `flow.trigger` | Workflow entry point - manual, webhook, schedule, event, mcp, or polling | `trigger_type` select (default: `manual`), `webhook_path` string, `schedule` string, `event_name` string, `tool_name` string, `tool_description` string, `poll_url` string, `poll_interval` number (default: `300`), `poll_method` select (default: `GET`), `poll_headers` object (default: `{}`), `poll_body` object (default: `{}`), `dedup_key` string, `config` object, `description` string | `__event__` (string), `trigger_data` (object), `trigger_type` (string), `triggered_at` (string) |

## format

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `format.currency` | Format numbers as currency | `amount` number *(required)*, `currency` string (default: `USD`), `decimal_places` number (default: `2`), `symbol_position` string (default: `before`) | `result` (string), `original` (number), `symbol` (string) |
| `format.duration` | Format seconds as human-readable duration | `seconds` number *(required)*, `format` string (default: `short`), `show_zero` boolean (default: `False`) | `result` (string), `original` (number), `parts` (object) |
| `format.filesize` | Format bytes as human-readable file size | `bytes` number *(required)*, `binary` boolean (default: `False`), `decimal_places` number (default: `2`) | `result` (string), `original` (number), `unit` (string), `value` (number) |
| `format.number` | Format numbers with separators and decimals | `number` number *(required)*, `decimal_places` number (default: `2`), `thousand_separator` string (default: `,`), `decimal_separator` string (default: `.`) | `result` (string), `original` (number) |
| `format.percentage` | Format numbers as percentages | `value` number *(required)*, `is_ratio` boolean (default: `True`), `decimal_places` number (default: `1`), `include_sign` boolean (default: `False`) | `result` (string), `original` (number), `numeric` (number) |

## git

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `git.clone` | Clone a git repository | `url` string *(required)*, `destination` string *(required)*, `branch` string, `depth` number, `token` string | `ok` (boolean), `data` (object) |
| `git.commit` | Create a git commit | `repo_path` string *(required)*, `message` string *(required)*, `add_all` boolean (default: `False`), `files` array, `author_name` string, `author_email` string | `ok` (boolean), `data` (object) |
| `git.diff` | Get git diff | `repo_path` string *(required)*, `ref1` string (default: `HEAD`), `ref2` string, `staged` boolean (default: `False`), `stat_only` boolean (default: `False`) | `ok` (boolean), `data` (object) |

## google

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `google.calendar.create_event` | Create a new event in Google Calendar | `access_token` string *(required)*, `summary` string *(required)*, `start_time` string *(required)*, `end_time` string *(required)*, `description` string, `location` string, `attendees` string, `timezone` string (default: `UTC`) | `event_id` (string), `summary` (string), `start` (string), `end` (string), `html_link` (string) |
| `google.calendar.list_events` | List upcoming events from Google Calendar | `access_token` string *(required)*, `max_results` number (default: `10`), `time_min` string, `time_max` string | `events` (array), `count` (number) |
| `google.gmail.search` | Search Gmail messages using Gmail search query syntax | `access_token` string *(required)*, `query` string *(required)*, `max_results` number (default: `10`) | `messages` (array), `total` (number) |
| `google.gmail.send` | Send an email via the Gmail API | `access_token` string *(required)*, `to` string *(required)*, `subject` string *(required)*, `body` string *(required)*, `html` boolean (default: `False`), `cc` string, `bcc` string | `message_id` (string), `thread_id` (string), `to` (string) |

## graphql

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `graphql.mutation` | Execute a GraphQL mutation against an endpoint | `url` string *(required)*, `mutation` string *(required)*, `variables` object, `headers` object, `auth_token` string | `data` (object), `errors` (array), `status_code` (number) |
| `graphql.query` | Execute a GraphQL query against an endpoint | `url` string *(required)*, `query` string *(required)*, `variables` object, `headers` object, `auth_token` string | `data` (object), `errors` (array), `status_code` (number) |

## hash

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `hash.sha256` | Calculate SHA-256 cryptographic hash of text | `text` string *(required)*, `encoding` string (default: `utf-8`) | `hash` (string), `algorithm` (string) |
| `hash.sha512` | Calculate SHA-512 cryptographic hash of text | `text` string *(required)*, `encoding` string (default: `utf-8`) | `hash` (string), `algorithm` (string) |

## http

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `http.batch` | Run a batch of HTTP probes sequentially and capture timing + body | `requests` array *(required)*, `description` string, `measure_time` boolean (default: `False`), `timeout` number (default: `30`), `verify_ssl` boolean (default: `True`), `ssrf_protection` boolean (default: `True`), `detect_patterns` array | `ok` (boolean), `data` (array), `count` (number), `failed_count` (number), `total_duration_ms` (number), `detected` (array) |
| `http.get` | Send HTTP GET request to an API endpoint | `url` string *(required)*, `headers` object (default: `{}`), `query` object (default: `{}`), `timeout` number (default: `30`), `verify_ssl` boolean (default: `True`), `ssrf_protection` boolean (default: `True`) | `ok` (boolean), `status` (number), `body` (any), `headers` (object) |
| `http.paginate` | Automatically iterate through paginated API endpoints and collect all results | `url` string *(required)*, `method` select (default: `GET`), `headers` object (default: `{}`), `auth` object, `strategy` string (default: `offset`), `data_path` string (default: ``), `offset_param` string (default: `offset`), `limit_param` string (default: `limit`), `page_size` number (default: `100`), `page_param` string (default: `page`), `start_page` number (default: `1`), `cursor_param` string (default: `cursor`), `cursor_path` string (default: ``), `max_pages` number (default: `50`), `delay_ms` number (default: `0`), `timeout` number (default: `30`), `verify_ssl` boolean (default: `True`), `ssrf_protection` boolean (default: `True`) | `ok` (boolean), `items` (array), `total_items` (number), `pages_fetched` (number), `duration_ms` (number) |
| `http.request` | Send HTTP request and receive response | `url` string *(required)*, `method` select (default: `GET`), `headers` object (default: `{}`), `body` any, `query` object (default: `{}`), `content_type` select (default: `application/json`), `auth` object, `timeout` number (default: `30`), `follow_redirects` boolean (default: `True`), `verify_ssl` boolean (default: `True`), `response_type` select (default: `auto`), `retry_count` number (default: `0`), `retry_backoff` string (default: `exponential`), `retry_delay` number (default: `1`), `ssrf_protection` boolean (default: `True`) | `ok` (boolean), `status` (number), `status_text` (string), `headers` (object), `body` (any), `url` (string), `duration_ms` (number), `content_type` (string), `content_length` (number) |
| `http.response_assert` | Assert and validate HTTP response properties | `response` object *(required)*, `status` any, `body_contains` any, `body_not_contains` any, `body_matches` string *(required)*, `json_path` object, `json_path_exists` array, `header_contains` object, `content_type` select (default: ``), `max_duration_ms` number, `schema` object, `fail_fast` boolean (default: `False`) | `ok` (boolean), `passed` (number), `failed` (number), `total` (number), `assertions` (array), `errors` (array) |
| `http.session` | Send a sequence of HTTP requests with persistent cookies (login → action → logout) | `requests` array *(required)*, `auth` object, `stop_on_error` boolean (default: `True`), `timeout` number (default: `30`), `verify_ssl` boolean (default: `True`), `ssrf_protection` boolean (default: `True`) | `ok` (boolean), `results` (array), `cookies` (object), `duration_ms` (number) |
| `http.webhook_wait` | Start a temporary server and wait for an incoming webhook callback | `path` string (default: `/webhook`), `port` number (default: `0`), `timeout` number (default: `300`), `use_ngrok` boolean (default: `False`), `ngrok_token` string, `expected_method` string (default: `POST`), `response_status` number (default: `200`), `response_body` string (default: `{"ok": true}`) | `ok` (boolean), `webhook_url` (string), `method` (string), `headers` (object), `body` (any), `query` (object), `duration_ms` (number) |

## image

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `image.compress` | Compress images to reduce file size while maintaining quality | `input_path` string *(required)*, `output_path` string, `quality` number (default: `85`), `optimize` boolean (default: `True`), `max_size_kb` number, `format` select (default: `png`) | `output_path` (string), `original_size_bytes` (number), `compressed_size_bytes` (number), `compression_ratio` (number) |
| `image.convert` | Convert image to different format (PNG, JPEG, WEBP, etc.) | `input_path` string *(required)*, `output_path` string, `format` select *(required)*, `quality` number (default: `85`), `resize` object | `path` (string), `size` (number), `format` (string), `dimensions` (object) |
| `image.crop` | Crop image to specified region | `input_path` string *(required)*, `output_path` string *(required)*, `left` number *(required)*, `top` number *(required)*, `right` number *(required)*, `bottom` number *(required)* | `output_path` (string), `width` (integer), `height` (integer), `original_width` (integer), `original_height` (integer) |
| `image.download` | Download image from URL to local file | `url` string *(required)*, `output_path` string, `output_dir` string (default: `/tmp`), `headers` object (default: `{}`), `timeout` number (default: `30`) | `path` (string), `size` (number), `content_type` (string), `filename` (string) |
| `image.ocr` | Extract text from images using Tesseract OCR | `image_path` string *(required)*, `language` string (default: `eng`), `psm` number (default: `3`), `output_type` select (default: `text`) | `text` (string), `confidence` (number), `language` (string) |
| `image.qrcode_generate` | Generate QR codes from text, URLs, or data | `data` string *(required)*, `output_path` string, `format` select (default: `png`), `size` number (default: `300`), `color` string (default: `#000000`), `background` string (default: `#FFFFFF`), `error_correction` select (default: `M`), `border` number (default: `4`), `version` number, `logo_path` string | `output_path` (string), `file_size` (number), `dimensions` (object) |
| `image.resize` | Resize images to specified dimensions with various algorithms | `input_path` string *(required)*, `output_path` string, `width` number, `height` number, `scale` number, `algorithm` select (default: `lanczos`), `maintain_aspect` boolean (default: `True`) | `output_path` (string), `original_size` (object), `new_size` (object) |
| `image.rotate` | Rotate image by specified angle | `input_path` string *(required)*, `output_path` string *(required)*, `angle` number *(required)*, `expand` boolean (default: `True`), `fill_color` string (default: `#000000`) | `output_path` (string), `width` (integer), `height` (integer), `angle` (number) |
| `image.watermark` | Add text or image watermark to images | `input_path` string *(required)*, `output_path` string *(required)*, `text` string, `watermark_image` string, `position` select (default: `bottom-right`), `opacity` number (default: `0.5`), `font_size` number (default: `36`) | `output_path` (string), `watermark_type` (string) |

## k8s

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `k8s.apply` | Apply a Kubernetes manifest via kubectl apply | `manifest` string *(required)*, `namespace` string, `kubeconfig` string | `kind` (string), `name` (string), `namespace` (string), `action` (string) |
| `k8s.describe` | Describe a Kubernetes resource in detail | `resource_type` string *(required)*, `name` string *(required)*, `namespace` string (default: `default`), `kubeconfig` string | `resource_type` (string), `name` (string), `namespace` (string), `description` (string) |
| `k8s.get_pods` | List Kubernetes pods in a namespace | `namespace` string (default: `default`), `label_selector` string, `kubeconfig` string | `pods` (array), `count` (number) |
| `k8s.logs` | Retrieve logs from a Kubernetes pod | `pod` string *(required)*, `namespace` string (default: `default`), `container` string, `tail` number (default: `100`), `previous` boolean (default: `False`), `kubeconfig` string | `pod` (string), `logs` (string), `lines` (number) |
| `k8s.scale` | Scale a Kubernetes deployment to a specified replica count | `deployment` string *(required)*, `replicas` number *(required)*, `namespace` string (default: `default`), `kubeconfig` string | `deployment` (string), `replicas` (number), `namespace` (string), `scaled` (boolean) |

## llm

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `llm.agent` | Autonomous AI agent with multi-port connections (model, memory, tools) | `prompt_source` select (default: `manual`), `task` string, `prompt_path` string (default: `{{input}}`), `join_strategy` select (default: `first`), `join_separator` string (default: `\n\n---\n\n`), `max_input_size` number (default: `10000`), `agent_type` select (default: `tools`), `system_prompt` string (default: `You are a helpful AI agent....`), `response_format` select (default: `text`), `output_schema` object (default: `{}`), `context` object (default: `{}`), `max_iterations` number (default: `10`), `provider` select (default: `openai`), `model` string (default: `gpt-4o`), `api_key` string, `temperature` number (default: `0.7`), `base_url` string | `ok` (boolean), `result` (string), `steps` (array), `tool_calls` (number), `tokens_used` (number) |
| `llm.chat` | Interact with LLM APIs for intelligent operations | `prompt` string *(required)*, `system_prompt` string, `context` object, `messages` array, `provider` select (default: `openai`), `model` string (default: `gpt-4o`), `temperature` number (default: `0.7`), `max_tokens` number (default: `2000`), `response_format` select (default: `text`), `api_key` string, `base_url` string | `ok` (boolean), `response` (string), `parsed` (any), `model` (string), `tokens_used` (number), `finish_reason` (string) |
| `llm.code_fix` | Automatically generate code fixes based on issues | `issues` array *(required)*, `source_files` array *(required)*, `fix_mode` select (default: `suggest`), `backup` boolean (default: `True`), `context` string, `model` string (default: `gpt-4o`), `api_key` string | `ok` (boolean), `fixes` (array), `applied` (array), `failed` (array), `summary` (string) |

## logic

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `logic.and` | Perform logical AND operation | `values` array *(required)* | `result` (boolean), `true_count` (number), `total_count` (number) |
| `logic.contains` | Check if a value contains another value | `haystack` text *(required)*, `needle` text *(required)*, `case_sensitive` boolean (default: `True`) | `result` (boolean), `position` (number), `count` (number) |
| `logic.equals` | Check if two values are equal | `a` text *(required)*, `b` text *(required)*, `strict` boolean (default: `False`), `case_sensitive` boolean (default: `True`) | `result` (boolean), `type_a` (string), `type_b` (string) |
| `logic.not` | Perform logical NOT operation | `value` boolean *(required)* | `result` (boolean), `original` (boolean) |
| `logic.or` | Perform logical OR operation | `values` array *(required)* | `result` (boolean), `true_count` (number), `total_count` (number) |

## markdown

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `markdown.parse_frontmatter` | Extract YAML frontmatter from Markdown content | `text` string *(required)* | `frontmatter` (object), `content` (string) |
| `markdown.to_html` | Convert Markdown text to HTML | `text` string *(required)*, `extensions` array | `html` (string), `word_count` (number) |
| `markdown.toc` | Generate a table of contents from Markdown headings | `text` string *(required)*, `max_depth` number (default: `3`) | `toc` (array), `toc_markdown` (string) |

## math

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `math.abs` | Get absolute value of a number | `number` number *(required)* | `result` (number), `original` (number) |
| `math.calculate` | Perform basic mathematical operations | `operation` select *(required)*, `a` number *(required)*, `b` number, `precision` number (default: `2`) | `result` (number), `operation` (string), `expression` (string) |
| `math.ceil` | Round number up to nearest integer | `number` number *(required)* | `result` (number), `original` (number) |
| `math.floor` | Round number down to nearest integer | `number` number *(required)* | `result` (number), `original` (number) |
| `math.power` | Raise number to a power | `base` number *(required)*, `exponent` number *(required)* | `result` (number), `base` (number), `exponent` (number) |
| `math.round` | Round number to specified decimal places | `number` number *(required)*, `decimals` number (default: `0`) | `result` (number), `original` (number), `decimals` (number) |

## mcp

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `mcp.recipe` | Run an approved MCP recipe contract and emit redacted execution evidence | `recipe_id` string *(required)*, `scenario_id` string *(required)*, `default_args` object (default: `{}`), `runtime_required_args` array (default: `[]`) | `ok` (boolean), `recipe_ok` (boolean), `recipe_id` (string), `scenario_id` (string), `status` (string), `runtime_args_present` (array), `runtime_args_missing` (array), `evidence` (object) |

## meta

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `meta.modules.generate` | Generate new module from specification | — | `status` (string), `message` (string), `module_id` (string), `description` (string) |
| `meta.modules.list` | List all available modules in the registry | `category` string, `tags` array, `include_params` boolean (default: `True`), `include_output` boolean (default: `True`), `format` select (default: `json`) | `modules` (array), `count` (number), `formatted` (string) |
| `meta.modules.test_generator` | Test module generation capability | — | `status` (string), `message` (string), `spec_received` (boolean) |
| `meta.modules.update_docs` | Generate or update MODULES.md documentation from registry | `output_path` string (default: `docs/MODULES.md`), `include_examples` boolean (default: `True`) | `file_path` (string), `modules_count` (number), `categories` (array) |

## monitor

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `monitor.http_check` | HTTP health check / uptime monitor | `url` string *(required)*, `method` select (default: `GET`), `expected_status` number (default: `200`), `timeout_ms` number (default: `10000`), `headers` object, `body` string, `check_ssl` boolean (default: `True`), `contains` string, `follow_redirects` boolean (default: `True`) | `ok` (boolean), `data` (object) |

## network

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `network.ping` | Ping a host to check connectivity and measure latency | `host` string *(required)*, `count` number (default: `4`), `timeout` number (default: `5`) | `host` (string), `alive` (boolean), `packets_sent` (number), `packets_received` (number), `packet_loss_pct` (number), `latency_ms` (object) |
| `network.port_scan` | Scan ports on a host to check which are open | `host` string *(required)*, `ports` string, `timeout` number (default: `1.0`) | `host` (string), `open_ports` (array), `closed_ports` (array), `scan_time_ms` (number) |
| `network.traceroute` | Trace the route packets take to reach a destination host | `host` string *(required)*, `max_hops` number (default: `30`), `timeout` number (default: `5`) | `host` (string), `hops` (array), `total_hops` (number) |
| `network.whois` | Perform WHOIS lookup for a domain to retrieve registration information | `domain` string *(required)* | `domain` (string), `registrar` (string), `creation_date` (string), `expiration_date` (string), `name_servers` (array), `raw` (string) |

## notification

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `notification.discord.send_message` | Send message to Discord via webhook | `webhook_url` string, `content` string *(required)*, `username` string, `avatar_url` string | `status` (string), `sent` (boolean), `message` (string) |
| `notification.email.send` | Send email via SMTP | `smtp_server` string *(required)*, `smtp_port` number (default: `587`), `username` string *(required)*, `password` string *(required)*, `from_email` string *(required)*, `to_email` string *(required)*, `subject` string *(required)*, `body` text *(required)*, `html` boolean (default: `False`) | `status` (string), `sent` (boolean), `message` (string) |
| `notification.slack.send_message` | Send message to Slack via webhook | `webhook_url` string, `text` string *(required)*, `channel` string, `username` string, `icon_emoji` string | `status` (string), `sent` (boolean), `message` (string) |
| `notification.teams.send_message` | Send message to Microsoft Teams via incoming webhook | `webhook_url` string *(required)*, `message` text *(required)*, `title` string, `color` string, `sections` array | `ok` (boolean), `data` (object) |
| `notification.telegram.send_message` | Send message via Telegram Bot API | `bot_token` string, `chat_id` string *(required)*, `text` string *(required)*, `parse_mode` select (default: `Markdown`) | `status` (string), `sent` (boolean), `message_id` (number), `message` (string) |
| `notification.whatsapp.send_message` | Send message via WhatsApp Business API (Meta Cloud API) | `phone_number_id` string *(required)*, `to` string *(required)*, `message` text *(required)*, `access_token` password *(required)*, `message_type` select (default: `text`), `template_name` string, `template_language` string (default: `en`) | `ok` (boolean), `data` (object) |

## notify

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `notify.send` | Send notification to Telegram, Discord, Slack, LINE, or any webhook URL | `url` string *(required)*, `message` string *(required)*, `title` string, `chat_id` string | `ok` (boolean), `platform` (string), `status_code` (number), `response` (object) |

## object

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `object.deep_merge` | Deep merge multiple objects | `objects` array *(required)*, `array_merge` string (default: `replace`) | `result` (object) |
| `object.flatten` | Flatten nested object to single level | `object` object *(required)*, `separator` string (default: `.`), `max_depth` number (default: `0`) | `result` (object), `keys` (array) |
| `object.get` | Get value from object by path | `object` object *(required)*, `path` string *(required)*, `default` any | `value` (any), `found` (boolean) |
| `object.keys` | Get all keys from an object | `object` object *(required)* | `keys` (array), `count` (number) |
| `object.merge` | Merge multiple objects into one | `objects` array *(required)* | `result` (object) |
| `object.omit` | Omit specific keys from an object | `object` object *(required)*, `keys` array *(required)* | `result` (object) |
| `object.pick` | Pick specific keys from an object | `object` object *(required)*, `keys` array *(required)* | `result` (object) |
| `object.set` | Set value in object by path | `object` object *(required)*, `path` string *(required)*, `value` any *(required)* | `result` (object) |
| `object.unflatten` | Unflatten object with dot notation to nested | `object` object *(required)*, `separator` string (default: `.`) | `result` (object) |
| `object.values` | Get all values from an object | `object` object *(required)* | `values` (array), `count` (number) |

## output

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `output.display` | Universal inspect/display/IO node — debug data, render output, or define workflow I/O | `type` select (default: `auto`), `content` string *(required)*, `title` string, `mode` select (default: `display`), `output_key` string (default: `result`) | `type` (string), `title` (string), `content` (['string', 'object', 'array']), `mode` (string), `validation_warning` (string) |

## path

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `path.basename` | Get file name from path | `path` string *(required)*, `remove_extension` boolean (default: `False`) | `result` (string), `original` (string), `extension` (string) |
| `path.dirname` | Get directory name from path | `path` string *(required)* | `result` (string), `original` (string) |
| `path.extension` | Get file extension from path | `path` string *(required)*, `include_dot` boolean (default: `True`) | `result` (string), `original` (string), `has_extension` (boolean) |
| `path.is_absolute` | Check if path is absolute | `path` string *(required)* | `result` (boolean), `path` (string), `absolute` (string) |
| `path.join` | Join path components | `parts` array *(required)* | `result` (string), `parts` (array) |
| `path.normalize` | Normalize a file path | `path` string *(required)*, `resolve` boolean (default: `False`) | `result` (string), `original` (string), `is_absolute` (boolean) |

## payment

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `payment.stripe.create_payment` | Create a payment intent with Stripe | `api_key` string, `amount` number *(required)*, `currency` string (default: `usd`), `description` string, `customer` string | `id` (string), `amount` (number), `currency` (string), `status` (string), `client_secret` (string) |
| `payment.stripe.get_customer` | Retrieve customer information from Stripe | `api_key` string, `customer_id` string *(required)* | `id` (string), `email` (string), `name` (string), `created` (number), `balance` (number) |
| `payment.stripe.list_charges` | List recent charges from Stripe | `api_key` string, `limit` number (default: `10`), `customer` string | `charges` (array), `count` (number), `has_more` (boolean) |

## pdf

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `pdf.fill_form` | Fill PDF form fields with data and optionally insert images | `template` string *(required)*, `output` string *(required)*, `fields` object (default: `{}`), `images` array (default: `[]`), `flatten` boolean (default: `True`) | `output_path` (string), `fields_filled` (number), `images_inserted` (number), `file_size_bytes` (number) |
| `pdf.generate` | Generate PDF files from HTML content or text | `content` string *(required)*, `output_path` string *(required)*, `title` string, `author` string, `page_size` select (default: `A4`), `orientation` select (default: `portrait`), `margin` number (default: `20`), `header` string, `footer` string | `output_path` (string), `page_count` (number), `file_size_bytes` (number) |
| `pdf.parse` | Extract text and metadata from PDF files | `path` string *(required)*, `pages` string (default: `all`), `extract_images` boolean (default: `False`), `extract_tables` boolean (default: `False`) | `text` (string), `pages` (array), `metadata` (object), `page_count` (number) |
| `pdf.to_word` | Convert PDF files to Word documents (.docx) | `input_path` string *(required)*, `output_path` string, `preserve_formatting` boolean (default: `True`), `pages` string (default: `all`) | `output_path` (string), `page_count` (number), `file_size` (number) |

## port

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `port.check` | Check if network port(s) are open or closed | `port` any *(required)*, `host` string (default: `localhost`), `connect_timeout` number (default: `2`), `expect_open` boolean | `ok` (boolean), `results` (array), `open_ports` (array), `closed_ports` (array), `summary` (object) |
| `port.wait` | Wait for a network port to become available | `port` number *(required)*, `host` string (default: `localhost`), `timeout` number (default: `60`), `interval` number (default: `500`), `expect_closed` boolean (default: `False`) | `ok` (boolean), `available` (boolean), `host` (string), `port` (number), `wait_time_ms` (number), `attempts` (number) |

## process

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `process.list` | List all running background processes | `filter_name` string, `include_status` boolean (default: `True`) | `ok` (boolean), `processes` (array), `count` (number), `running` (number), `stopped` (number) |
| `process.start` | Start a background process (server, service, etc.) | `command` string *(required)*, `cwd` string, `env` object, `name` string, `wait_for_output` string, `wait_timeout` number (default: `60`), `capture_output` boolean (default: `True`), `log_file` string, `auto_restart` boolean (default: `False`) | `ok` (boolean), `pid` (number), `process_id` (string), `name` (string), `command` (string), `cwd` (string), `started_at` (string), `initial_output` (string) |
| `process.stop` | Stop a running background process | `process_id` string, `name` string, `pid` number, `signal` select (default: `SIGTERM`), `timeout` number (default: `10`), `force` boolean (default: `False`), `stop_all` boolean (default: `False`) | `ok` (boolean), `stopped` (array), `failed` (array), `count` (number) |

## productivity

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `productivity.airtable.create` | Create a new record in Airtable table | `api_key` string, `base_id` string *(required)*, `table_name` string *(required)*, `fields` json *(required)* | `id` (string), `createdTime` (string), `fields` (json) |
| `productivity.airtable.read` | Read records from Airtable table | `api_key` string, `base_id` string *(required)*, `table_name` string *(required)*, `view` string, `max_records` number (default: `100`) | `records` (array), `count` (number) |
| `productivity.airtable.update` | Update an existing record in Airtable table | `api_key` string, `base_id` string *(required)*, `table_name` string *(required)*, `record_id` string *(required)*, `fields` json *(required)* | `id` (string), `fields` (json) |

## queue

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `queue.dequeue` | Remove and return an item from a queue | `queue_name` string *(required)*, `backend` string (default: `memory`), `redis_url` string (default: `redis://localhost:6379`), `timeout` number (default: `0`) | `data` (any), `queue_name` (string), `remaining` (number), `empty` (boolean) |
| `queue.enqueue` | Add an item to an in-memory or Redis queue | `queue_name` string *(required)*, `data` string *(required)*, `backend` string (default: `memory`), `redis_url` string (default: `redis://localhost:6379`) | `queue_name` (string), `position` (number), `queue_size` (number) |
| `queue.size` | Get the current size of a queue | `queue_name` string *(required)*, `backend` string (default: `memory`), `redis_url` string (default: `redis://localhost:6379`) | `queue_name` (string), `size` (number) |

## random

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `random.choice` | Select random element(s) from an array | `array` array *(required)*, `count` number (default: `1`), `unique` boolean (default: `True`) | `choice` (any), `count` (number) |
| `random.number` | Generate random number within a range | `min` number (default: `0`), `max` number (default: `100`), `integer` boolean (default: `True`), `precision` number (default: `2`) | `number` (number), `min` (number), `max` (number) |
| `random.shuffle` | Randomly shuffle array elements | `array` array *(required)* | `result` (array), `length` (number) |
| `random.uuid` | Generate random UUID (v4) | `uppercase` boolean (default: `False`), `remove_hyphens` boolean (default: `False`) | `uuid` (string), `version` (number) |

## regex

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `regex.extract` | Extract named groups from text | `text` string *(required)*, `pattern` string *(required)*, `ignore_case` boolean (default: `False`) | `extracted` (object), `matched` (boolean), `full_match` (string) |
| `regex.match` | Find all matches of a pattern in text | `text` string *(required)*, `pattern` string *(required)*, `ignore_case` boolean (default: `False`), `first_only` boolean (default: `False`) | `matches` (array), `count` (number), `groups` (array) |
| `regex.replace` | Replace pattern matches in text | `text` string *(required)*, `pattern` string *(required)*, `replacement` string *(required)*, `ignore_case` boolean (default: `False`), `count` number (default: `0`) | `result` (string), `replacements` (number), `original` (string) |
| `regex.split` | Split text by a regex pattern | `text` string *(required)*, `pattern` string *(required)*, `ignore_case` boolean (default: `False`), `max_split` number (default: `0`), `remove_empty` boolean (default: `False`) | `result` (array), `count` (number) |
| `regex.test` | Test if string matches a regex pattern | `text` string *(required)*, `pattern` string *(required)*, `ignore_case` boolean (default: `False`), `full_match` boolean (default: `False`) | `result` (boolean), `pattern` (string) |

## sandbox

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `sandbox.execute_js` | Execute JavaScript code via Node.js with timeout | `code` string *(required)*, `timeout` number (default: `10`) | `stdout` (string), `stderr` (string), `exit_code` (number), `execution_time_ms` (number) |
| `sandbox.execute_python` | Execute Python code in a subprocess with timeout | `code` string *(required)*, `timeout` number (default: `10`), `allowed_modules` array | `stdout` (string), `stderr` (string), `exit_code` (number), `execution_time_ms` (number) |
| `sandbox.execute_shell` | Execute a shell command with timeout and environment control | `command` string *(required)*, `timeout` number (default: `10`), `working_dir` string, `env` object | `stdout` (string), `stderr` (string), `exit_code` (number), `execution_time_ms` (number) |

## scheduler

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `scheduler.cron_parse` | Parse cron expression and calculate next N run times | `expression` string *(required)*, `count` number (default: `5`), `timezone` string (default: `0`) | `expression` (string), `description` (string), `next_runs` (array), `is_valid` (boolean) |
| `scheduler.delay` | Pause execution for a specified duration | `seconds` number *(required)*, `message` string | `delayed_seconds` (number), `message` (string) |
| `scheduler.interval` | Calculate interval timing and next occurrences | `seconds` number (default: `0`), `minutes` number (default: `0`), `hours` number (default: `0`), `start_time` string | `interval_seconds` (number), `next_runs` (array), `human_readable` (string) |

## set

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `set.difference` | Get elements in first array but not in others | `source` array *(required)*, `exclude` array *(required)* | `result` (array), `count` (number), `removed_count` (number) |
| `set.intersection` | Get intersection of two or more arrays | `arrays` array *(required)* | `result` (array), `count` (number) |
| `set.union` | Get union of two or more arrays | `arrays` array *(required)* | `result` (array), `count` (number) |
| `set.unique` | Remove duplicate elements from array | `array` array *(required)*, `preserve_order` boolean (default: `True`) | `result` (array), `count` (number), `duplicates_removed` (number) |

## shell

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `shell.exec` | Execute a shell command and capture output | `command` string *(required)*, `cwd` string, `env` object, `timeout` number (default: `300`), `shell` boolean (default: `False`), `capture_stderr` boolean (default: `True`), `encoding` select (default: `utf-8`), `raise_on_error` boolean (default: `False`) | `ok` (boolean), `exit_code` (number), `stdout` (string), `stderr` (string), `command` (string), `cwd` (string), `duration_ms` (number) |

## slack

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `slack.send` | Send messages to Slack channels via incoming webhook | `message` string *(required)*, `webhook_url` string, `channel` string, `username` string, `icon_emoji` string, `blocks` array, `attachments` array | `sent` (boolean) |

## ssh

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `ssh.exec` | Execute command on remote server via SSH | `host` string *(required)*, `port` number (default: `22`), `username` string *(required)*, `password` string, `private_key` string, `command` string *(required)*, `timeout` number (default: `30`) | `ok` (boolean), `data` (object) |
| `ssh.sftp_download` | Download file from remote server via SFTP | `host` string *(required)*, `port` number (default: `22`), `username` string *(required)*, `password` string, `private_key` string, `remote_path` string *(required)*, `local_path` string *(required)* | `ok` (boolean), `data` (object) |
| `ssh.sftp_upload` | Upload file to remote server via SFTP | `host` string *(required)*, `port` number (default: `22`), `username` string *(required)*, `password` string, `private_key` string, `local_path` string *(required)*, `remote_path` string *(required)*, `overwrite` boolean (default: `True`) | `ok` (boolean), `data` (object) |

## stats

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `stats.mean` | Calculate arithmetic mean of numbers | `numbers` array *(required)*, `precision` number (default: `2`) | `mean` (number), `count` (number), `sum` (number) |
| `stats.median` | Calculate median (middle value) of numbers | `numbers` array *(required)* | `median` (number), `count` (number) |
| `stats.min_max` | Find minimum and maximum values | `numbers` array *(required)* | `min` (number), `max` (number), `range` (number), `min_index` (number), `max_index` (number) |
| `stats.mode` | Calculate mode (most frequent value) | `values` array *(required)*, `all_modes` boolean (default: `False`) | `mode` (any), `frequency` (number), `count` (number) |
| `stats.percentile` | Calculate percentile of numbers | `numbers` array *(required)*, `percentile` number *(required)* | `value` (number), `percentile` (number) |
| `stats.std_dev` | Calculate standard deviation of numbers | `numbers` array *(required)*, `population` boolean (default: `False`), `precision` number (default: `4`) | `std_dev` (number), `variance` (number), `mean` (number) |
| `stats.sum` | Calculate sum of numbers | `numbers` array *(required)* | `sum` (number), `count` (number) |
| `stats.variance` | Calculate variance of numbers | `numbers` array *(required)*, `population` boolean (default: `False`), `precision` number (default: `4`) | `variance` (number), `mean` (number) |

## storage

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `storage.delete` | Delete a value from persistent key-value storage | `namespace` string *(required)*, `key` string *(required)* | `ok` (boolean), `deleted` (boolean), `key` (string) |
| `storage.get` | Retrieve a value from persistent key-value storage | `namespace` string *(required)*, `key` string *(required)*, `default` any | `ok` (boolean), `found` (boolean), `value` (any), `key` (string) |
| `storage.set` | Store a value in persistent key-value storage | `namespace` string *(required)*, `key` string *(required)*, `value` any *(required)*, `ttl_seconds` number (default: `0`) | `ok` (boolean), `key` (string), `stored_at` (number), `expires_at` (number) |

## string

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `string.lowercase` | Convert a string to lowercase | `text` string *(required)* | `result` (string), `original` (string), `status` (string) |
| `string.pad` | Pad a string to a specified length | `text` string *(required)*, `length` number *(required)*, `pad_char` string (default: ` `), `position` string (default: `end`) | `result` (string), `original` (string), `added` (number) |
| `string.replace` | Replace occurrences of a substring in a string | `text` string *(required)*, `search` string *(required)*, `replace` string *(required)* | `result` (string), `original` (string), `search` (string), `replace` (string), `status` (string) |
| `string.reverse` | Reverse the characters in a string | `text` string *(required)* | `result` (string), `original` (string), `length` (number) |
| `string.slugify` | Convert text to URL-friendly slug | `text` string *(required)*, `separator` string (default: `-`), `lowercase` boolean (default: `True`), `max_length` number (default: `0`) | `result` (string), `original` (string) |
| `string.split` | Split a string into an array using a delimiter | `text` string *(required)*, `delimiter` select (default: ` `) | `parts` (array), `result` (array), `length` (number), `original` (string), `delimiter` (string), `status` (string) |
| `string.template` | Render a template with variable substitution | `template` string *(required)*, `variables` object *(required)*, `missing_value` string (default: ``), `preserve_missing` boolean (default: `False`) | `result` (string), `replaced` (number), `missing` (array) |
| `string.titlecase` | Convert string to title case | `text` string *(required)* | `result` (string) |
| `string.trim` | Remove whitespace from both ends of a string | `text` string *(required)* | `result` (string), `original` (string), `status` (string) |
| `string.truncate` | Truncate a string to a maximum length | `text` string *(required)*, `length` number *(required)*, `suffix` string (default: `...`), `word_boundary` boolean (default: `False`) | `result` (string), `original` (string), `truncated` (boolean), `removed` (number) |
| `string.uppercase` | Convert a string to uppercase | `text` string *(required)* | `result` (string), `original` (string), `status` (string) |

## template

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `template.invoke` | Execute a template from your library as a workflow step | `template_id` string *(required)*, `library_id` string *(required)*, `timeout_seconds` number (default: `300`), `output_mapping` object (default: `{}`) | `__event__` (string), `result` (any), `template_id` (string), `execution_time_ms` (number) |

## test

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `test.assert_contains` | Assert that a collection contains a value | `collection` ['array', 'string'] *(required)*, `value` ['string', 'number', 'boolean'] *(required)*, `message` string | `passed` (boolean), `collection` (['array', 'string']), `value` (['string', 'number', 'boolean']), `message` (string) |
| `test.assert_equal` | Assert that two values are equal | `actual` ['string', 'number', 'boolean', 'object', 'array'] *(required)*, `expected` ['string', 'number', 'boolean', 'object', 'array'] *(required)*, `message` string | `passed` (boolean), `actual` (['string', 'number', 'boolean', 'object', 'array']), `expected` (['string', 'number', 'boolean', 'object', 'array']), `message` (string) |
| `test.assert_greater_than` | Assert that a value is greater than another | `actual` number *(required)*, `threshold` number *(required)*, `message` string | `passed` (boolean), `actual` (number), `threshold` (number), `message` (string) |
| `test.assert_length` | Assert that a collection has expected length | `collection` ['array', 'string'] *(required)*, `expected_length` number *(required)*, `message` string | `passed` (boolean), `actual_length` (number), `expected_length` (number), `message` (string) |
| `test.assert_not_null` | Assert that a value is not null or undefined | `value` ['string', 'number', 'boolean', 'object', 'array', 'null'] *(required)*, `message` string | `passed` (boolean), `message` (string) |
| `test.assert_status` | Compare probe statuses to a baseline to derive exploitable/sanitized verdict | `source` ['array', 'object'] *(required)*, `baseline_index` number (default: `0`), `probe_indices` array, `expected_blocked` array (default: `[401, 403]`), `on_bypass` string (default: `exploitable`), `on_blocked` string (default: `sanitized`), `on_error` string (default: `unreachable`) | `passed` (boolean), `verdict` (string), `baseline` (object), `probes` (array) |
| `test.assert_timing` | Compare probe duration to a baseline to detect time-based oracles | `source` ['array', 'object'] *(required)*, `baseline_index` number (default: `0`), `probe_index` number *(required)*, `threshold_ms` number (default: `3000`), `on_slow` string (default: `exploitable`), `on_normal` string (default: `inconclusive`), `on_error` string (default: `unreachable`) | `passed` (boolean), `verdict` (string), `baseline_ms` (number), `probe_ms` (number), `delta_ms` (number), `threshold_ms` (number) |
| `test.assert_true` | Assert that a condition is true | `condition` boolean *(required)*, `message` string | `passed` (boolean), `message` (string) |

## testing

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `testing.e2e.run_steps` | Execute end-to-end test steps sequentially | `steps` array *(required)*, `stop_on_failure` boolean (default: `True`), `timeout_per_step` number (default: `30000`) | `ok` (boolean), `passed` (number), `failed` (number), `results` (array) |
| `testing.gate.evaluate` | Evaluate quality metrics against defined thresholds | `metrics` object *(required)*, `thresholds` object *(required)*, `fail_on_breach` boolean (default: `True`) | `ok` (boolean), `passed` (boolean), `results` (array), `summary` (string) |
| `testing.http.run_suite` | Execute HTTP API test suite | `tests` array *(required)*, `base_url` string, `headers` object (default: `{}`) | `ok` (boolean), `passed` (number), `failed` (number), `results` (array) |
| `testing.lint.run` | Run linting checks on source code | `paths` array *(required)*, `linter` string (default: `auto`), `fix` boolean (default: `False`) | `ok` (boolean), `errors` (number), `warnings` (number), `issues` (array) |
| `testing.report.generate` | Generate test execution report | `results` object *(required)*, `format` string (default: `json`), `title` string (default: `Test Report`) | `ok` (boolean), `report` (string), `format` (string), `summary` (object) |
| `testing.scenario.run` | Execute scenario-based test (BDD style) | `scenario` object *(required)*, `context` object (default: `{}`) | `ok` (boolean), `passed` (boolean), `steps` (array) |
| `testing.security.scan` | Scan for security vulnerabilities | `targets` array *(required)*, `scan_type` string (default: `all`), `severity_threshold` string (default: `medium`) | `ok` (boolean), `vulnerabilities` (array), `summary` (object) |
| `testing.suite.run` | Execute a collection of tests | `tests` array *(required)*, `parallel` boolean (default: `False`), `max_failures` number (default: `0`) | `ok` (boolean), `passed` (number), `failed` (number), `skipped` (number), `results` (array) |
| `testing.unit.run` | Execute unit tests | `paths` array *(required)*, `pattern` string (default: `test_*.py`), `verbose` boolean (default: `False`) | `ok` (boolean), `passed` (number), `failed` (number), `errors` (number), `results` (array) |
| `testing.visual.compare` | Compare visual outputs for differences | `actual` string *(required)*, `expected` string *(required)*, `threshold` number (default: `0.1`), `output_diff` boolean (default: `True`) | `ok` (boolean), `match` (boolean), `difference` (number), `diff_image` (string) |

## text

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `text.char_count` | Count characters in text | `text` text *(required)* | `total` (number), `without_spaces` (number), `letters` (number), `digits` (number), `spaces` (number), `lines` (number) |
| `text.detect_encoding` | Detect text encoding | `text` text *(required)* | `encoding` (string), `confidence` (number), `is_ascii` (boolean), `has_bom` (boolean) |
| `text.extract_emails` | Extract all email addresses from text | `text` text *(required)*, `unique` boolean (default: `True`), `lowercase` boolean (default: `True`) | `emails` (array), `count` (number), `domains` (array) |
| `text.extract_numbers` | Extract all numbers from text | `text` text *(required)*, `include_decimals` boolean (default: `True`), `include_negative` boolean (default: `True`) | `numbers` (array), `count` (number), `sum` (number), `min` (number), `max` (number) |
| `text.extract_urls` | Extract all URLs from text | `text` text *(required)*, `unique` boolean (default: `True`) | `urls` (array), `count` (number) |
| `text.word_count` | Count words in text | `text` text *(required)* | `word_count` (number), `unique_words` (number), `sentence_count` (number), `paragraph_count` (number), `avg_word_length` (number) |

## training

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `training.practice.analyze` | Analyze website structure for practice | `url` string *(required)* | `status` (string), `structure` (object) |
| `training.practice.execute` | Execute practice session | `url` string *(required)*, `max_items` number (default: `10`) | `status` (string), `items_processed` (number) |
| `training.practice.infer_schema` | Infer data schema from website | `url` string *(required)*, `sample_size` number (default: `5`) | `status` (string), `schema` (object) |
| `training.practice.stats` | Get practice statistics | — | `total_sessions` (number), `successful_sessions` (number), `success_rate` (number), `history` (array) |

## ui

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `ui.evaluate` | Comprehensive UI quality evaluation with multi-dimensional scoring | `screenshot` string *(required)*, `app_type` string (default: `web_app`), `page_type` string, `evaluation_criteria` array (default: `['visual_design', 'usabilit...`), `target_audience` string, `brand_guidelines` string, `min_score` number (default: `70`), `api_key` string | `ok` (boolean), `passed` (boolean), `overall_score` (number), `scores` (object), `strengths` (array), `issues` (array), `recommendations` (array), `summary` (string) |

## utility

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `utility.datetime.now` | Get current date and time | `format` select (default: `iso`), `custom_format` string, `timezone` string (default: `UTC`) | `status` (string), `datetime` (string), `timestamp` (number), `iso` (string) |
| `utility.delay` | Pause workflow execution for specified duration | `duration_ms` number (default: `1000`), `duration_seconds` number | `status` (string), `waited_ms` (number) |
| `utility.hash.md5` | Calculate MD5 hash of text | `text` text *(required)*, `encoding` string (default: `utf-8`) | `status` (string), `hash` (string) |
| `utility.random.number` | Generate random number in range | `min` number (default: `0`), `max` number (default: `100`), `decimals` number (default: `0`) | `status` (string), `value` (number) |
| `utility.random.string` | Generate random string or UUID | `length` number (default: `16`), `charset` select (default: `alphanumeric`) | `status` (string), `value` (string) |

## validate

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `validate.credit_card` | Validate credit card number using Luhn algorithm | `card_number` string *(required)* | `valid` (boolean), `card_type` (string), `masked` (string), `luhn_valid` (boolean) |
| `validate.email` | Validate email address format | `email` string *(required)* | `valid` (boolean), `email` (string), `local_part` (string), `domain` (string) |
| `validate.ip` | Validate IPv4 or IPv6 address format | `ip` string *(required)*, `version` string (default: `any`) | `valid` (boolean), `ip` (string), `version` (string), `is_private` (boolean), `is_loopback` (boolean) |
| `validate.json_schema` | Validate JSON data against a JSON Schema | `data` text *(required)*, `schema` text *(required)* | `valid` (boolean), `errors` (array), `error_count` (number) |
| `validate.phone` | Validate phone number format | `phone` string *(required)*, `region` string (default: `international`) | `valid` (boolean), `phone` (string), `normalized` (string), `region` (string) |
| `validate.url` | Validate URL format and structure | `url` string *(required)*, `require_https` boolean (default: `False`) | `valid` (boolean), `url` (string), `scheme` (string), `host` (string), `port` (number), `path` (string), `query` (string) |
| `validate.uuid` | Validate UUID format and version | `uuid` string *(required)*, `version` number (default: `0`) | `valid` (boolean), `uuid` (string), `version` (number), `variant` (string) |

## verification

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `verification.discover` | Build a deterministic site graph from browser state or supplied page snapshots | `target` string *(required)*, `pages` array, `use_browser` boolean (default: `True`) | `ok` (boolean), `site_graph` (object), `scores` (object) |
| `verification.generate_scenarios` | Generate replayable Flyto2 YAML scenarios from a deterministic site graph | `site_graph` object *(required)*, `name` string, `output_format` string (default: `yaml`) | `ok` (boolean), `scenarios` (object), `workflow` (string) |
| `verification.report` | Create a deterministic verification evidence pack and optional report file | `site_graph` object, `scenarios` object, `run_result` object, `artifacts` object, `format` string (default: `json`), `output_path` string | `ok` (boolean), `evidence_pack` (object), `report` (string), `path` (string) |
| `verification.run` | Replay generated verification scenarios and return deterministic evidence | `scenarios` object *(required)*, `stop_on_failure` boolean (default: `True`), `timeout_per_step` number (default: `30000`) | `ok` (boolean), `passed` (number), `failed` (number), `results` (array), `evaluation` (object) |

## verify

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `verify.annotate` | Draw labeled bounding boxes on screenshots to mark differences | `image_path` string *(required)*, `annotations` array *(required)*, `output_path` string | `output_path` (string), `annotation_count` (integer) |
| `verify.capture` | Capture computed styles from browser element | `url` string *(required)*, `selector` string *(required)*, `wait_for` string, `viewport_width` number (default: `1280`), `viewport_height` number (default: `800`) | `element` (object), `found` (boolean) |
| `verify.compare` | Compare captured styles with expected values | `actual` object *(required)*, `expected` object *(required)*, `selector` string, `size_tolerance` number (default: `2.0`), `spacing_tolerance` number (default: `2.0`), `font_size_tolerance` number (default: `1.0`), `color_tolerance` number (default: `5`), `check_typography` boolean (default: `True`), `check_colors` boolean (default: `True`), `check_spacing` boolean (default: `True`), `check_sizing` boolean (default: `False`) | `passed` (boolean), `violations` (array), `error_count` (number), `warning_count` (number) |
| `verify.figma` | Fetch design tokens from Figma API (token stays local) | `file_id` string *(required)*, `node_id` string, `node_name` string, `token` string | `node` (object), `style` (object) |
| `verify.report` | Generate verification report in HTML/JSON/Markdown | `results` array *(required)*, `name` string (default: `verify-report`), `url` string, `format` string (default: `html`), `output_dir` string (default: `./verify-reports`), `screenshots` array | `report_path` (string), `summary` (object) |
| `verify.ruleset` | Load verification rules from YAML file | `path` string *(required)* | `ruleset` (object), `rules_count` (integer) |
| `verify.run` | Run full design verification: capture → compare → report | `url` string *(required)*, `selectors` array, `ruleset_path` string, `expected_styles` object, `figma_file_id` string, `figma_token` string, `figma_mapping` object, `output_dir` string (default: `./verify-reports`), `report_format` string (default: `html`), `take_screenshot` boolean (default: `True`), `viewport_width` number (default: `1280`), `viewport_height` number (default: `800`) | `passed` (boolean), `summary` (object), `report_path` (string) |
| `verify.spec` | Dynamic spec verification - compose any modules via YAML | `ruleset_path` string, `ruleset` object | `passed` (boolean), `summary` (object), `results` (array) |
| `verify.visual_diff` | Compare reference design with dev site visually, annotate differences | `reference_url` string *(required)*, `dev_url` string *(required)*, `output_dir` string (default: `./verify-reports/visual-diff`), `focus_areas` array, `viewport_width` number (default: `1280`), `viewport_height` number (default: `800`), `model` string (default: `gpt-4o`), `api_key` string | `similarity_score` (number), `annotations` (array), `annotated_image` (string), `report_path` (string), `summary` (string) |

## vision

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `vision.analyze` | Analyze images using OpenAI Vision API (GPT-4V) | `image` string *(required)*, `prompt` string *(required)*, `analysis_type` select (default: `general`), `context` string, `output_format` select (default: `structured`), `model` string (default: `gpt-4o`), `max_tokens` number (default: `1000`), `api_key` string *(required)*, `header_name` string (default: `X-API-Key`), `detail` select (default: `high`) | `ok` (boolean), `analysis` (string), `structured` (object), `model` (string), `tokens_used` (number) |
| `vision.compare` | Compare two images and identify visual differences | `image_before` string *(required)*, `image_after` string *(required)*, `comparison_type` select (default: `visual_regression`), `threshold` number (default: `5`), `focus_areas` array, `ignore_areas` array, `model` string (default: `gpt-4o`), `api_key` string *(required)*, `header_name` string (default: `X-API-Key`) | `ok` (boolean), `has_differences` (boolean), `similarity_score` (number), `differences` (array), `summary` (string), `recommendation` (string) |

## warroom

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `warroom.discover` | Build a deterministic site graph from browser state or supplied page snapshots | `target` string *(required)*, `pages` array, `use_browser` boolean (default: `True`) | `ok` (boolean), `site_graph` (object), `scores` (object) |
| `warroom.generate_scenarios` | Generate replayable Flyto2 YAML scenarios from a Warroom site graph | `site_graph` object *(required)*, `name` string, `output_format` string (default: `yaml`) | `ok` (boolean), `scenarios` (object), `workflow` (string) |
| `warroom.llm_review` | Prepare redacted evidence for manual LLM review; never gates by itself | `enabled` boolean (default: `False`), `evidence_pack` object *(required)*, `question` string | `ok` (boolean), `status` (string), `advisory_only` (boolean), `redacted_evidence` (object) |
| `warroom.public_site_verify` | Evaluate DNS, TLS, route, browser, and SEO/GEO evidence for a public site | `base_url` string *(required)*, `observations` object *(required)*, `required_routes` array, `generated_at` string | `ok` (boolean), `contract` (string), `p0_findings` (number), `p1_findings` (number), `route_matrix` (array), `browser_matrix` (array) |
| `warroom.report` | Create a deterministic Warroom evidence pack and optional report file | `site_graph` object, `scenarios` object, `run_result` object, `artifacts` object, `format` string (default: `json`), `output_path` string | `ok` (boolean), `evidence_pack` (object), `report` (string), `path` (string) |
| `warroom.run` | Replay generated Warroom scenarios and return deterministic evidence | `scenarios` object *(required)*, `stop_on_failure` boolean (default: `True`), `timeout_per_step` number (default: `30000`) | `ok` (boolean), `passed` (number), `failed` (number), `results` (array), `evaluation` (object) |

## webhook

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `webhook.trigger` | Send HTTP POST request to a webhook URL | `url` string *(required)*, `method` select (default: `POST`), `payload` object, `headers` object (default: `{}`), `content_type` select (default: `application/json`), `auth_token` string, `timeout` number (default: `30`) | `status_code` (number), `response` (object), `headers` (object) |

## word

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `word.parse` | Extract text and content from Word documents (.docx) | `file_path` string *(required)*, `extract_tables` boolean (default: `True`), `extract_images` boolean (default: `False`), `images_output_dir` string, `preserve_formatting` boolean (default: `False`) | `text` (string), `paragraphs` (array), `tables` (array), `images` (array), `metadata` (object) |
| `word.to_pdf` | Convert Word documents (.docx) to PDF files | `input_path` string *(required)*, `output_path` string, `method` select (default: `auto`) | `output_path` (string), `file_size` (number), `method_used` (string) |
