# Tool Catalog

> Auto-generated from flyto-core module registry. **329 modules** across **63 categories**.
>
> Last generated: 2026-02-15

## Categories

- [agent](#agent) (2)
- [ai](#ai) (6)
- [analysis](#analysis) (6)
- [api](#api) (11)
- [array](#array) (15)
- [browser](#browser) (38)
- [check](#check) (7)
- [cloud](#cloud) (6)
- [communication](#communication) (2)
- [compare](#compare) (1)
- [convert](#convert) (5)
- [core](#core) (4)
- [crypto](#crypto) (3)
- [data](#data) (4)
- [database](#database) (3)
- [datetime](#datetime) (4)
- [db](#db) (6)
- [decode](#decode) (3)
- [element](#element) (3)
- [email](#email) (2)
- [encode](#encode) (4)
- [error](#error) (3)
- [excel](#excel) (2)
- [file](#file) (8)
- [flow](#flow) (19)
- [format](#format) (5)
- [hash](#hash) (2)
- [http](#http) (3)
- [image](#image) (5)
- [llm](#llm) (3)
- [logic](#logic) (5)
- [math](#math) (6)
- [meta](#meta) (4)
- [notification](#notification) (4)
- [notify](#notify) (1)
- [object](#object) (10)
- [path](#path) (6)
- [payment](#payment) (3)
- [pdf](#pdf) (4)
- [port](#port) (2)
- [process](#process) (3)
- [productivity](#productivity) (3)
- [random](#random) (4)
- [regex](#regex) (5)
- [set](#set) (4)
- [shell](#shell) (1)
- [slack](#slack) (1)
- [stats](#stats) (8)
- [stealth](#stealth) (2)
- [storage](#storage) (3)
- [string](#string) (11)
- [template](#template) (1)
- [test](#test) (6)
- [testing](#testing) (10)
- [text](#text) (6)
- [training](#training) (4)
- [ui](#ui) (1)
- [utility](#utility) (5)
- [validate](#validate) (7)
- [verify](#verify) (9)
- [vision](#vision) (2)
- [webhook](#webhook) (1)
- [word](#word) (2)

---

## agent

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `agent.autonomous` | Self-directed AI agent with memory and goal-oriented behavior | `goal` string *(required)*, `context` string, `max_iterations` number (default: `5`), `llm_provider` select (default: `openai`), `model` string (default: `gpt-4-turbo-preview`), `ollama_url` string (default: `http://localhost:11434`), `temperature` number (default: `0.7`) | `result` (string), `thoughts` (array), `iterations` (number), `goal_achieved` (boolean) |
| `agent.chain` | Sequential AI processing chain with multiple steps | `input` string *(required)*, `chain_steps` array *(required)*, `llm_provider` select (default: `openai`), `model` string (default: `gpt-4-turbo-preview`), `ollama_url` string (default: `http://localhost:11434`), `temperature` number (default: `0.7`) | `result` (string), `intermediate_results` (array), `steps_completed` (number) |

## ai

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `ai.local_ollama.chat` | Chat with local LLM via Ollama (completely offline) | `prompt` string *(required)*, `model` select (default: `llama2`), `temperature` number (default: `0.7`), `system_message` string, `ollama_url` string (default: `http://localhost:11434`), `max_tokens` number | `response` (string), `model` (string), `context` (array), `total_duration` (number), `load_duration` (number), `prompt_eval_count` (number), `eval_count` (number) |
| `ai.memory` | Conversation memory for AI Agent | `memory_type` select *(required)*, `window_size` number (default: `10`), `session_id` string (default: ``), `initial_messages` array (default: `[]`) | `memory_type` (string), `session_id` (string), `messages` (array), `config` (object) |
| `ai.memory.entity` | Extract and track entities (people, places, concepts) from conversations | `entity_types` multiselect (default: `['person', 'organization', ...`), `extraction_model` select *(required)*, `session_id` string (default: ``), `track_relationships` boolean (default: `True`), `max_entities` number (default: `100`) | `memory_type` (string), `session_id` (string), `entities` (object), `relationships` (array), `config` (object) |
| `ai.memory.redis` | Persistent conversation memory using Redis storage | `redis_url` string *(required)*, `key_prefix` string (default: `flyto:memory:`), `session_id` string *(required)*, `ttl_seconds` number (default: `86400`), `max_messages` number (default: `100`), `load_on_start` boolean (default: `True`) | `memory_type` (string), `session_id` (string), `messages` (array), `connected` (boolean), `config` (object) |
| `ai.memory.vector` | Semantic memory using vector embeddings for relevant context retrieval | `embedding_model` select *(required)*, `top_k` number (default: `5`), `similarity_threshold` number (default: `0.7`), `session_id` string (default: ``), `include_metadata` boolean (default: `True`) | `memory_type` (string), `session_id` (string), `embedding_model` (string), `config` (object) |
| `ai.model` | LLM model configuration for AI Agent | `provider` string (default: `openai`), `model` string (default: `gpt-4o`), `temperature` number (default: `0.7`), `api_key` string, `base_url` string, `max_tokens` number (default: `4096`) | `provider` (string), `model` (string), `config` (object) |

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
| `api.anthropic.chat` | Send a chat message to Anthropic Claude AI and get a response | `api_key` string, `model` string (default: `claude-3-5-sonnet-20241022`), `messages` array *(required)*, `max_tokens` number (default: `1024`), `temperature` number (default: `1.0`), `system` string | `content` (string), `model` (string), `stop_reason` (string), `usage` (object) |
| `api.github.create_issue` | Create a new issue in a GitHub repository | `owner` string *(required)*, `repo` string *(required)*, `title` string *(required)*, `body` text, `labels` array, `assignees` array, `token` string *(required)* | `status` (string), `issue` (object), `number` (number), `url` (string) |
| `api.github.get_repo` | Get information about a GitHub repository | `owner` string *(required)*, `repo` string *(required)*, `token` string | `status` (string), `repo` (object), `name` (string), `full_name` (string), `description` (string), `stars` (number), `forks` (number), `url` (string) |
| `api.github.list_issues` | List issues from a GitHub repository | `owner` string *(required)*, `repo` string *(required)*, `state` select (default: `open`), `labels` string, `limit` number (default: `30`), `token` string | `status` (string), `issues` (array), `count` (number) |
| `api.google_gemini.chat` | Send a chat message to Google Gemini AI and get a response | `api_key` string, `model` string (default: `gemini-1.5-pro`), `prompt` string *(required)*, `temperature` number (default: `1.0`), `max_output_tokens` number (default: `2048`) | `text` (string), `model` (string), `candidates` (array) |
| `api.google_sheets.read` | Read data from Google Sheets spreadsheet | `credentials` object, `spreadsheet_id` string *(required)*, `range` string *(required)*, `include_header` boolean (default: `True`) | `values` (array), `data` (array), `row_count` (number) |
| `api.google_sheets.write` | Write data to Google Sheets spreadsheet | `credentials` object, `spreadsheet_id` string *(required)*, `range` string *(required)*, `values` array *(required)*, `value_input_option` string (default: `USER_ENTERED`) | `updated_range` (string), `updated_rows` (number), `updated_columns` (number), `updated_cells` (number) |
| `api.notion.create_page` | Create a new page in Notion database | `api_key` string, `database_id` string *(required)*, `properties` object *(required)*, `content` array | `page_id` (string), `url` (string), `created_time` (string) |
| `api.notion.query_database` | Query pages from Notion database with filters and sorting | `api_key` string, `database_id` string *(required)*, `filter` object, `sorts` array, `page_size` number (default: `100`) | `results` (array), `count` (number), `has_more` (boolean) |
| `api.openai.chat` | Send a chat message to OpenAI GPT models | `prompt` string *(required)*, `model` select (default: `gpt-4-turbo-preview`), `temperature` number (default: `0.7`), `max_tokens` number (default: `1000`), `system_message` string | `response` (string), `model` (string), `usage` (object) |
| `api.openai.image` | Generate images using DALL-E | `prompt` string *(required)*, `size` select (default: `1024x1024`), `model` select (default: `dall-e-3`), `quality` select (default: `standard`), `n` number (default: `1`) | `images` (array), `model` (string) |

## array

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `array.chunk` | Split array into chunks of specified size | `array` array *(required)*, `size` number *(required)* | `result` (array), `chunks` (number) |
| `array.compact` | Remove null/empty values from array | `array` array *(required)*, `remove_empty_strings` boolean (default: `True`), `remove_zero` boolean (default: `False`), `remove_false` boolean (default: `False`) | `result` (array), `removed` (number) |
| `array.difference` | Find elements in first array not in others | `array` array *(required)*, `subtract` array *(required)* | `result` (array), `length` (number) |
| `array.drop` | Drop first N elements from array | `array` array *(required)*, `count` number *(required)* | `result` (array), `dropped` (number) |
| `array.filter` | Filter array elements by condition | `array` array *(required)*, `condition` string *(required)*, `value` string *(required)* | `filtered` (array), `count` (number) |
| `array.flatten` | Flatten nested arrays into single array | `array` array *(required)*, `depth` number (default: `1`) | `result` (array), `length` (number) |
| `array.group_by` | Group array elements by a key | `array` array *(required)*, `key` string *(required)* | `groups` (object), `keys` (array), `count` (number) |
| `array.intersection` | Find common elements between arrays | `arrays` array *(required)* | `result` (array), `length` (number) |
| `array.join` | Join array elements into string | `array` array *(required)*, `separator` string (default: `,`) | `result` (string) |
| `array.map` | Transform each element in an array | `array` array *(required)*, `operation` select *(required)*, `value` any | `result` (array), `length` (number) |
| `array.reduce` | Reduce array to single value | `array` array *(required)*, `operation` select *(required)*, `separator` string (default: `,`) | `result` (any), `operation` (string) |
| `array.sort` | Sort array elements in ascending or descending order | `array` array *(required)*, `order` string (default: `asc`) | `sorted` (array), `count` (number) |
| `array.take` | Take first N elements from array | `array` array *(required)*, `count` number *(required)* | `result` (array), `length` (number) |
| `array.unique` | Remove duplicate values from array | `array` array *(required)*, `preserve_order` boolean (default: `True`) | `unique` (array), `count` (number), `duplicates_removed` (number) |
| `array.zip` | Combine multiple arrays element-wise | `arrays` array *(required)*, `fill_value` any | `result` (array), `length` (number) |

## browser

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `browser.click` | Click an element on the page | `click_method` select (default: `text`), `target` string, `selector` string, `timeout` number (default: `30000`) | `status` (string), `selector` (string), `method` (string) |
| `browser.close` | Close the browser instance and release resources | `_no_params` boolean (default: `True`) | `status` (string), `message` (string) |
| `browser.console` | Capture browser console logs (errors, warnings, info) | `level` string (default: `all`), `timeout` number (default: `5000`), `clear_existing` boolean (default: `False`) | `status` (string), `messages` (array), `count` (number) |
| `browser.cookies` | Get, set, or clear browser cookies | `action` string *(required)*, `name` string, `value` string, `domain` string, `path` string (default: `/`), `secure` boolean (default: `False`), `httpOnly` boolean (default: `False`), `expires` number | `status` (string), `cookies` (array), `count` (number) |
| `browser.dialog` | Handle alert, confirm, and prompt dialogs | `action` string *(required)*, `prompt_text` string, `timeout` number (default: `30000`) | `status` (string), `message` (string), `type` (string), `default_value` (string) |
| `browser.download` | Download file from browser | `selector` string, `save_path` string *(required)*, `timeout` number (default: `60000`) | `status` (string), `path` (string), `filename` (string), `size` (number) |
| `browser.drag` | Drag and drop elements | `source` string *(required)*, `target` string *(required)*, `source_position` object, `target_position` object, `timeout` number (default: `30000`) | `status` (string), `source` (string), `target` (string) |
| `browser.emulate` | Emulate mobile devices, tablets, and custom viewports | `device` string *(required)*, `width` number, `height` number, `user_agent` string, `is_mobile` boolean, `has_touch` boolean, `device_scale_factor` number | `status` (string), `device` (string), `viewport` (object), `is_mobile` (boolean) |
| `browser.ensure` | Ensure a browser session exists (reuse or launch) | `headless` boolean (default: `False`), `width` number (default: `1280`), `height` number (default: `720`) | `status` (string), `message` (string), `is_owner` (boolean) |
| `browser.evaluate` | Execute JavaScript code in page context | `script` string *(required)*, `args` array | `status` (string), `result` (any) |
| `browser.extract` | Extract structured data from the page | `selector` string *(required)*, `limit` number, `fields` object | `status` (string), `data` (array), `count` (number) |
| `browser.find` | Find elements in page and return element ID list | `selector` string *(required)*, `limit` number | `status` (string), `count` (number), `element_ids` (array) |
| `browser.form` | Smart form filling with automatic field detection | `form_selector` string, `data` object *(required)*, `field_mapping` object, `clear_before_fill` boolean (default: `True`), `submit` boolean (default: `False`), `submit_selector` string, `delay_between_fields_ms` integer (default: `100`) | `filled_fields` (array), `failed_fields` (array), `submitted` (boolean) |
| `browser.frame` | Switch to iframe or frame context | `selector` string, `name` string, `url` string, `action` string (default: `enter`), `timeout` number (default: `30000`) | `status` (string), `frame_url` (string), `frame_name` (string), `frames` (array) |
| `browser.geolocation` | Mock browser geolocation | `latitude` number *(required)*, `longitude` number *(required)*, `accuracy` number (default: `100`) | `status` (string), `location` (object) |
| `browser.goto` | Navigate to a specific URL | `url` string *(required)*, `wait_until` select (default: `domcontentloaded`), `timeout_ms` number (default: `30000`) | `status` (string), `url` (string) |
| `browser.hover` | Hover mouse over an element | `selector` string *(required)*, `timeout` number (default: `30000`), `position` object | `status` (string), `selector` (string) |
| `browser.launch` | Launch a new browser instance with Playwright | `headless` boolean (default: `False`), `width` number (default: `1280`), `height` number (default: `720`) | `status` (string), `message` (string) |
| `browser.login` | Handle common login flows with success/failure detection | `username` string *(required)*, `password` string *(required)*, `username_selector` string, `password_selector` string, `submit_selector` string, `success_selector` string, `error_selector` string, `remember_me` boolean (default: `False`), `remember_me_selector` string, `timeout_ms` integer (default: `30000`), `delay_before_submit_ms` integer (default: `500`) | `success` (boolean), `error_message` (string), `requires_2fa` (boolean), `redirect_url` (string) |
| `browser.network` | Monitor and intercept network requests | `action` string *(required)*, `url_pattern` string, `resource_type` string, `timeout` number (default: `30000`), `mock_response` object | `status` (string), `requests` (array), `blocked_count` (number) |
| `browser.pages` | List all open browser pages/tabs with details | `include_details` boolean (default: `True`), `include_content_info` boolean (default: `False`) | `status` (string), `pages` (array), `count` (number), `current_index` (number) |
| `browser.pagination` | Auto-paginate through pages and extract data | `mode` string (default: `next_button`), `item_selector` string *(required)*, `fields` object, `next_selector` string, `load_more_selector` string, `max_pages` integer (default: `10`), `max_items` integer (default: `0`), `wait_between_pages_ms` integer (default: `1000`), `wait_for_selector` string, `scroll_amount` integer (default: `1000`), `no_more_indicator` string | `items` (array), `total_items` (integer), `pages_processed` (integer), `stopped_reason` (string) |
| `browser.pdf` | Generate PDF from current page | `path` string (default: ``), `page_size` string (default: `A4`), `orientation` string (default: `portrait`), `print_background` boolean (default: `True`), `scale` number (default: `1`), `margin` number (default: `20`), `header` string, `footer` string | `status` (string), `path` (string), `size` (number) |
| `browser.performance` | Collect Web Vitals (LCP, FCP, CLS, TTFB) and performance metrics | `metrics` array (default: `['all']`), `timeout_ms` number (default: `3000`), `setup_observers` boolean (default: `True`) | `status` (string), `metrics` (object) |
| `browser.press` | Press a keyboard key | `key` string *(required)* | `status` (string), `key` (string) |
| `browser.record` | Record user actions as workflow | `action` string *(required)*, `output_format` string (default: `yaml`), `output_path` string (default: ``) | `status` (string), `recording` (array), `workflow` (string) |
| `browser.release` | Release browser session (close only if owned) | `force` boolean (default: `False`) | `status` (string), `message` (string), `was_owner` (boolean) |
| `browser.screenshot` | Take a screenshot of the current page | `path` string (default: `screenshot.png`), `full_page` boolean (default: `False`), `format` select (default: `png`) | `status` (string), `filepath` (string) |
| `browser.scroll` | Scroll page to element, position, or direction | `selector` string, `direction` string (default: `down`), `amount` number (default: `500`), `behavior` string (default: `smooth`) | `status` (string), `scrolled_to` (object) |
| `browser.select` | Select option from dropdown element | `selector` string *(required)*, `value` string, `label` string, `index` number, `timeout` number (default: `30000`) | `status` (string), `selected` (array), `selector` (string) |
| `browser.snapshot` | Capture DOM snapshot in HTML, MHTML, or text format | `format` string (default: `html`), `selector` string, `path` string (default: ``) | `status` (string), `format` (string), `content` (string), `path` (string), `size_bytes` (number) |
| `browser.storage` | Access localStorage and sessionStorage | `action` string *(required)*, `type` string (default: `local`), `key` string, `value` string | `status` (string), `value` (any), `keys` (array), `length` (number) |
| `browser.tab` | Create, switch, and close browser tabs | `action` string *(required)*, `url` string, `index` number | `status` (string), `tab_count` (number), `current_index` (number), `tabs` (array) |
| `browser.trace` | Start/stop Chrome DevTools performance tracing (Chromium only) | `action` string *(required)*, `categories` array (default: `['devtools.timeline']`), `screenshots` boolean (default: `True`), `path` string (default: ``) | `status` (string), `tracing` (boolean), `path` (string), `size_bytes` (number) |
| `browser.type` | Type text into an input field | `selector` string *(required)*, `text` string *(required)* | `status` (string), `selector` (string) |
| `browser.upload` | Upload file to file input element | `selector` string *(required)*, `file_path` string *(required)*, `timeout` number (default: `30000`) | `status` (string), `filename` (string), `size` (number), `selector` (string) |
| `browser.viewport` | Resize browser viewport to specific dimensions | `width` number *(required)*, `height` number *(required)* | `status` (string), `viewport` (object), `previous_viewport` (object) |
| `browser.wait` | Wait for a duration or until an element appears | `duration_ms` number (default: `1000`), `selector` string, `timeout` number (default: `30000`) | `status` (string), `selector` (string), `duration_ms` (number) |

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
| `core.api.http_get` | Send HTTP GET request to any URL | `url` string *(required)*, `headers` object (default: `{}`), `params` object (default: `{}`), `timeout` number (default: `30`) | `status_code` (number), `headers` (object), `body` (string), `json` (object) |
| `core.api.http_post` | Send HTTP POST request to any URL | `url` string *(required)*, `headers` object (default: `{}`), `body` string, `json` any, `timeout` number (default: `30`) | `status_code` (number), `headers` (object), `body` (string), `json` (object) |
| `core.api.serpapi_search` | Use SerpAPI to search keywords (100 free searches/month) | `keyword` string *(required)*, `limit` number (default: `10`) | `status` (string), `data` (array), `count` (number) |

## crypto

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `crypto.hmac` | Generate HMAC signature | `message` text *(required)*, `key` password *(required)*, `algorithm` string (default: `sha256`), `encoding` string (default: `hex`) | `signature` (string), `algorithm` (string) |
| `crypto.random_bytes` | Generate cryptographically secure random bytes | `length` number *(required)*, `encoding` string (default: `hex`) | `bytes` (string), `length` (number) |
| `crypto.random_string` | Generate cryptographically secure random string | `length` number *(required)*, `charset` string (default: `alphanumeric`), `uppercase` boolean (default: `False`) | `string` (string), `length` (number) |

## data

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `data.json.parse` | Parse JSON string into object | `json_string` text *(required)* | `status` (string), `data` (object) |
| `data.json.stringify` | Convert object to JSON string | `data` object *(required)*, `pretty` boolean (default: `False`), `indent` number (default: `2`) | `status` (string), `json` (string) |
| `data.pipeline` | Chain multiple data transformations in a single step | `input` any *(required)*, `steps` array *(required)* | `result` (any), `original_count` (integer), `result_count` (integer), `steps_applied` (integer) |
| `data.text.template` | Fill text template with variables | `template` text *(required)*, `variables` object *(required)* | `status` (string), `result` (string) |

## database

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `database.insert` | Insert data into database tables | `table` string *(required)*, `data` object *(required)*, `database_type` string (default: `postgresql`), `connection_string` string, `host` string, `port` number, `database` string, `user` string, `password` string, `returning` array | `inserted_count` (number), `returning_data` (array) |
| `database.query` | Execute SQL queries on PostgreSQL, MySQL, or SQLite databases | `query` string *(required)*, `params` array (default: `[]`), `database_type` string (default: `postgresql`), `connection_string` string, `host` string, `port` number, `database` string, `user` string, `password` string, `fetch` string (default: `all`) | `rows` (array), `row_count` (number), `columns` (array) |
| `database.update` | Update data in database tables | `table` string *(required)*, `data` object *(required)*, `where` object *(required)*, `database_type` string (default: `postgresql`), `connection_string` string, `host` string, `port` number, `database` string, `user` string, `password` string | `updated_count` (number) |

## datetime

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `datetime.add` | Add time to datetime | `datetime` string (default: `now`), `days` number (default: `0`), `hours` number (default: `0`), `minutes` number (default: `0`), `seconds` number (default: `0`) | `result` (string), `timestamp` (number) |
| `datetime.format` | Format datetime to string | `datetime` string (default: `now`), `format` string (default: `%Y-%m-%d %H:%M:%S`) | `result` (string), `timestamp` (number) |
| `datetime.parse` | Parse string to datetime | `datetime_string` string *(required)*, `format` string (default: `%Y-%m-%d %H:%M:%S`) | `result` (string), `timestamp` (number), `year` (number), `month` (number), `day` (number), `hour` (number), `minute` (number), `second` (number) |
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

## error

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `error.circuit_breaker` | Protect against cascading failures with circuit breaker pattern | `action` object *(required)*, `circuit_id` string *(required)*, `failure_threshold` integer (default: `5`), `failure_window_ms` integer (default: `60000`), `recovery_timeout_ms` integer (default: `30000`), `success_threshold` integer (default: `3`), `fallback` object, `fallback_value` any, `track_errors` array (default: `[]`) | `__event__` (string), `result` (any), `circuit_state` (string), `failure_count` (integer), `last_failure_time` (string), `circuit_opened_at` (string) |
| `error.fallback` | Provide fallback value when operation fails | `operation` object, `fallback_value` any, `fallback_operation` object, `fallback_on` array (default: `[]`), `include_error_info` boolean (default: `True`), `log_fallback` boolean (default: `True`) | `result` (any), `used_fallback` (boolean), `source` (string), `original_error` (object) |
| `error.retry` | Wrap operations with configurable retry logic | `operation` object *(required)*, `max_retries` integer (default: `3`), `initial_delay_ms` integer (default: `1000`), `max_delay_ms` integer (default: `30000`), `backoff_multiplier` number (default: `2.0`), `jitter` boolean (default: `True`), `retry_on` array (default: `[]`), `timeout_per_attempt_ms` integer (default: `0`) | `__event__` (string), `result` (any), `attempts` (integer), `total_delay_ms` (number), `errors` (array) |

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
| `file.edit` | Replace a string in a file (targeted edit, not full overwrite) | `path` string *(required)*, `old_string` string *(required)*, `new_string` string *(required)*, `replace_all` boolean (default: `False`), `encoding` string (default: `utf-8`) | `path` (string), `replacements` (number), `diff` (string) |
| `file.exists` | Check if a file or directory exists | `path` string *(required)* | `exists` (boolean), `is_file` (boolean), `is_directory` (boolean) |
| `file.move` | Move or rename a file | `source` string *(required)*, `destination` string *(required)* | `moved` (boolean), `source` (string), `destination` (string) |
| `file.read` | Read content from a file | `path` string *(required)*, `encoding` string (default: `utf-8`) | `content` (string), `size` (number) |
| `file.write` | Write content to a file | `path` string *(required)*, `content` string *(required)*, `encoding` string (default: `utf-8`), `mode` string (default: `overwrite`) | `path` (string), `bytes_written` (number) |

## flow

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `flow.batch` | Process items in batches with configurable size | `items` array *(required)*, `batch_size` integer *(required)*, `delay_ms` integer (default: `0`), `continue_on_error` boolean (default: `False`), `parallel_batches` integer (default: `1`) | `__event__` (string), `batch` (array), `batch_index` (integer), `total_batches` (integer), `total_items` (integer), `is_last_batch` (boolean), `progress` (object) |
| `flow.branch` | Conditional branching based on expression evaluation | `condition` string *(required)* | `__event__` (string), `outputs` (object), `result` (boolean), `condition` (string), `resolved_condition` (string) |
| `flow.breakpoint` | Pause workflow execution for human approval or input | `title` string (default: `Approval Required`), `description` string, `timeout_seconds` integer (default: `0`), `required_approvers` array *(required)*, `approval_mode` string (default: `single`), `custom_fields` array *(required)*, `include_context` boolean (default: `True`), `auto_approve_condition` string | `__event__` (string), `breakpoint_id` (string), `status` (string), `approved_by` (array), `rejected_by` (array), `custom_inputs` (object), `comments` (array), `resolved_at` (string), `wait_duration_ms` (integer) |
| `flow.container` | Embedded subflow container for organizing complex workflows | `subflow` object (default: `{'nodes': [], 'edges': []}`), `inherit_context` boolean (default: `True`), `isolated_variables` array *(required)*, `export_variables` array *(required)* | `__event__` (string), `outputs` (object), `subflow_result` (object), `exported_variables` (object), `node_count` (integer), `execution_time_ms` (number) |
| `flow.end` | Explicit workflow end node | `output_mapping` object (default: `{}`), `success_message` string | `__event__` (string), `ended_at` (string), `workflow_result` (object) |
| `flow.error_handle` | Catches and handles errors from upstream nodes | `action` string *(required)*, `include_traceback` boolean (default: `True`), `error_code_mapping` object (default: `{}`), `fallback_value` any | `__event__` (string), `outputs` (object), `error_info` (object), `action_taken` (string) |
| `flow.error_workflow_trigger` | Entry point for error workflows - triggered when another workflow fails | `description` string (default: ``) | `__event__` (string), `error_context` (object), `triggered_at` (string) |
| `flow.foreach` | Iterate over a list and execute steps for each item | `items` array *(required)*, `steps` array, `item_var` string (default: `item`), `index_var` string (default: `index`), `output_mode` string (default: `collect`) | `__event__` (string), `__set_context` (object), `outputs` (object), `iteration` (number), `status` (string), `results` (array), `count` (number) |
| `flow.fork` | Split execution into parallel branches | `branch_count` integer (default: `2`) | `__event__` (string), `input_data` (any), `branch_count` (integer) |
| `flow.goto` | Unconditional jump to another step | `target` string *(required)*, `max_iterations` number (default: `100`) | `__event__` (string), `target` (string), `iteration` (number) |
| `flow.invoke` | Execute an external workflow file | `workflow_source` string *(required)*, `workflow_params` object *(required)*, `timeout_seconds` number (default: `300`), `output_mapping` object (default: `{}`) | `__event__` (string), `result` (any), `workflow_id` (string), `execution_time_ms` (number) |
| `flow.join` | Wait for parallel branches to complete | `strategy` string (default: `all`), `input_count` integer (default: `2`), `timeout` number (default: `60000`), `cancel_pending` boolean (default: `True`) | `__event__` (string), `joined_data` (array), `completed_count` (integer), `strategy` (string) |
| `flow.loop` | Repeat steps N times using output port routing | `times` number *(required)*, `target` string, `steps` array, `index_var` string (default: `index`) | `__event__` (string), `outputs` (object), `iteration` (number), `status` (string), `results` (array), `count` (number) |
| `flow.merge` | Merge multiple inputs into a single output | `strategy` string (default: `all`), `input_count` integer (default: `2`) | `__event__` (string), `merged_data` (any), `input_count` (integer), `strategy` (string) |
| `flow.parallel` | Execute multiple tasks in parallel with different strategies | `tasks` array *(required)*, `mode` string (default: `all`), `timeout_ms` integer (default: `60000`), `fail_fast` boolean (default: `True`), `concurrency_limit` integer (default: `0`) | `__event__` (string), `results` (array), `completed_count` (integer), `failed_count` (integer), `total_count` (integer), `mode` (string), `duration_ms` (number) |
| `flow.start` | Explicit workflow start node | — | `__event__` (string), `started_at` (string), `workflow_id` (string) |
| `flow.subflow` | Reference and execute an external workflow | `workflow_ref` string *(required)*, `execution_mode` select (default: `inline`), `input_mapping` object *(required)*, `output_mapping` object (default: `{}`), `timeout` number (default: `300000`) | `__event__` (string), `result` (any), `execution_id` (string), `workflow_ref` (string) |
| `flow.switch` | Multi-way branching based on value matching | `expression` string *(required)*, `cases` array *(required)* | `__event__` (string), `outputs` (object), `matched_case` (string), `value` (any) |
| `flow.trigger` | Workflow entry point - manual, webhook, schedule, or event | `trigger_type` string (default: `manual`), `webhook_path` string, `schedule` string, `event_name` string, `config` object, `description` string | `__event__` (string), `trigger_data` (object), `trigger_type` (string), `triggered_at` (string) |

## format

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `format.currency` | Format numbers as currency | `amount` number *(required)*, `currency` string (default: `USD`), `decimal_places` number (default: `2`), `symbol_position` string (default: `before`) | `result` (string), `original` (number), `symbol` (string) |
| `format.duration` | Format seconds as human-readable duration | `seconds` number *(required)*, `format` string (default: `short`), `show_zero` boolean (default: `False`) | `result` (string), `original` (number), `parts` (object) |
| `format.filesize` | Format bytes as human-readable file size | `bytes` number *(required)*, `binary` boolean (default: `False`), `decimal_places` number (default: `2`) | `result` (string), `original` (number), `unit` (string), `value` (number) |
| `format.number` | Format numbers with separators and decimals | `number` number *(required)*, `decimal_places` number (default: `2`), `thousand_separator` string (default: `,`), `decimal_separator` string (default: `.`) | `result` (string), `original` (number) |
| `format.percentage` | Format numbers as percentages | `value` number *(required)*, `is_ratio` boolean (default: `True`), `decimal_places` number (default: `1`), `include_sign` boolean (default: `False`) | `result` (string), `original` (number), `numeric` (number) |

## hash

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `hash.sha256` | Calculate SHA-256 cryptographic hash of text | `text` text *(required)*, `encoding` string (default: `utf-8`) | `hash` (string), `algorithm` (string) |
| `hash.sha512` | Calculate SHA-512 cryptographic hash of text | `text` text *(required)*, `encoding` string (default: `utf-8`) | `hash` (string), `algorithm` (string) |

## http

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `http.get` | Send HTTP GET request to an API endpoint | `url` string *(required)*, `headers` object (default: `{}`), `query` object (default: `{}`), `timeout` number (default: `30`) | `ok` (boolean), `status` (number), `body` (any), `headers` (object) |
| `http.request` | Send HTTP request and receive response | `url` string *(required)*, `method` string (default: `GET`), `headers` object (default: `{}`), `body` any, `query` object (default: `{}`), `content_type` string (default: `application/json`), `auth` object, `timeout` number (default: `30`), `follow_redirects` boolean (default: `True`), `verify_ssl` boolean (default: `True`), `response_type` string (default: `auto`) | `ok` (boolean), `status` (number), `status_text` (string), `headers` (object), `body` (any), `url` (string), `duration_ms` (number), `content_type` (string), `content_length` (number) |
| `http.response_assert` | Assert and validate HTTP response properties | `response` object *(required)*, `status` any, `body_contains` any, `body_not_contains` any, `body_matches` string *(required)*, `json_path` object, `json_path_exists` array, `header_contains` object, `content_type` string (default: ``), `max_duration_ms` number, `schema` object, `fail_fast` boolean (default: `False`) | `ok` (boolean), `passed` (number), `failed` (number), `total` (number), `assertions` (array), `errors` (array) |

## image

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `image.compress` | Compress images to reduce file size while maintaining quality | `input_path` string *(required)*, `output_path` string, `quality` number (default: `85`), `optimize` boolean (default: `True`), `max_size_kb` number, `format` string (default: `png`) | `output_path` (string), `original_size_bytes` (number), `compressed_size_bytes` (number), `compression_ratio` (number) |
| `image.convert` | Convert image to different format (PNG, JPEG, WEBP, etc.) | `input_path` string *(required)*, `output_path` string, `format` string *(required)*, `quality` number (default: `85`), `resize` object | `path` (string), `size` (number), `format` (string), `dimensions` (object) |
| `image.download` | Download image from URL to local file | `url` string *(required)*, `output_path` string, `output_dir` string (default: `/tmp`), `headers` object (default: `{}`), `timeout` number (default: `30`) | `path` (string), `size` (number), `content_type` (string), `filename` (string) |
| `image.qrcode_generate` | Generate QR codes from text, URLs, or data | `data` string *(required)*, `output_path` string, `size` number (default: `300`), `color` string (default: `#000000`), `background` string (default: `#FFFFFF`), `error_correction` select (default: `M`), `logo_path` string | `output_path` (string), `file_size` (number), `dimensions` (object) |
| `image.resize` | Resize images to specified dimensions with various algorithms | `input_path` string *(required)*, `output_path` string, `width` number, `height` number, `scale` number, `algorithm` string (default: `lanczos`), `maintain_aspect` boolean (default: `True`) | `output_path` (string), `original_size` (object), `new_size` (object) |

## llm

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `llm.agent` | Autonomous AI agent with multi-port connections (model, memory, tools) | `prompt_source` select (default: `manual`), `task` string, `prompt_path` string (default: `{{input}}`), `join_strategy` select (default: `first`), `join_separator` string (default: `\n\n---\n\n`), `max_input_size` number (default: `10000`), `system_prompt` string (default: `You are a helpful AI agent....`), `tools` array (default: `[]`), `context` object (default: `{}`), `max_iterations` number (default: `10`), `provider` string (default: `openai`), `model` string (default: `gpt-4o`), `temperature` number (default: `0.3`), `api_key` string, `base_url` string | `ok` (boolean), `result` (string), `steps` (array), `tool_calls` (number), `tokens_used` (number) |
| `llm.chat` | Interact with LLM APIs for intelligent operations | `prompt` string *(required)*, `system_prompt` string, `context` object, `messages` array, `provider` string (default: `openai`), `model` string (default: `gpt-4o`), `temperature` number (default: `0.7`), `max_tokens` number (default: `2000`), `response_format` string (default: `text`), `api_key` string, `base_url` string | `ok` (boolean), `response` (string), `parsed` (any), `model` (string), `tokens_used` (number), `finish_reason` (string) |
| `llm.code_fix` | Automatically generate code fixes based on issues | `issues` array *(required)*, `source_files` array *(required)*, `fix_mode` string (default: `suggest`), `backup` boolean (default: `True`), `context` string, `model` string (default: `gpt-4o`), `api_key` string | `ok` (boolean), `fixes` (array), `applied` (array), `failed` (array), `summary` (string) |

## logic

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `logic.and` | Perform logical AND operation | `values` array *(required)* | `result` (boolean), `true_count` (number), `total_count` (number) |
| `logic.contains` | Check if a value contains another value | `haystack` text *(required)*, `needle` text *(required)*, `case_sensitive` boolean (default: `True`) | `result` (boolean), `position` (number), `count` (number) |
| `logic.equals` | Check if two values are equal | `a` text *(required)*, `b` text *(required)*, `strict` boolean (default: `False`), `case_sensitive` boolean (default: `True`) | `result` (boolean), `type_a` (string), `type_b` (string) |
| `logic.not` | Perform logical NOT operation | `value` boolean *(required)* | `result` (boolean), `original` (boolean) |
| `logic.or` | Perform logical OR operation | `values` array *(required)* | `result` (boolean), `true_count` (number), `total_count` (number) |

## math

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `math.abs` | Get absolute value of a number | `number` number *(required)* | `result` (number), `original` (number) |
| `math.calculate` | Perform basic mathematical operations | `operation` string *(required)*, `a` number *(required)*, `b` number, `precision` number (default: `2`) | `result` (number), `operation` (string), `expression` (string) |
| `math.ceil` | Round number up to nearest integer | `number` number *(required)* | `result` (number), `original` (number) |
| `math.floor` | Round number down to nearest integer | `number` number *(required)* | `result` (number), `original` (number) |
| `math.power` | Raise number to a power | `base` number *(required)*, `exponent` number *(required)* | `result` (number), `base` (number), `exponent` (number) |
| `math.round` | Round number to specified decimal places | `number` number *(required)*, `decimals` number (default: `0`) | `result` (number), `original` (number), `decimals` (number) |

## meta

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `meta.modules.generate` | Generate new module from specification | — | `status` (string), `message` (string), `module_id` (string), `description` (string) |
| `meta.modules.list` | List all available modules in the registry | `category` string, `tags` array, `include_params` boolean (default: `True`), `include_output` boolean (default: `True`), `format` select (default: `json`) | `modules` (array), `count` (number), `formatted` (string) |
| `meta.modules.test_generator` | Test module generation capability | — | `status` (string), `message` (string), `spec_received` (boolean) |
| `meta.modules.update_docs` | Generate or update MODULES.md documentation from registry | `output_path` string (default: `docs/MODULES.md`), `include_examples` boolean (default: `True`) | `file_path` (string), `modules_count` (number), `categories` (array) |

## notification

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `notification.discord.send_message` | Send message to Discord via webhook | `webhook_url` string, `content` string *(required)*, `username` string, `avatar_url` string | `status` (string), `sent` (boolean), `message` (string) |
| `notification.email.send` | Send email via SMTP | `smtp_server` string *(required)*, `smtp_port` number (default: `587`), `username` string *(required)*, `password` string *(required)*, `from_email` string *(required)*, `to_email` string *(required)*, `subject` string *(required)*, `body` text *(required)*, `html` boolean (default: `False`) | `status` (string), `sent` (boolean), `message` (string) |
| `notification.slack.send_message` | Send message to Slack via webhook | `webhook_url` string, `text` string *(required)*, `channel` string, `username` string, `icon_emoji` string | `status` (string), `sent` (boolean), `message` (string) |
| `notification.telegram.send_message` | Send message via Telegram Bot API | `bot_token` string, `chat_id` string *(required)*, `text` string *(required)*, `parse_mode` select (default: `Markdown`) | `status` (string), `sent` (boolean), `message_id` (number), `message` (string) |

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
| `object.keys` | Get all keys from an object | `object` json *(required)* | `keys` (array), `count` (number) |
| `object.merge` | Merge multiple objects into one | `objects` array *(required)* | `result` (json) |
| `object.omit` | Omit specific keys from an object | `object` json *(required)*, `keys` array *(required)* | `result` (json) |
| `object.pick` | Pick specific keys from an object | `object` json *(required)*, `keys` array *(required)* | `result` (json) |
| `object.set` | Set value in object by path | `object` object *(required)*, `path` string *(required)*, `value` any *(required)* | `result` (object) |
| `object.unflatten` | Unflatten object with dot notation to nested | `object` object *(required)*, `separator` string (default: `.`) | `result` (object) |
| `object.values` | Get all values from an object | `object` json *(required)* | `values` (array), `count` (number) |

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
| `pdf.generate` | Generate PDF files from HTML content or text | `content` string *(required)*, `output_path` string *(required)*, `title` string, `author` string, `page_size` string (default: `A4`), `orientation` string (default: `portrait`), `margin` number (default: `20`), `header` string, `footer` string | `output_path` (string), `page_count` (number), `file_size_bytes` (number) |
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
| `process.stop` | Stop a running background process | `process_id` string, `name` string, `pid` number, `signal` string (default: `SIGTERM`), `timeout` number (default: `10`), `force` boolean (default: `False`), `stop_all` boolean (default: `False`) | `ok` (boolean), `stopped` (array), `failed` (array), `count` (number) |

## productivity

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `productivity.airtable.create` | Create a new record in Airtable table | `api_key` string, `base_id` string *(required)*, `table_name` string *(required)*, `fields` json *(required)* | `id` (string), `createdTime` (string), `fields` (json) |
| `productivity.airtable.read` | Read records from Airtable table | `api_key` string, `base_id` string *(required)*, `table_name` string *(required)*, `view` string, `max_records` number (default: `100`) | `records` (array), `count` (number) |
| `productivity.airtable.update` | Update an existing record in Airtable table | `api_key` string, `base_id` string *(required)*, `table_name` string *(required)*, `record_id` string *(required)*, `fields` json *(required)* | `id` (string), `fields` (json) |

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
| `regex.extract` | Extract named groups from text | `text` text *(required)*, `pattern` string *(required)*, `ignore_case` boolean (default: `False`) | `extracted` (object), `matched` (boolean), `full_match` (string) |
| `regex.match` | Find all matches of a pattern in text | `text` text *(required)*, `pattern` string *(required)*, `ignore_case` boolean (default: `False`), `first_only` boolean (default: `False`) | `matches` (array), `count` (number), `groups` (array) |
| `regex.replace` | Replace pattern matches in text | `text` text *(required)*, `pattern` string *(required)*, `replacement` string *(required)*, `ignore_case` boolean (default: `False`), `count` number (default: `0`) | `result` (string), `replacements` (number), `original` (string) |
| `regex.split` | Split text by a regex pattern | `text` text *(required)*, `pattern` string *(required)*, `ignore_case` boolean (default: `False`), `max_split` number (default: `0`), `remove_empty` boolean (default: `False`) | `result` (array), `count` (number) |
| `regex.test` | Test if string matches a regex pattern | `text` text *(required)*, `pattern` string *(required)*, `ignore_case` boolean (default: `False`), `full_match` boolean (default: `False`) | `result` (boolean), `pattern` (string) |

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
| `shell.exec` | Execute a shell command and capture output | `command` string *(required)*, `cwd` string, `env` object, `timeout` number (default: `300`), `shell` boolean (default: `False`), `capture_stderr` boolean (default: `True`), `encoding` string (default: `utf-8`), `raise_on_error` boolean (default: `False`) | `ok` (boolean), `exit_code` (number), `stdout` (string), `stderr` (string), `command` (string), `cwd` (string), `duration_ms` (number) |

## slack

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `slack.send` | Send messages to Slack channels via incoming webhook | `message` string *(required)*, `webhook_url` string, `channel` string, `username` string, `icon_emoji` string, `blocks` array, `attachments` array | `sent` (boolean) |

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

## stealth

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `stealth.fingerprint` |  | `action` string (default: `generate`), `fingerprint_id` string, `platform` string (default: `windows`) | `action` (string), `fingerprint` (object), `fingerprint_id` (string) |
| `stealth.launch` |  | `browser` string (default: `chromium`), `headless` boolean (default: `False`), `proxy` string, `fingerprint_mode` string (default: `random`), `locale` string (default: `en-US`), `timezone` string | `browser_id` (string), `fingerprint` (object), `browser_type` (string), `headless` (boolean) |

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
| `string.pad` | Pad a string to a specified length | `text` text *(required)*, `length` number *(required)*, `pad_char` string (default: ` `), `position` string (default: `end`) | `result` (string), `original` (string), `added` (number) |
| `string.replace` | Replace occurrences of a substring in a string | `text` string *(required)*, `search` string *(required)*, `replace` string *(required)* | `result` (string), `original` (string), `search` (string), `replace` (string), `status` (string) |
| `string.reverse` | Reverse the characters in a string | `text` string *(required)* | `result` (string), `original` (string), `length` (number) |
| `string.slugify` | Convert text to URL-friendly slug | `text` text *(required)*, `separator` string (default: `-`), `lowercase` boolean (default: `True`), `max_length` number (default: `0`) | `result` (string), `original` (string) |
| `string.split` | Split a string into an array using a delimiter | `text` string *(required)*, `delimiter` string (default: ` `) | `parts` (array), `result` (array), `length` (number), `original` (string), `delimiter` (string), `status` (string) |
| `string.template` | Render a template with variable substitution | `template` text *(required)*, `variables` object *(required)*, `missing_value` string (default: ``), `preserve_missing` boolean (default: `False`) | `result` (string), `replaced` (number), `missing` (array) |
| `string.titlecase` | Convert string to title case | `text` string *(required)* | `result` (string) |
| `string.trim` | Remove whitespace from both ends of a string | `text` string *(required)* | `result` (string), `original` (string), `status` (string) |
| `string.truncate` | Truncate a string to a maximum length | `text` text *(required)*, `length` number *(required)*, `suffix` string (default: `...`), `word_boundary` boolean (default: `False`) | `result` (string), `original` (string), `truncated` (boolean), `removed` (number) |
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

## verify

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `verify.annotate` | Draw labeled bounding boxes on screenshots to mark differences | `image_path` string *(required)*, `annotations` array *(required)*, `output_path` string | `output_path` (string), `annotation_count` (integer) |
| `verify.capture` | Capture computed styles from browser element | `url` string *(required)*, `selector` string *(required)*, `wait_for` string, `viewport_width` integer (default: `1280`), `viewport_height` integer (default: `800`) | `element` (object), `found` (boolean) |
| `verify.compare` | Compare captured styles with expected values | `actual` object *(required)*, `expected` object *(required)*, `selector` string, `size_tolerance` number (default: `2.0`), `spacing_tolerance` number (default: `2.0`), `font_size_tolerance` number (default: `1.0`), `color_tolerance` integer (default: `5`), `check_typography` boolean (default: `True`), `check_colors` boolean (default: `True`), `check_spacing` boolean (default: `True`), `check_sizing` boolean (default: `False`) | `passed` (boolean), `violations` (array), `error_count` (integer), `warning_count` (integer) |
| `verify.figma` | Fetch design tokens from Figma API (token stays local) | `file_id` string *(required)*, `node_id` string, `node_name` string, `token` string | `node` (object), `style` (object) |
| `verify.report` | Generate verification report in HTML/JSON/Markdown | `results` array *(required)*, `name` string (default: `verify-report`), `url` string, `format` string (default: `html`), `output_dir` string (default: `./verify-reports`), `screenshots` array | `report_path` (string), `summary` (object) |
| `verify.ruleset` | Load verification rules from YAML file | `path` string *(required)* | `ruleset` (object), `rules_count` (integer) |
| `verify.run` | Run full design verification: capture → compare → report | `url` string *(required)*, `selectors` array, `ruleset_path` string, `expected_styles` object, `figma_file_id` string, `figma_token` string, `figma_mapping` object, `output_dir` string (default: `./verify-reports`), `report_format` string (default: `html`), `take_screenshot` boolean (default: `True`), `viewport_width` integer (default: `1280`), `viewport_height` integer (default: `800`) | `passed` (boolean), `summary` (object), `report_path` (string) |
| `verify.spec` | Dynamic spec verification - compose any modules via YAML | `ruleset_path` string, `ruleset` object | `passed` (boolean), `summary` (object), `results` (array) |
| `verify.visual_diff` | Compare reference design with dev site visually, annotate differences | `reference_url` string *(required)*, `dev_url` string *(required)*, `output_dir` string (default: `./verify-reports/visual-diff`), `focus_areas` array, `viewport_width` integer (default: `1280`), `viewport_height` integer (default: `800`), `model` string (default: `gpt-4o`), `api_key` string | `similarity_score` (number), `annotations` (array), `annotated_image` (string), `report_path` (string), `summary` (string) |

## vision

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `vision.analyze` | Analyze images using OpenAI Vision API (GPT-4V) | `image` string *(required)*, `prompt` string *(required)*, `analysis_type` string (default: `general`), `context` string, `output_format` string (default: `structured`), `model` string (default: `gpt-4o`), `max_tokens` number (default: `1000`), `api_key` string *(required)*, `header_name` string (default: `X-API-Key`), `detail` string (default: `high`) | `ok` (boolean), `analysis` (string), `structured` (object), `model` (string), `tokens_used` (number) |
| `vision.compare` | Compare two images and identify visual differences | `image_before` string *(required)*, `image_after` string *(required)*, `comparison_type` string (default: `visual_regression`), `threshold` number (default: `5`), `focus_areas` array, `ignore_areas` array, `model` string (default: `gpt-4o`), `api_key` string *(required)*, `header_name` string (default: `X-API-Key`) | `ok` (boolean), `has_differences` (boolean), `similarity_score` (number), `differences` (array), `summary` (string), `recommendation` (string) |

## webhook

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `webhook.trigger` | Send HTTP POST request to a webhook URL | `url` string *(required)*, `method` string (default: `POST`), `payload` object, `headers` object (default: `{}`), `content_type` string (default: `application/json`), `auth_token` string, `timeout` number (default: `30`) | `status_code` (number), `response` (object), `headers` (object) |

## word

| Module | Description | Parameters | Output |
|--------|-------------|------------|--------|
| `word.parse` | Extract text and content from Word documents (.docx) | `file_path` string *(required)*, `extract_tables` boolean (default: `True`), `extract_images` boolean (default: `False`), `images_output_dir` string, `preserve_formatting` boolean (default: `False`) | `text` (string), `paragraphs` (array), `tables` (array), `images` (array), `metadata` (object) |
| `word.to_pdf` | Convert Word documents (.docx) to PDF files | `input_path` string *(required)*, `output_path` string, `method` select (default: `auto`) | `output_path` (string), `file_size` (number), `method_used` (string) |
