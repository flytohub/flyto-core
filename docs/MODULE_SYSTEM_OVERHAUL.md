# Flyto-Core 模組系統全面整改方案

> **版本**: 1.0.0
> **日期**: 2026-01-07
> **狀態**: 核准執行

本文件為 flyto-core 模組系統的完整整改藍圖，涵蓋安全性、可靠性、一致性、前端整合等所有面向。

---

## 目錄

1. [執行摘要](#1-執行摘要)
2. [現狀分析](#2-現狀分析)
3. [核心設計原則](#3-核心設計原則)
4. [P0 立即止血](#4-p0-立即止血)
5. [P1 統一規格](#5-p1-統一規格)
6. [P2 平台化](#6-p2-平台化)
7. [安全性修復清單](#7-安全性修復清單)
8. [前端整合規範](#8-前端整合規範)
9. [工具與自動化](#9-工具與自動化)
10. [遷移策略](#10-遷移策略)
11. [附錄](#11-附錄)
12. [國際化架構 (i18n)](#12-國際化架構-i18n)

---

## 1. 執行摘要

### 1.1 審計結論

| 維度 | 等級 | 發現問題數 | 狀態 |
|------|------|-----------|------|
| 安全性 | B | 5 個高危 | ✅ 已修復 |
| 可靠性 | B | 13 個問題 | ✅ 已修復 |
| 一致性 | C | 35+ 個問題 | 🔄 進行中 |
| 文件完整性 | B- | 6 個缺口 | 🔄 進行中 |
| 前端整合 | D | 8 個缺失 | ⏳ 待開始 |

### 1.2 關鍵決策

| 決策項目 | 決定 | 理由 |
|----------|------|------|
| 模組實作模式 | **Function-first** | 更原子化、可測、可組合 |
| 回傳格式 | **統一由 Runtime 封裝** | 避免模組作者自訂協議 |
| 錯誤處理 | **ModuleError + Runtime 轉換** | 統一錯誤分類與格式 |
| Class 使用時機 | **僅限需要資源生命週期** | Browser session, DB connection |

### 1.3 實施時程

| 階段 | 時間 | 內容 |
|------|------|------|
| P0 止血 | Day 1-2 | 語法錯誤、Runtime 統一、Compile Gate |
| P1 規格 | Day 3-4 | 參數命名、Examples、Category 規則 |
| P2 平台 | Day 5-7 | REST API、Capabilities、Port Types |

---

## 2. 現狀分析

### 2.1 模組統計

```
總模組數: 200
├── Function-based: 106 (53%)
├── Class-based: 94 (47%)
├── 有 params_schema: 198 (99%)
├── 有 output_schema: 200 (100%)
├── 有完整 i18n: 188 (94%)
└── Schema 驗證通過: 200 (100%)
```

### 2.2 關鍵問題清單

#### 2.2.1 語法錯誤 [CRITICAL]

| 檔案 | 行數 | 問題 |
|------|------|------|
| `browser/extract.py` | 31 | 缺少逗號導致模組無法載入 |

```python
# ❌ 錯誤
can_connect_to=['browser.*', ...],    params_schema=compose(

# ✅ 正確
can_connect_to=['browser.*', ...],
params_schema=compose(
```

#### 2.2.2 回傳值格式不一致 [CRITICAL]

**發現 3 種不同模式:**

| 模式 | 模組範例 | 格式 |
|------|----------|------|
| Status Pattern | browser.click, data.json.parse | `{"status": "success", ...}` |
| OK Pattern | api.http_get, file.read | `{"ok": true, "data": ...}` |
| 混合 Pattern | 部分模組 | 兩種都有 |

**影響:**
- 呼叫者需要檢查不同欄位
- 無法統一錯誤處理
- 前端難以實作通用邏輯

#### 2.2.3 錯誤處理不一致 [CRITICAL]

**發現 4 種錯誤模式:**

```python
# 模式 A: OK Pattern (推薦)
{'ok': False, 'error': 'message', 'error_code': 'VALIDATION_ERROR'}

# 模式 B: Status Pattern
{'status': 'error', 'message': 'message'}  # 無 error_code

# 模式 C: 直接拋異常
raise ValueError("Missing required parameter")

# 模式 D: 混合
{'status': 'error', 'message': '...', 'text': None}  # 多餘欄位
```

**受影響檔案:**
- `data/json_parse.py` (lines 71-75 vs 84-87)
- `data/csv_read.py` (lines 97-101 vs 105-108)
- `file/read.py` (line 83-87)
- `element/text.py` (line 98, 104)

#### 2.2.4 參數命名不一致 [HIGH]

| 概念 | 變體 1 | 變體 2 | 變體 3 |
|------|--------|--------|--------|
| 文字輸入 | `text` | `json_string` | `data` |
| 檔案路徑 | `path` | `file_path` | - |
| 超時 | `timeout_ms` | `timeout` | `timeout_seconds` |
| 選擇器 | `selector` | `css_selector` | `xpath` |

**受影響檔案:**
- `string/split.py` (line 72: `text`)
- `data/json_parse.py` (line 68: `json_string`)
- `file/read.py` (line 47: `path`)
- `data/csv_read.py` (line 91: `file_path`)

#### 2.2.5 Class vs Function 混用 [HIGH]

| 類別 | 實作模式 | 錯誤處理 |
|------|----------|----------|
| browser.* | Class-based | 拋異常 |
| data.* | Function-based | 返回 `{ok: false}` |
| string.* | Function-based | 返回 `{ok: false}` |
| math.* | Function-based | 返回 `{ok: false}` |
| api.* | Function-based | 返回 `{ok: false}` |
| file.* | Function-based | 返回 `{ok: false}` |
| database.* | Function-based | 返回 `{ok: false}` |

**問題:** 呼叫者無法統一處理錯誤

#### 2.2.6 連線規則與類型不匹配 [HIGH]

```python
# 問題範例: 宣告接受所有，但實際只能處理特定類型
@register_module(
    can_receive_from=['*'],      # 宣稱接受任何輸入
    input_types=['browser'],     # 實際只能處理 browser
)
```

**影響:**
- UI 無法正確顯示可連線模組
- LLM 生成錯誤的 workflow
- Runtime 無法驗證連線合法性

#### 2.2.7 Category 與 module_id 不匹配 [MEDIUM]

**發現 53 個模組有此問題:**

```python
@register_module(
    module_id='email.send',      # 暗示 category='email'
    category='communication'      # 但設為 communication
)
```

**受影響模組範例:**
- `email.send` → category='communication'
- `slack.send` → category='communication'
- `telegram.send` → category='communication'

#### 2.2.8 output_schema 缺少描述 [MEDIUM]

**301 個欄位缺少 description:**

```python
# ❌ 缺少描述
output_schema={
    'status': {'type': 'string'},
    'selector': {'type': 'string'}
}

# ✅ 完整描述
output_schema={
    'status': {'type': 'string', 'description': 'Operation status'},
    'selector': {'type': 'string', 'description': 'CSS selector used'}
}
```

#### 2.2.9 Examples 格式不一致 [MEDIUM]

**發現 3 種格式:**

```python
# 格式 A
examples=[{'name': '...', 'params': {...}}]

# 格式 B
examples=[{'title': '...', 'params': {...}}]

# 格式 C (完整)
examples=[{'title': '...', 'title_key': '...', 'params': {...}}]
```

#### 2.2.10 硬編碼值 [MEDIUM]

| 檔案 | 行數 | 值 | 問題 |
|------|------|-----|------|
| `browser/goto.py` | 90 | `'domcontentloaded'` | 應為常數 |
| `api/http_get.py` | 32 | `timeout=60` | 應可配置 |
| `email_send.py` | 101 | `587` | SMTP port 硬編碼 |
| `llm/chat.py` | 133-134 | `'gpt-4o'`, `0.7`, `2000` | 應為常數 |

---

## 3. 核心設計原則

### 3.1 Function-First 原則

> **模組執行介面統一為 Function signature**
> **Class 僅作為實作細節，用於需要資源生命週期的場景**

#### 為什麼 Function 更原子化?

| 優勢 | 說明 |
|------|------|
| **介面天然小** | 只有 params, context, return |
| **容易純函數** | 同輸入 → 同輸出，可測可快照 |
| **統一封裝簡單** | return data，runtime 包 `{ok, data}` |
| **易於 lint/規範化** | 靜態掃描 decorator metadata |

#### Class 使用時機

僅限以下場景:
- 瀏覽器 session (page/context)
- 長連線 (DB / websocket)
- 需要 cache 或資源復用 (大模型、embedding client)
- 需要 teardown (close browser, release file handle)

### 3.2 統一回傳協議原則

> **Runtime 是唯一的協議出口**
> **模組作者不決定回傳格式**

#### 模組作者只允許兩種行為:

1. **return 任意 data** → Runtime 包成 `{ok: true, data: ...}`
2. **raise ModuleError** → Runtime 包成 `{ok: false, error: ..., error_code: ...}`

#### 禁止行為:

- ❌ 模組自己回 `{ok: ...}` 當作協議 (會 double wrap)
- ❌ 模組自己回 `{status: ...}`
- ❌ 直接 raise 原生異常 (除非是真的 bug)

### 3.3 命名一致性原則

> **建立 Canonical Param Names 字典**
> **Runtime 自動 normalize aliases**

```yaml
# params_vocabulary.yml
canonical_names:
  text: string           # 文字輸入
  path: file_path        # 檔案路徑
  url: url               # URL
  timeout_ms: number     # 超時 (毫秒)
  selector: string       # CSS/XPath 選擇器
  headers: object        # HTTP headers
  payload: object        # 請求 body
  encoding: string       # 編碼

aliases:
  file_path: path
  json_string: text
  timeout: timeout_ms
  timeout_seconds: timeout_ms
  css_selector: selector
```

### 3.4 類型相容性原則

> **連線規則必須與類型宣告一致**
> **Runtime 驗證連線合法性**

```python
# 正確: 類型與連線規則一致
@register_module(
    input_types=['browser_page'],
    can_receive_from=['browser.*'],
)

# 錯誤: 宣稱接受所有，但類型限制
@register_module(
    input_types=['browser_page'],
    can_receive_from=['*'],  # ❌ 與 input_types 矛盾
)
```

---

## 4. P0 立即止血

### 4.1 修復語法錯誤

**檔案:** `src/core/modules/atomic/browser/extract.py`

```python
# 修復前 (line 31)
can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(

# 修復後
can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],
params_schema=compose(
```

### 4.2 建立 Compile Gate

**目的:** 避免語法錯誤導致整個 catalog 載入失敗

**CI 腳本:** `.github/workflows/module-lint.yml`

```yaml
name: Module Lint
on: [push, pull_request]

jobs:
  compile-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Python syntax check
        run: python -m compileall src/core/modules

      - name: Module lint
        run: python -m flyto_core.cli module-lint --strict
```

### 4.3 統一 Runtime Output

#### 4.3.1 定義 ModuleResult 結構

```python
# src/core/modules/result.py

from dataclasses import dataclass
from typing import Any, Optional, Dict


@dataclass
class ModuleResult:
    """統一的模組執行結果"""
    ok: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            'ok': self.ok,
            'data': self.data,
            'error': self.error,
            'error_code': self.error_code,
        }
        if self.meta:
            result['meta'] = self.meta
        return result

    @classmethod
    def success(cls, data: Any, meta: Optional[Dict] = None) -> 'ModuleResult':
        return cls(ok=True, data=data, meta=meta)

    @classmethod
    def failure(cls, error: str, error_code: str, meta: Optional[Dict] = None) -> 'ModuleResult':
        return cls(ok=False, error=error, error_code=error_code, meta=meta)
```

#### 4.3.2 定義 ModuleError 異常

```python
# src/core/modules/errors.py

class ModuleError(Exception):
    """模組執行錯誤的基類"""

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        field: Optional[str] = None,
        hint: Optional[str] = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.field = field
        self.hint = hint

    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'message': self.message,
            'details': self.details,
            'field': self.field,
            'hint': self.hint,
        }


# 預定義錯誤類型
class ValidationError(ModuleError):
    """參數驗證錯誤"""
    def __init__(self, message: str, field: str = None, **kwargs):
        super().__init__('VALIDATION_ERROR', message, field=field, **kwargs)


class ConfigMissingError(ModuleError):
    """配置缺失錯誤"""
    def __init__(self, message: str, **kwargs):
        super().__init__('CONFIG_MISSING', message, **kwargs)


class TimeoutError(ModuleError):
    """超時錯誤"""
    def __init__(self, message: str, **kwargs):
        super().__init__('TIMEOUT', message, **kwargs)


class NetworkError(ModuleError):
    """網路錯誤"""
    def __init__(self, message: str, **kwargs):
        super().__init__('NETWORK_ERROR', message, **kwargs)


class AuthError(ModuleError):
    """認證錯誤"""
    def __init__(self, message: str, **kwargs):
        super().__init__('AUTH_ERROR', message, **kwargs)


class RateLimitedError(ModuleError):
    """限流錯誤"""
    def __init__(self, message: str, **kwargs):
        super().__init__('RATE_LIMITED', message, **kwargs)


class NotFoundError(ModuleError):
    """資源不存在錯誤"""
    def __init__(self, message: str, **kwargs):
        super().__init__('NOT_FOUND', message, **kwargs)


class UnsupportedError(ModuleError):
    """不支援的操作"""
    def __init__(self, message: str, **kwargs):
        super().__init__('UNSUPPORTED', message, **kwargs)
```

#### 4.3.3 錯誤碼規範

| 錯誤碼 | 說明 | HTTP 對應 |
|--------|------|-----------|
| `VALIDATION_ERROR` | 參數驗證失敗 | 400 |
| `CONFIG_MISSING` | 缺少必要配置 | 400 |
| `AUTH_ERROR` | 認證失敗 | 401 |
| `FORBIDDEN` | 權限不足 | 403 |
| `NOT_FOUND` | 資源不存在 | 404 |
| `RATE_LIMITED` | 請求過於頻繁 | 429 |
| `TIMEOUT` | 操作超時 | 408 |
| `NETWORK_ERROR` | 網路連線錯誤 | 502 |
| `UNSUPPORTED` | 不支援的操作 | 501 |
| `INTERNAL_ERROR` | 內部錯誤 | 500 |

#### 4.3.4 Runtime Wrapper 實作

```python
# src/core/modules/runtime.py

import time
import traceback
from typing import Any, Callable, Dict
from .result import ModuleResult
from .errors import ModuleError


async def execute_module(
    module_fn: Callable,
    params: Dict[str, Any],
    context: Dict[str, Any],
    module_id: str,
    timeout_ms: int = 30000
) -> ModuleResult:
    """
    統一的模組執行入口

    所有模組都透過此函式執行，確保:
    1. 回傳格式統一
    2. 錯誤處理統一
    3. 超時控制
    4. 執行追蹤
    """
    start_time = time.time()
    request_id = context.get('request_id', 'unknown')

    meta = {
        'module_id': module_id,
        'request_id': request_id,
    }

    try:
        # 執行模組
        result = await asyncio.wait_for(
            module_fn({'params': params, **context}),
            timeout=timeout_ms / 1000
        )

        # 計算執行時間
        duration_ms = int((time.time() - start_time) * 1000)
        meta['duration_ms'] = duration_ms

        # 處理回傳值
        # 如果模組回傳的是舊格式 (有 ok 或 status)，進行兼容處理
        if isinstance(result, dict):
            if 'ok' in result:
                # 舊 OK pattern - 直接使用
                return ModuleResult(
                    ok=result.get('ok', True),
                    data=result.get('data', result),
                    error=result.get('error'),
                    error_code=result.get('error_code'),
                    meta=meta
                )
            elif 'status' in result and result.get('status') == 'error':
                # 舊 Status pattern - 轉換
                return ModuleResult(
                    ok=False,
                    error=result.get('message', 'Unknown error'),
                    error_code=result.get('error_code', 'EXECUTION_ERROR'),
                    meta=meta
                )

        # 新格式: 直接當作 data
        return ModuleResult.success(result, meta=meta)

    except ModuleError as e:
        # 預期的模組錯誤
        duration_ms = int((time.time() - start_time) * 1000)
        meta['duration_ms'] = duration_ms

        return ModuleResult(
            ok=False,
            error=e.message,
            error_code=e.code,
            meta={**meta, 'details': e.details, 'field': e.field, 'hint': e.hint}
        )

    except asyncio.TimeoutError:
        # 超時
        duration_ms = int((time.time() - start_time) * 1000)
        meta['duration_ms'] = duration_ms

        return ModuleResult.failure(
            error=f'Module {module_id} timed out after {timeout_ms}ms',
            error_code='TIMEOUT',
            meta=meta
        )

    except Exception as e:
        # 未預期的錯誤
        duration_ms = int((time.time() - start_time) * 1000)
        meta['duration_ms'] = duration_ms
        meta['traceback'] = traceback.format_exc()  # 僅內部使用，不對外暴露

        logger.error(f"Module {module_id} failed: {e}", exc_info=True)

        return ModuleResult.failure(
            error=str(e),
            error_code='INTERNAL_ERROR',
            meta=meta
        )
```

---

## 5. P1 統一規格

### 5.1 參數命名規範

#### 5.1.1 Canonical Names 字典

**檔案:** `src/core/modules/schema/vocabulary.py`

```python
"""
參數命名規範字典

所有模組應使用 canonical names，Runtime 會自動 normalize aliases。
"""

# Canonical parameter names
PARAM_VOCABULARY = {
    # === 基礎輸入 ===
    'text': {
        'type': 'string',
        'description': 'Text content to process',
        'aliases': ['content', 'input', 'value', 'json_string', 'html_string']
    },
    'path': {
        'type': 'string',
        'format': 'path',
        'description': 'File system path',
        'aliases': ['file_path', 'filepath', 'file', 'filename']
    },
    'url': {
        'type': 'string',
        'format': 'url',
        'description': 'URL address',
        'aliases': ['uri', 'endpoint', 'link', 'href']
    },

    # === 時間相關 ===
    'timeout_ms': {
        'type': 'number',
        'description': 'Timeout in milliseconds',
        'aliases': ['timeout', 'timeout_seconds', 'wait_time']
    },
    'delay_ms': {
        'type': 'number',
        'description': 'Delay in milliseconds',
        'aliases': ['delay', 'wait', 'sleep']
    },

    # === 選擇器 ===
    'selector': {
        'type': 'string',
        'description': 'CSS or XPath selector',
        'aliases': ['css_selector', 'xpath', 'query', 'element']
    },

    # === HTTP 相關 ===
    'headers': {
        'type': 'object',
        'description': 'HTTP headers',
        'aliases': ['http_headers', 'request_headers']
    },
    'payload': {
        'type': 'object',
        'description': 'Request body payload',
        'aliases': ['body', 'data', 'request_body', 'json_body']
    },
    'method': {
        'type': 'string',
        'description': 'HTTP method',
        'aliases': ['http_method', 'request_method']
    },

    # === 編碼相關 ===
    'encoding': {
        'type': 'string',
        'default': 'utf-8',
        'description': 'Character encoding',
        'aliases': ['charset', 'character_encoding']
    },

    # === 資料庫相關 ===
    'query': {
        'type': 'string',
        'description': 'SQL query string',
        'aliases': ['sql', 'sql_query', 'statement']
    },
    'table': {
        'type': 'string',
        'description': 'Database table name',
        'aliases': ['table_name', 'tablename']
    },

    # === 認證相關 ===
    'api_key': {
        'type': 'string',
        'format': 'password',
        'description': 'API key for authentication',
        'aliases': ['apikey', 'key', 'token', 'access_token']
    },
    'username': {
        'type': 'string',
        'description': 'Username for authentication',
        'aliases': ['user', 'login', 'account']
    },
    'password': {
        'type': 'string',
        'format': 'password',
        'description': 'Password for authentication',
        'aliases': ['pass', 'pwd', 'secret']
    },
}


def normalize_param_name(name: str) -> str:
    """將 alias 轉換為 canonical name"""
    for canonical, config in PARAM_VOCABULARY.items():
        if name == canonical:
            return canonical
        if name in config.get('aliases', []):
            return canonical
    return name  # 保持原樣如果不在字典中


def get_param_config(name: str) -> dict:
    """取得參數的標準配置"""
    canonical = normalize_param_name(name)
    return PARAM_VOCABULARY.get(canonical, {'type': 'string'})
```

#### 5.1.2 Lint 規則

```python
# scripts/lint_params.py

def check_param_naming(module_metadata: dict) -> List[LintIssue]:
    """檢查參數命名是否符合規範"""
    issues = []
    params_schema = module_metadata.get('params_schema', {})

    for param_name in params_schema.keys():
        canonical = normalize_param_name(param_name)
        if canonical != param_name:
            issues.append(LintIssue(
                severity='WARNING',
                message=f"Parameter '{param_name}' should use canonical name '{canonical}'",
                fix=f"Rename '{param_name}' to '{canonical}'"
            ))

    return issues
```

### 5.2 Examples 統一格式

#### 5.2.1 標準格式定義

```python
# Example 標準結構
{
    "id": "basic",              # 唯一識別符
    "title": "Basic usage",     # 顯示標題
    "title_key": "modules.xxx.examples.basic.title",  # i18n key
    "description": "...",       # 可選: 詳細說明
    "params": {                 # 執行參數
        "url": "https://example.com"
    },
    "expected": {               # 可選: 預期結果 (用於測試)
        "ok": True
    }
}
```

#### 5.2.2 遷移腳本

```python
# scripts/migrate_examples.py

def migrate_example(old_example: dict) -> dict:
    """將舊格式 example 轉換為新格式"""
    new_example = {
        'id': old_example.get('id', slugify(old_example.get('name') or old_example.get('title'))),
        'title': old_example.get('title') or old_example.get('name'),
        'params': old_example.get('params', {}),
    }

    # 添加 title_key 如果存在
    if 'title_key' in old_example:
        new_example['title_key'] = old_example['title_key']

    # 添加 expected 如果存在
    if 'expected_output' in old_example:
        new_example['expected'] = old_example['expected_output']

    return new_example
```

### 5.3 Category 與 Namespace 規則

#### 5.3.1 兩層分類系統

```python
# 分類規則
{
    "namespace": "從 module_id 第一段來 (API stable contract)",
    "category": "UI 展示用分類 (可調整)"
}

# 範例
{
    "module_id": "email.send",
    "namespace": "email",           # 自動從 module_id 提取
    "category": "communication",    # UI 顯示分類
}
```

#### 5.3.2 規則說明

| 項目 | 規則 | 用途 |
|------|------|------|
| `module_id` | API stable contract，不可隨意更改 | 程式呼叫、權限控制 |
| `namespace` | 從 module_id 第一段自動提取 | 權限策略、capability |
| `category` | 可調整的 UI 分類 | 前端展示、搜尋分組 |

#### 5.3.3 Lint 警告

```python
def check_category_consistency(module_metadata: dict) -> List[LintIssue]:
    """檢查 category 與 module_id 的一致性"""
    issues = []

    module_id = module_metadata.get('module_id', '')
    category = module_metadata.get('category', '')
    namespace = module_id.split('.')[0] if module_id else ''

    if namespace != category:
        issues.append(LintIssue(
            severity='INFO',
            message=f"Category '{category}' differs from namespace '{namespace}'",
            hint="This is allowed for UI grouping, but ensure it's intentional"
        ))

    return issues
```

### 5.4 output_schema 描述自動補全

#### 5.4.1 常見欄位模板

```python
# 自動補全模板
OUTPUT_FIELD_TEMPLATES = {
    'ok': 'Whether the operation was successful',
    'status': 'Operation status',
    'data': 'Result data',
    'result': 'Operation result',
    'error': 'Error message if failed',
    'error_code': 'Error code for programmatic handling',
    'message': 'Status message',
    'count': 'Number of items',
    'items': 'List of items',
    'rows': 'Database rows',
    'row_count': 'Number of rows affected',
    'columns': 'Column names',
    'url': 'URL address',
    'path': 'File path',
    'content': 'Content data',
    'text': 'Text content',
    'html': 'HTML content',
    'json': 'JSON data',
    'selector': 'Element selector',
    'screenshot': 'Screenshot data',
    'duration_ms': 'Execution duration in milliseconds',
    'timestamp': 'Timestamp of the operation',
}

def auto_fill_description(field_name: str) -> str:
    """自動生成欄位描述"""
    if field_name in OUTPUT_FIELD_TEMPLATES:
        return OUTPUT_FIELD_TEMPLATES[field_name]
    return f"(auto) {field_name}"
```

#### 5.4.2 批次修復腳本

```python
# scripts/fix_output_descriptions.py

import ast
import os

def fix_output_schema_descriptions(file_path: str) -> int:
    """為缺少描述的 output_schema 欄位添加描述"""
    # 讀取並解析檔案
    # 找出 output_schema 定義
    # 為缺少 description 的欄位添加
    # 回傳修復數量
    pass
```

---

## 6. P2 平台化

### 6.1 Catalog REST API

#### 6.1.1 API 端點設計

```python
# flyto-pro 或 flyto-cloud 實作

# GET /api/v1/catalog/outline
# 取得類別大綱 (約 500 tokens)
@app.get("/api/v1/catalog/outline")
async def get_catalog_outline():
    """
    Returns category-level summary for initial UI loading.

    Response:
    {
        "categories": {
            "browser": {
                "label": "Browser Automation",
                "description": "Control browser, navigate pages...",
                "count": 12,
                "icon": "Globe",
                "color": "#3B82F6"
            },
            ...
        }
    }
    """
    from core.catalog import get_outline
    return get_outline()


# GET /api/v1/catalog/categories/{category}
# 取得類別內所有模組 (約 500-2000 tokens)
@app.get("/api/v1/catalog/categories/{category}")
async def get_category_modules(category: str, include_params: bool = False):
    """
    Returns all modules in a category.

    Response:
    {
        "modules": [
            {
                "module_id": "browser.launch",
                "label": "Launch Browser",
                "description": "Start a new browser instance",
                "can_be_start": true,
                "input_types": [],
                "output_types": ["browser_context"]
            },
            ...
        ]
    }
    """
    from core.catalog import get_category_detail
    return get_category_detail(category, include_params=include_params)


# GET /api/v1/catalog/modules/{module_id}
# 取得完整模組詳情
@app.get("/api/v1/catalog/modules/{module_id:path}")
async def get_module_detail(module_id: str):
    """
    Returns complete module metadata.
    """
    from core.catalog import get_module_detail
    return get_module_detail(module_id)


# POST /api/v1/catalog/search
# 搜尋模組
@app.post("/api/v1/catalog/search")
async def search_modules(
    query: str,
    category: Optional[str] = None,
    limit: int = 20
):
    """
    Search modules by keyword.
    """
    from core.catalog import search_modules
    return search_modules(query, category=category, limit=limit)


# POST /api/v1/catalog/batch
# 批次取得模組
@app.post("/api/v1/catalog/batch")
async def get_modules_batch(module_ids: List[str]):
    """
    Get multiple modules in one request.
    """
    from core.catalog import get_modules_batch
    return get_modules_batch(module_ids)
```

#### 6.1.2 安全視圖

**Public View (給前端/第三方):**

```python
PUBLIC_FIELDS = [
    'module_id',
    'label', 'label_key',
    'description', 'description_key',
    'category', 'subcategory',
    'tags',
    'icon', 'color',
    'input_types', 'output_types',
    'can_receive_from', 'can_connect_to',
    'can_be_start',
    'params_schema',  # 去除敏感預設值
    'output_schema',
    'examples',       # 去除敏感資料
    'stability',
    'version',
    'timeout',
    'retryable',
    # 安全布林值
    'requires_credentials',
    'handles_sensitive_data',
    'required_permissions',
]

FORBIDDEN_FIELDS = [
    'internal_config',
    'connector_details',
    'default_credentials',
    'system_paths',
]
```

**Internal View (給執行器/管理):**

```python
INTERNAL_FIELDS = PUBLIC_FIELDS + [
    'execution_hints',
    'internal_defaults',
    'connector_config',
    'dangerous_flags',
]
```

### 6.2 Capabilities 系統

#### 6.2.1 Capability 定義

```python
# src/core/modules/capabilities.py

class Capability(Enum):
    """模組能力聲明"""

    # 網路相關
    NETWORK_PUBLIC = "network_public"      # 存取公開網路
    NETWORK_PRIVATE = "network_private"    # 存取內網
    NETWORK_LOCALHOST = "network_localhost" # 存取 localhost

    # 檔案系統
    FILESYSTEM_READ = "filesystem_read"    # 讀取檔案
    FILESYSTEM_WRITE = "filesystem_write"  # 寫入檔案
    FILESYSTEM_EXEC = "filesystem_exec"    # 執行檔案

    # 系統
    SHELL_EXEC = "shell_exec"              # 執行 shell 命令
    PROCESS_SPAWN = "process_spawn"        # 建立子程序

    # 敏感資料
    CREDENTIALS_ACCESS = "credentials_access"  # 存取憑證
    PII_ACCESS = "pii_access"                  # 存取個資

    # 外部服務
    CLOUD_STORAGE = "cloud_storage"        # 雲端儲存
    EMAIL_SEND = "email_send"              # 發送郵件
    PAYMENT = "payment"                    # 支付處理

    # 瀏覽器
    BROWSER_CONTROL = "browser_control"    # 控制瀏覽器
    DESKTOP_CONTROL = "desktop_control"    # 控制桌面


# 生產環境預設 policy
PRODUCTION_POLICY = {
    Capability.NETWORK_PRIVATE: False,
    Capability.NETWORK_LOCALHOST: False,
    Capability.FILESYSTEM_WRITE: True,  # 限制目錄
    Capability.SHELL_EXEC: False,
    Capability.DESKTOP_CONTROL: False,
}
```

#### 6.2.2 模組聲明 Capabilities

```python
@register_module(
    module_id='shell.exec',
    capabilities=[
        Capability.SHELL_EXEC,
        Capability.PROCESS_SPAWN,
        Capability.FILESYSTEM_EXEC,
    ],
    # ...
)
```

### 6.3 Port Type 系統

#### 6.3.1 Port 定義

```python
# src/core/modules/ports.py

@dataclass
class Port:
    """模組端口定義"""
    port_id: str                          # 唯一識別符
    direction: Literal['in', 'out']       # 方向
    data_type: str                        # 資料類型
    required: bool = True                 # 是否必要
    multiplicity: Literal['one', 'many'] = 'one'  # 一個或多個連線
    group: Optional[str] = None           # UI 分組
    label: Optional[str] = None           # 顯示標籤
    label_key: Optional[str] = None       # i18n key
    description: Optional[str] = None     # 說明
    semantics: Optional[str] = None       # 語意 (iterate/done/true/false)


# 標準資料類型
class DataType(Enum):
    ANY = "any"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    JSON = "json"
    FILE = "file"
    IMAGE = "image"
    BINARY = "binary"
    HTML = "html"
    TABLE = "table"

    # Browser 相關
    BROWSER_INSTANCE = "browser_instance"
    BROWSER_PAGE = "browser_page"
    BROWSER_ELEMENT = "browser_element"

    # AI 相關
    AI_MODEL = "ai_model"
    AI_MEMORY = "ai_memory"
    AI_TOOL = "ai_tool"

    # 認證相關
    CREDENTIAL = "credential"

    # HTTP 相關
    HTTP_RESPONSE = "http_response"
```

#### 6.3.2 類型相容性檢查

```python
def is_type_compatible(from_type: str, to_type: str) -> bool:
    """檢查類型是否相容"""
    # any 接受任何類型
    if to_type == 'any':
        return True

    # 完全匹配
    if from_type == to_type:
        return True

    # 繼承關係
    TYPE_HIERARCHY = {
        'string': ['any'],
        'number': ['any'],
        'boolean': ['any'],
        'object': ['any', 'json'],
        'array': ['any', 'json'],
        'json': ['any'],
        'browser_page': ['browser_instance'],
        'browser_element': ['browser_page'],
    }

    if from_type in TYPE_HIERARCHY:
        if to_type in TYPE_HIERARCHY[from_type]:
            return True

    return False
```

### 6.4 Module Spec Version

#### 6.4.1 版本定義

```python
# 目前支援的 spec version
CURRENT_SPEC_VERSION = "1.1"

SPEC_VERSIONS = {
    "1.0": {
        "features": ["basic_registration", "params_schema", "output_schema"],
        "deprecated_in": "2.0"
    },
    "1.1": {
        "features": ["ports", "capabilities", "node_type"],
        "current": True
    }
}
```

#### 6.4.2 模組聲明

```python
@register_module(
    module_id='example.module',
    spec_version='1.1',  # 聲明使用的 spec version
    # ...
)
```

### 6.5 副作用標記

#### 6.5.1 副作用定義

```python
@register_module(
    module_id='email.send',
    side_effects=['network', 'email'],   # 會產生的副作用
    deterministic=False,                  # 非確定性 (有網路呼叫)
    replayable=False,                     # 不可重放 (會真的發郵件)
    # ...
)
```

#### 6.5.2 副作用類型

| 副作用 | 說明 | 影響 |
|--------|------|------|
| `network` | 網路請求 | 不可離線執行 |
| `filesystem` | 檔案讀寫 | 可能改變系統狀態 |
| `email` | 發送郵件 | 不可重放 |
| `database` | 資料庫操作 | 可能改變資料 |
| `payment` | 支付處理 | 不可重放 |
| `notification` | 發送通知 | 不可重放 |

---

## 7. 安全性修復清單

### 7.1 已完成修復 ✅

| 項目 | 檔案 | 修復內容 |
|------|------|----------|
| API Key URL 暴露 | `constants.py`, `services.py` | 改用 HTTP header |
| 路徑穿越漏洞 | `file/read.py`, `file/write.py` | 添加 `validate_path_with_env_config()` |
| Shell 命令注入 | `shell/exec.py` | `use_shell` 預設改為 `False` |
| SQL 注入 | `database/insert.py`, `database/update.py` | 添加 `validate_sql_identifier()` |
| 裸 except 子句 | `document/word_to_pdf.py` | 改為具體異常類型 |
| SMTP 連線洩漏 | `communication/email_send.py` | 添加 `try/finally` |
| MySQL 連線洩漏 | `database/query.py`, `insert.py`, `update.py` | 添加 `await conn.ensure_closed()` |

### 7.2 安全工具函式

**檔案:** `src/core/utils.py`

```python
# 路徑穿越保護
validate_path_safe(path, base_dir=None)
validate_path_with_env_config(path)
class PathTraversalError(ValueError)

# SQL 注入保護
validate_sql_identifier(name, identifier_type)
validate_sql_identifiers(names, identifier_type)
class SQLInjectionError(ValueError)

# SSRF 保護 (已存在)
validate_url_ssrf(url, allow_private=False, allowed_hosts=None)
validate_url_with_env_config(url)
class SSRFError(ValueError)
```

### 7.3 環境變數配置

```bash
# 路徑安全
FLYTO_SANDBOX_DIR=/path/to/sandbox    # 限制檔案操作目錄
FLYTO_ALLOW_ABSOLUTE_PATHS=true       # 是否允許絕對路徑

# SSRF 保護
FLYTO_ALLOW_PRIVATE_NETWORK=false     # 是否允許內網存取
FLYTO_ALLOWED_HOSTS=api.example.com   # 允許的私有主機清單
```

---

## 8. 前端整合規範

### 8.1 API Response 格式

#### 8.1.1 成功回應

```json
{
    "ok": true,
    "data": {
        "module_id": "browser.click",
        "label": "Click Element",
        ...
    },
    "error": null,
    "error_code": null,
    "meta": {
        "request_id": "req_xxx",
        "duration_ms": 45
    }
}
```

#### 8.1.2 錯誤回應

```json
{
    "ok": false,
    "data": null,
    "error": "Module not found: browser.clicck",
    "error_code": "NOT_FOUND",
    "meta": {
        "request_id": "req_xxx",
        "hint": "Did you mean 'browser.click'?"
    }
}
```

### 8.2 TypeScript 類型定義

```typescript
// types/catalog.ts

interface ModuleResult<T = any> {
    ok: boolean;
    data: T | null;
    error: string | null;
    error_code: string | null;
    meta?: {
        request_id?: string;
        duration_ms?: number;
        hint?: string;
    };
}

interface ModuleMetadata {
    module_id: string;
    label: string;
    label_key: string;
    description: string;
    description_key: string;
    category: string;
    subcategory: string;
    tags: string[];
    icon: string;
    color: string;

    input_types: string[];
    output_types: string[];
    can_receive_from: string[];
    can_connect_to: string[];
    can_be_start: boolean;

    params_schema: Record<string, ParamField>;
    output_schema: Record<string, OutputField>;

    requires_credentials: boolean;
    handles_sensitive_data: boolean;
    required_permissions: string[];

    timeout?: number;
    retryable: boolean;
    max_retries?: number;

    examples: Example[];

    stability: 'stable' | 'beta' | 'experimental';
    version: string;
}

interface ParamField {
    type: string;
    label: string;
    label_key?: string;
    description: string;
    description_key?: string;
    required: boolean;
    default?: any;
    options?: Array<{value: string; label: string}>;
    validation?: {
        pattern?: string;
        min?: number;
        max?: number;
    };
    format?: string;
    advanced?: boolean;
    visibility?: 'default' | 'expert' | 'hidden';
    group?: 'basic' | 'connection' | 'options' | 'advanced';
}

interface OutputField {
    type: string;
    description: string;
}

interface Example {
    id: string;
    title: string;
    title_key?: string;
    description?: string;
    params: Record<string, any>;
    expected?: {
        ok: boolean;
    };
}
```

### 8.3 連線驗證邏輯

```typescript
// services/connectionValidator.ts

function canConnect(
    sourceModule: ModuleMetadata,
    targetModule: ModuleMetadata
): boolean {
    // Rule 1: Check explicit patterns
    const isExplicitlyAllowed = sourceModule.can_connect_to.some(pattern =>
        matchesPattern(targetModule.module_id, pattern)
    );

    if (isExplicitlyAllowed) return true;

    // Rule 2: Check type compatibility
    const hasMatchingType = sourceModule.output_types.some(outType =>
        targetModule.input_types.includes(outType) ||
        targetModule.input_types.includes('any')
    );

    return hasMatchingType;
}

function matchesPattern(moduleId: string, pattern: string): boolean {
    // Exact match
    if (pattern === moduleId) return true;

    // Universal wildcard
    if (pattern === '*') return true;

    // Category wildcard: browser.* matches browser.click
    if (pattern.endsWith('.*')) {
        const prefix = pattern.slice(0, -2);
        return moduleId.startsWith(prefix + '.');
    }

    return false;
}

function getCompatibleModules(
    sourceModule: ModuleMetadata,
    allModules: ModuleMetadata[],
    direction: 'predecessors' | 'successors'
): ModuleMetadata[] {
    if (direction === 'successors') {
        return allModules.filter(m => canConnect(sourceModule, m));
    } else {
        return allModules.filter(m => canConnect(m, sourceModule));
    }
}
```

### 8.4 安全注意事項

#### 8.4.1 絕對不要暴露給前端

```typescript
// ❌ 絕對不要暴露
- database passwords / connection strings
- API keys, tokens, credentials
- private SSH keys
- OAuth secrets
- internal file paths
- system commands
```

#### 8.4.2 敏感欄位處理

```typescript
// 顯示敏感模組的警告
function renderModuleWarning(module: ModuleMetadata) {
    if (module.requires_credentials) {
        return <Warning>This module requires credentials</Warning>;
    }
    if (module.handles_sensitive_data) {
        return <Warning>This module handles sensitive data</Warning>;
    }
    return null;
}

// 隱藏密碼欄位的值
function renderParamInput(param: ParamField, value: any) {
    if (param.format === 'password') {
        return <PasswordInput value="••••••••" />;
    }
    return <TextInput value={value} />;
}

// 發送前清除敏感資料
function sanitizeForLogging(params: Record<string, any>, schema: Record<string, ParamField>) {
    const sanitized = { ...params };
    for (const [key, config] of Object.entries(schema)) {
        if (config.format === 'password' || key.includes('password') || key.includes('secret')) {
            sanitized[key] = '***REDACTED***';
        }
    }
    return sanitized;
}
```

---

## 9. 工具與自動化

### 9.1 Module Lint 工具

**檔案:** `src/core/cli/lint.py`

```python
"""
flyto-core lint - 模組品質檢查工具

Usage:
    flyto-core lint [--strict] [--fix] [--category CATEGORY]

Options:
    --strict    將 WARNING 視為錯誤
    --fix       自動修復可修復的問題
    --category  只檢查特定類別
"""

class LintRule:
    """Lint 規則基類"""
    severity: str  # 'ERROR', 'WARNING', 'INFO'
    fixable: bool = False

    def check(self, module_metadata: dict) -> List[LintIssue]:
        raise NotImplementedError

    def fix(self, file_path: str, issue: LintIssue) -> bool:
        raise NotImplementedError


# 內建規則
LINT_RULES = [
    # 回傳格式
    ReturnFormatRule(),

    # 參數命名
    ParamNamingRule(),

    # Schema 完整性
    OutputSchemaDescriptionRule(),
    ParamsSchemaCompleteRule(),

    # 元資料
    I18nKeysRule(),
    ExamplesFormatRule(),
    CategoryConsistencyRule(),

    # 連線規則
    ConnectionRuleConsistencyRule(),
    TypeCompatibilityRule(),

    # 安全性
    CredentialExposureRule(),
    HardcodedValueRule(),
]
```

### 9.2 規則清單

| 規則 | 嚴重度 | 可修復 | 說明 |
|------|--------|--------|------|
| `syntax-error` | ERROR | N | 語法錯誤 |
| `return-format` | ERROR | N | 回傳格式不符規範 |
| `missing-output-schema` | ERROR | N | 缺少 output_schema |
| `missing-output-description` | WARNING | Y | output_schema 欄位缺少描述 |
| `param-naming` | WARNING | Y | 參數名稱應使用 canonical name |
| `missing-i18n-keys` | WARNING | Y | 缺少 i18n keys |
| `examples-format` | WARNING | Y | examples 格式不一致 |
| `category-mismatch` | INFO | N | category 與 module_id 不一致 |
| `type-connection-mismatch` | WARNING | N | 類型與連線規則不一致 |
| `hardcoded-value` | INFO | N | 發現硬編碼值 |
| `credential-exposure` | ERROR | N | 可能暴露憑證 |

### 9.3 CI 整合

**檔案:** `.github/workflows/quality.yml`

```yaml
name: Code Quality

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Compile check
        run: python -m compileall src/core/modules

      - name: Module lint
        run: flyto-core lint --strict

      - name: Schema validation
        run: python scripts/validate_schemas.py --strict

      - name: Run tests
        run: pytest tests/ -v
```

### 9.4 自動修復工具

```bash
# 修復所有可修復的問題
flyto-core lint --fix

# 只修復特定類別
flyto-core lint --fix --category browser

# 預覽將要修復的內容
flyto-core lint --fix --dry-run
```

---

## 10. 遷移策略

### 10.1 兼容舊模組

Runtime 會自動處理舊格式:

```python
# 舊格式 1: {ok: false, error: ...}
# → 直接使用

# 舊格式 2: {status: 'error', message: ...}
# → 轉換為 {ok: false, error: message, error_code: 'EXECUTION_ERROR'}

# 舊格式 3: raise ValueError
# → 轉換為 {ok: false, error: str(e), error_code: 'INTERNAL_ERROR'}
```

### 10.2 漸進式遷移

| 階段 | 時間 | 動作 |
|------|------|------|
| 階段 1 | 立即 | Runtime 兼容所有格式 |
| 階段 2 | v1.6 | Lint 警告舊格式 |
| 階段 3 | v1.7 | Lint 錯誤舊格式 (--strict) |
| 階段 4 | v2.0 | 移除兼容層 |

### 10.3 Legacy 欄位棄用

| 舊欄位 | 新欄位 | 棄用版本 | 移除版本 |
|--------|--------|----------|----------|
| `label` | `ui_label` | v1.6 | v2.0 |
| `description` | `ui_description` | v1.6 | v2.0 |
| `icon` | `ui_icon` | v1.6 | v2.0 |
| `color` | `ui_color` | v1.6 | v2.0 |
| `label_key` | `ui_label_key` | v1.6 | v2.0 |
| `description_key` | `ui_description_key` | v1.6 | v2.0 |

---

## 11. 附錄

### 11.1 完整錯誤碼表

| 錯誤碼 | 說明 | 建議處理 |
|--------|------|----------|
| `VALIDATION_ERROR` | 參數驗證失敗 | 檢查輸入參數 |
| `CONFIG_MISSING` | 缺少必要配置 | 檢查環境變數或配置檔 |
| `AUTH_ERROR` | 認證失敗 | 檢查憑證 |
| `FORBIDDEN` | 權限不足 | 檢查權限設定 |
| `NOT_FOUND` | 資源不存在 | 確認資源存在 |
| `RATE_LIMITED` | 請求過於頻繁 | 等待後重試 |
| `TIMEOUT` | 操作超時 | 增加超時或優化操作 |
| `NETWORK_ERROR` | 網路連線錯誤 | 檢查網路連線 |
| `UNSUPPORTED` | 不支援的操作 | 檢查參數或使用其他模組 |
| `INTERNAL_ERROR` | 內部錯誤 | 回報問題 |
| `PATH_TRAVERSAL` | 路徑穿越攻擊 | 檢查路徑參數 |
| `SQL_INJECTION` | SQL 注入攻擊 | 檢查 SQL 參數 |
| `SSRF` | SSRF 攻擊 | 檢查 URL 參數 |

### 11.2 資料類型對照表

| 類型 | 說明 | 可接受來源 |
|------|------|-----------|
| `any` | 任意類型 | 所有 |
| `string` | 字串 | string, any |
| `number` | 數字 | number, any |
| `boolean` | 布林 | boolean, any |
| `object` | 物件 | object, json, any |
| `array` | 陣列 | array, json, any |
| `json` | JSON | object, array, json, any |
| `file` | 檔案路徑 | file, string, any |
| `image` | 圖片 | image, file, binary, any |
| `binary` | 二進位 | binary, any |
| `html` | HTML | html, string, any |
| `table` | 表格資料 | table, array, any |
| `browser_instance` | 瀏覽器實例 | browser_instance |
| `browser_page` | 瀏覽器頁面 | browser_page, browser_instance |
| `browser_element` | 網頁元素 | browser_element, browser_page |

### 11.3 關鍵檔案索引

| 用途 | 路徑 |
|------|------|
| 模組註冊 Decorator | `src/core/modules/registry/decorators.py` |
| Schema 建構器 | `src/core/modules/schema/builders.py` |
| Schema 預設值 | `src/core/modules/schema/presets/` |
| Schema 驗證器 | `src/core/modules/schema_validator.py` |
| 基礎模組類別 | `src/core/modules/base.py` |
| 模組結果類別 | `src/core/modules/result.py` (新增) |
| 模組錯誤類別 | `src/core/modules/errors.py` (新增) |
| Runtime 執行器 | `src/core/modules/runtime.py` (新增) |
| 安全工具 | `src/core/utils.py` |
| 常數定義 | `src/core/constants.py` |
| Catalog API | `src/core/catalog/` |
| Lint 工具 | `src/core/cli/lint.py` (新增) |

### 11.4 環境變數清單

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `FLYTO_ENV` | 執行環境 | `development` |
| `FLYTO_SANDBOX_DIR` | 檔案操作沙箱目錄 | 無 |
| `FLYTO_ALLOW_ABSOLUTE_PATHS` | 允許絕對路徑 | `true` |
| `FLYTO_ALLOW_PRIVATE_NETWORK` | 允許內網存取 | `false` |
| `FLYTO_ALLOWED_HOSTS` | 允許的私有主機 | 無 |
| `FLYTO_MODULE_TIMEOUT_MS` | 預設模組超時 | `30000` |
| `FLYTO_LOG_LEVEL` | 日誌等級 | `INFO` |

### 11.5 參考文件

- [REGISTER_MODULE_GUIDE.md](./REGISTER_MODULE_GUIDE.md) - 模組開發入門
- [MODULE_SPECIFICATION.md](./MODULE_SPECIFICATION.md) - 命名規範
- [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) - 安全審計報告
- [CHANGELOG.md](../CHANGELOG.md) - 版本更新記錄

---

## 12. 國際化架構 (i18n)

### 12.1 設計原則

#### 12.1.1 現況問題

目前 description 有兩種寫法：
1. **label/description 有 key**: `label_key='modules.browser.click.label'`
2. **output_schema description 寫死英文**: `{'type': 'string', 'description': 'Operation status'}`

這導致：
- 無法翻譯 output_schema 欄位描述
- 語言包會越來越大，打包在 core 不合理
- 缺乏社群貢獻機制

#### 12.1.2 設計目標

| 目標 | 說明 |
|------|------|
| **按需下載** | 語言包不打包在 core，使用者選擇下載 |
| **社群擴展** | 開放使用者貢獻翻譯，但有品質管控 |
| **安全可控** | 純字串替換，不執行程式碼 |
| **向後相容** | 英文作為 fallback，沒有語言包也能運作 |

### 12.2 架構設計

#### 12.2.1 Key 格式規範

```
modules.{category}.{module_name}.{section}.{field}

範例:
- modules.browser.click.label                    # 模組標籤
- modules.browser.click.description              # 模組描述
- modules.browser.click.params.selector.label    # 參數標籤
- modules.browser.click.output.status.description # 輸出欄位描述
```

#### 12.2.2 output_schema 統一格式

```python
# ❌ 現在寫法（寫死英文）
output_schema={
    'status': {'type': 'string', 'description': 'Operation status'}
}

# ✅ 未來寫法（使用 key）
output_schema={
    'status': {
        'type': 'string',
        'description_key': 'modules.browser.click.output.status.description'
    }
}
```

#### 12.2.3 語言包結構

```
flyto-i18n/                           # 獨立 repo
├── locales/
│   ├── en/                           # 英文（基準包，必須完整）
│   │   ├── modules.browser.json      # browser 類別
│   │   ├── modules.flow.json         # flow 類別
│   │   ├── modules.data.json         # data 類別
│   │   └── common.json               # 共用詞彙
│   ├── zh-TW/                        # 繁體中文
│   │   ├── modules.browser.json
│   │   └── ...
│   ├── zh-CN/                        # 簡體中文
│   ├── ja/                           # 日文
│   └── ko/                           # 韓文
├── schema/
│   └── locale.schema.json            # JSON Schema 驗證格式
├── scripts/
│   ├── validate.py                   # 驗證腳本
│   └── sync-keys.py                  # 同步 key 腳本
└── README.md
```

#### 12.2.4 語言包 JSON 格式

```json
// locales/zh-TW/modules.browser.json
{
  "$schema": "../schema/locale.schema.json",
  "locale": "zh-TW",
  "category": "browser",
  "version": "1.0.0",
  "translations": {
    "modules.browser.click.label": "點擊元素",
    "modules.browser.click.description": "點擊頁面上的元素",
    "modules.browser.click.params.selector.label": "選擇器",
    "modules.browser.click.params.selector.description": "CSS 選擇器用於定位元素",
    "modules.browser.click.output.status.description": "操作狀態（成功/錯誤）"
  }
}
```

### 12.3 安全機制

#### 12.3.1 JSON Schema 驗證

```json
// schema/locale.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["locale", "category", "version", "translations"],
  "properties": {
    "locale": {
      "type": "string",
      "pattern": "^[a-z]{2}(-[A-Z]{2})?$"
    },
    "category": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9_]*$"
    },
    "translations": {
      "type": "object",
      "additionalProperties": {
        "type": "string",
        "maxLength": 500
      },
      "propertyNames": {
        "pattern": "^modules\\.[a-z_]+\\.[a-z_]+\\.[a-z_]+(\\.[a-z_]+)*$"
      }
    }
  },
  "additionalProperties": false
}
```

#### 12.3.2 安全規則

| 規則 | 說明 |
|------|------|
| **純字串** | 只允許字串值，不支援任何模板語法 |
| **長度限制** | 單一翻譯最長 500 字元 |
| **Key 白名單** | 只接受 `modules.*` 開頭的 key |
| **無程式碼** | 不解析任何表達式，純替換 |
| **Schema 驗證** | CI 自動驗證格式 |

### 12.4 Runtime 翻譯流程

```python
# src/core/i18n/translator.py

class Translator:
    """
    Runtime 翻譯器

    設計:
    - Lazy load: 按需載入語言包
    - Fallback: 找不到翻譯時用英文
    - Cache: LRU cache 避免重複載入
    """

    def __init__(self, locale: str = 'en'):
        self.locale = locale
        self.fallback = 'en'
        self._cache: Dict[str, Dict] = {}

    def translate(self, key: str) -> str:
        """
        翻譯 key 為目標語言

        Args:
            key: i18n key (e.g., 'modules.browser.click.label')

        Returns:
            翻譯後的字串，找不到時返回 key 本身
        """
        # 1. 嘗試目標語言
        result = self._lookup(key, self.locale)
        if result:
            return result

        # 2. Fallback 到英文
        if self.locale != self.fallback:
            result = self._lookup(key, self.fallback)
            if result:
                return result

        # 3. 返回 key 本身（開發時方便識別缺失翻譯）
        return key

    def resolve_schema(self, schema: Dict) -> Dict:
        """
        解析 schema 中的 description_key

        將 {'type': 'string', 'description_key': 'xxx'}
        轉換為 {'type': 'string', 'description': '翻譯結果'}
        """
        resolved = {}
        for field, spec in schema.items():
            resolved[field] = spec.copy()
            if 'description_key' in spec:
                resolved[field]['description'] = self.translate(spec['description_key'])
        return resolved
```

### 12.5 社群貢獻機制

#### 12.5.1 貢獻流程

```
1. Fork flyto-i18n repo
2. 新增/修改語言檔案
3. 本地執行 validate.py 確認格式
4. 提交 PR
5. CI 自動檢查:
   - JSON Schema 驗證
   - Key 完整性檢查（與 en 比對）
   - 字串長度檢查
6. Maintainer review
7. Merge & 發布新版本
```

#### 12.5.2 Key 同步工具

```python
# scripts/sync-keys.py

def sync_keys():
    """
    從 flyto-core 同步所有 i18n keys

    掃描所有 @register_module 並提取:
    - label_key
    - description_key
    - params_schema 中的 label_key, description_key
    - output_schema 中的 description_key

    生成缺失 key 報告供翻譯者參考
    """
    pass
```

#### 12.5.3 貢獻等級

| 等級 | 條件 | 權限 |
|------|------|------|
| **Contributor** | 首次貢獻 | 提交 PR |
| **Reviewer** | 5+ PR merged | 審核其他 PR |
| **Maintainer** | 20+ PR + 信任 | 直接 merge |

### 12.6 前端整合

#### 12.6.1 語言包載入 API

```typescript
// Frontend API

interface I18nService {
  // 設定語言
  setLocale(locale: string): Promise<void>;

  // 取得可用語言列表
  getAvailableLocales(): Promise<LocaleInfo[]>;

  // 下載語言包
  downloadLocale(locale: string, categories?: string[]): Promise<void>;

  // 翻譯
  t(key: string, fallback?: string): string;
}

// 使用範例
const i18n = useI18n();
await i18n.setLocale('zh-TW');
await i18n.downloadLocale('zh-TW', ['browser', 'flow']);

// 元件中使用
<span>{{ i18n.t('modules.browser.click.label') }}</span>
```

#### 12.6.2 Module Catalog API 整合

```typescript
// GET /api/modules/catalog?locale=zh-TW

// Response 會自動翻譯
{
  "modules": [
    {
      "id": "browser.click",
      "label": "點擊元素",           // 已翻譯
      "description": "點擊頁面上的元素", // 已翻譯
      "params_schema": {
        "selector": {
          "type": "string",
          "label": "選擇器",        // 已翻譯
          "description": "CSS 選擇器" // 已翻譯
        }
      },
      "output_schema": {
        "status": {
          "type": "string",
          "description": "操作狀態"  // 已翻譯
        }
      }
    }
  ]
}
```

### 12.7 Repo 架構

#### 12.7.1 命名與位置

```
flytohub/
├── flyto-core      # 模組核心 (Python)
├── flyto-pro       # AI 大腦 (Python)
├── flyto-cloud     # 前端部署 (Vue + FastAPI)
└── flyto-i18n      # 語言包 ← 新建立
```

**Repo 名稱: `flyto-i18n`**

命名理由：
- 與其他 repo 風格一致（flyto-xxx）
- `i18n` 是國際化標準縮寫（業界慣用）
- Vue, React, Angular 等框架都用這個命名

#### 12.7.2 flyto-i18n 完整結構

```
flyto-i18n/
├── locales/
│   ├── en/                           # 英文基準包（自動產生）
│   │   ├── modules.browser.json      # browser 類別
│   │   ├── modules.flow.json         # flow 類別
│   │   ├── modules.data.json         # data 類別
│   │   ├── modules.api.json          # api 類別
│   │   ├── modules.database.json     # database 類別
│   │   ├── modules.file.json         # file 類別
│   │   ├── modules.ai.json           # ai 類別
│   │   └── common.json               # 共用詞彙（error, success 等）
│   ├── zh-TW/                        # 繁體中文
│   ├── zh-CN/                        # 簡體中文
│   ├── ja/                           # 日文
│   ├── ko/                           # 韓文
│   ├── es/                           # 西班牙文
│   ├── fr/                           # 法文
│   └── de/                           # 德文
│
├── schema/
│   ├── locale.schema.json            # 單一語言檔驗證
│   └── manifest.schema.json          # 語言包 manifest 驗證
│
├── scripts/
│   ├── sync-from-core.py             # 從 flyto-core 同步 keys
│   ├── validate.py                   # 驗證所有翻譯
│   ├── coverage.py                   # 產生翻譯覆蓋率報告
│   ├── build.py                      # 打包發布
│   └── missing-keys.py               # 列出缺失翻譯
│
├── dist/                             # 編譯輸出（gitignore）
│   ├── flyto-i18n-en.json            # 合併後的單檔
│   ├── flyto-i18n-zh-TW.json
│   └── ...
│
├── .github/
│   └── workflows/
│       ├── validate.yml              # PR 驗證
│       ├── sync.yml                  # 定期從 core 同步
│       └── release.yml               # 發布到 CDN/npm
│
├── manifest.json                     # 語言包元資訊
├── CONTRIBUTING.md                   # 貢獻指南
├── README.md
└── LICENSE                           # MIT
```

#### 12.7.3 manifest.json 格式

```json
{
  "name": "flyto-i18n",
  "version": "1.0.0",
  "source_version": "flyto-core@2.0.0",
  "locales": {
    "en": {
      "name": "English",
      "native_name": "English",
      "coverage": 100,
      "status": "official"
    },
    "zh-TW": {
      "name": "Traditional Chinese",
      "native_name": "繁體中文",
      "coverage": 95,
      "status": "community",
      "maintainers": ["@user1", "@user2"]
    },
    "ja": {
      "name": "Japanese",
      "native_name": "日本語",
      "coverage": 60,
      "status": "in_progress"
    }
  }
}
```

### 12.8 完整工作流程

#### 12.8.1 開發流程（新增/修改模組）

```
┌─────────────────────────────────────────────────────────────┐
│  1. 開發者在 flyto-core 新增模組                              │
│     @register_module(                                        │
│         label_key='modules.browser.click.label',             │
│         description_key='modules.browser.click.description', │
│         ...                                                  │
│     )                                                        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  2. flyto-core CI 觸發 repository_dispatch 到 flyto-i18n    │
│     gh api repos/flytohub/flyto-i18n/dispatches \           │
│       -f event_type=sync-keys                                │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  3. flyto-i18n 執行 sync-from-core.py                        │
│     - Clone flyto-core                                       │
│     - 掃描所有 @register_module                               │
│     - 提取 label_key, description_key                        │
│     - 更新 en/ 基準包（英文從 description 取值）              │
│     - 產生新 keys 報告                                        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 自動建立 PR 更新 en/ 基準包                               │
│     - PR title: "sync: update keys from flyto-core@v2.0.1"  │
│     - 列出新增/移除的 keys                                    │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Maintainer review & merge                                │
└─────────────────────────────────────────────────────────────┘
```

#### 12.8.2 翻譯貢獻流程

```
┌─────────────────────────────────────────────────────────────┐
│  1. 貢獻者 Fork flyto-i18n                                   │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  2. 新增/修改語言檔案                                         │
│     locales/zh-TW/modules.browser.json                       │
│     {                                                        │
│       "modules.browser.click.label": "點擊元素",              │
│       "modules.browser.click.description": "點擊頁面元素"     │
│     }                                                        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  3. 本地驗證                                                 │
│     python scripts/validate.py --locale zh-TW                │
│     python scripts/coverage.py --locale zh-TW                │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 提交 PR                                                  │
│     PR template:                                             │
│     - [ ] 通過 validate.py                                   │
│     - [ ] 翻譯準確性自查                                      │
│     - [ ] 沒有機器翻譯痕跡                                    │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  5. CI 自動檢查                                              │
│     ✓ JSON Schema 驗證                                       │
│     ✓ Key 存在於 en/ 基準包                                  │
│     ✓ 無重複 key                                             │
│     ✓ 字串長度 <= 500                                        │
│     ✓ 無 HTML/JS 注入                                        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Native speaker review（該語言維護者審核）                 │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  7. Merge & 更新 coverage                                    │
│     manifest.json: zh-TW.coverage = 95%                      │
└─────────────────────────────────────────────────────────────┘
```

#### 12.8.3 前端載入流程

```
┌─────────────────────────────────────────────────────────────┐
│  1. 使用者開啟 flyto-cloud                                   │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  2. 偵測瀏覽器語言 / 使用者設定                               │
│     navigator.language → 'zh-TW'                             │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  3. 檢查本地快取                                             │
│     localStorage['flyto-i18n-zh-TW'] ?                       │
│     - 有且版本符合 → 直接使用                                 │
│     - 無或過期 → 下載                                        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 從 CDN 下載語言包                                        │
│     GET https://cdn.flyto2.net/i18n/zh-TW/latest.json       │
│     或按類別下載:                                            │
│     GET https://cdn.flyto2.net/i18n/zh-TW/modules.browser.json │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  5. 快取到 localStorage + 記錄版本                           │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  6. API 請求帶上 locale                                      │
│     GET /api/modules/catalog?locale=zh-TW                    │
│     → 後端用 Translator 翻譯後返回                           │
└─────────────────────────────────────────────────────────────┘
```

### 12.9 實施路線圖

| 階段 | 內容 | 產出 | 優先級 |
|------|------|------|--------|
| **Phase 1** | 建立 flyto-i18n repo | repo 結構、schema、README | P1 |
| **Phase 2** | 實作 sync-from-core.py | 自動提取 keys 腳本 | P1 |
| **Phase 3** | 產生 en/ 基準包 | 英文翻譯（從現有 description） | P1 |
| **Phase 4** | 設定 GitHub Actions | PR 驗證、自動同步 | P1 |
| **Phase 5** | flyto-core 加入 Translator | runtime 翻譯支援 | P2 |
| **Phase 6** | output_schema 改用 description_key | 模組遷移 | P2 |
| **Phase 7** | 開放社群貢獻 | CONTRIBUTING.md、PR template | P3 |
| **Phase 8** | 整合 flyto-cloud | 前端 i18n 服務 | P3 |
| **Phase 9** | 設定 CDN 發布 | 自動發布到 CDN | P3 |

### 12.10 關鍵決策

| 決策 | 選擇 | 理由 |
|------|------|------|
| 語言包位置 | 獨立 repo | 不增加 core 體積，可獨立版本控制 |
| 基準語言 | 英文 | 國際通用，作為 fallback |
| 翻譯格式 | JSON | 簡單、通用、易驗證 |
| Key 命名 | 點分隔層級 | 清晰、可讀、易於按類別載入 |
| 社群平台 | GitHub PR | 透明、可追蹤、易於審核 |

### 12.11 CDN 分發架構

使用者**不會**下載 flyto-i18n repo 到本地。語言包透過 CDN 分發。

#### 12.11.1 分發端點

```
# GitHub Releases (推薦)
https://github.com/flytohub/flyto-i18n/releases/download/v1.0.0/zh-TW.json

# jsDelivr CDN (自動從 GitHub 同步)
https://cdn.jsdelivr.net/gh/flytohub/flyto-i18n@v1.0.0/locales/zh-TW/modules.browser.json

# 自建 CDN (可選)
https://cdn.flyto2.net/i18n/v1.0.0/zh-TW/modules.browser.json
```

#### 12.11.2 版本管理

```
flyto-i18n releases:
├── v1.0.0/
│   ├── manifest.json           # 版本元資訊
│   ├── en.zip                  # 完整英文包
│   ├── zh-TW.zip               # 完整繁中包
│   └── categories/
│       ├── en/
│       │   ├── modules.browser.json
│       │   ├── modules.flow.json
│       │   └── ...
│       └── zh-TW/
│           └── ...
└── latest -> v1.0.0            # 指向最新穩定版
```

#### 12.11.3 前端載入策略

```typescript
// src/i18n/loader.ts

const CDN_BASE = 'https://cdn.jsdelivr.net/gh/flytohub/flyto-i18n';

interface LoadOptions {
  locale: string;
  version?: string;        // 預設 'latest'
  categories?: string[];   // 按需載入，預設全部
  cache?: boolean;         // 預設 true
}

async function loadI18n(options: LoadOptions): Promise<I18nBundle> {
  const { locale, version = 'latest', categories, cache = true } = options;

  // 1. 檢查 localStorage 快取
  const cacheKey = `flyto-i18n-${locale}-${version}`;
  if (cache) {
    const cached = localStorage.getItem(cacheKey);
    if (cached) {
      const data = JSON.parse(cached);
      if (data.version === version) {
        return data.bundle;
      }
    }
  }

  // 2. 從 CDN 載入
  const url = `${CDN_BASE}@${version}/dist/${locale}.json`;
  const response = await fetch(url);
  const bundle = await response.json();

  // 3. 快取
  if (cache) {
    localStorage.setItem(cacheKey, JSON.stringify({
      version,
      timestamp: Date.now(),
      bundle
    }));
  }

  return bundle;
}

// 按需載入（只載入 browser 類別）
async function loadCategory(locale: string, category: string): Promise<object> {
  const url = `${CDN_BASE}@latest/locales/${locale}/modules.${category}.json`;
  const response = await fetch(url);
  return response.json();
}
```

#### 12.11.4 Fallback 機制

```typescript
class I18nService {
  private bundles: Map<string, object> = new Map();
  private locale: string = 'en';

  async setLocale(locale: string): Promise<void> {
    try {
      // 嘗試載入目標語言
      const bundle = await loadI18n({ locale });
      this.bundles.set(locale, bundle);
      this.locale = locale;
    } catch (error) {
      console.warn(`Failed to load ${locale}, falling back to en`);
      // Fallback 到英文（內建或從 CDN）
      if (!this.bundles.has('en')) {
        const enBundle = await loadI18n({ locale: 'en' });
        this.bundles.set('en', enBundle);
      }
      this.locale = 'en';
    }
  }

  t(key: string): string {
    // 1. 嘗試目標語言
    const localBundle = this.bundles.get(this.locale);
    if (localBundle?.[key]) return localBundle[key];

    // 2. Fallback 到英文
    const enBundle = this.bundles.get('en');
    if (enBundle?.[key]) return enBundle[key];

    // 3. 返回 key 本身（方便識別缺失翻譯）
    return key;
  }
}
```

### 12.12 GitHub Actions 自動同步

#### 12.12.1 flyto-core → flyto-i18n 同步

當 flyto-core main 分支有變更時，自動提取 i18n keys 並同步到 flyto-i18n。

```yaml
# flyto-core/.github/workflows/sync-i18n.yml

name: Sync i18n Keys

on:
  push:
    branches: [main]
    paths:
      - 'src/core/modules/**/*.py'

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Extract i18n keys
        run: |
          python scripts/extract-i18n-keys.py --output /tmp/i18n-keys.json

      - name: Trigger flyto-i18n sync
        uses: peter-evans/repository-dispatch@v2
        with:
          token: ${{ secrets.FLYTO_I18N_TOKEN }}
          repository: flytohub/flyto-i18n
          event-type: sync-from-core
          client-payload: '{"ref": "${{ github.sha }}", "keys_url": "..."}'
```

```yaml
# flyto-i18n/.github/workflows/sync.yml

name: Sync from Core

on:
  repository_dispatch:
    types: [sync-from-core]
  workflow_dispatch:
    inputs:
      core_ref:
        description: 'flyto-core commit ref'
        required: false
        default: 'main'

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Checkout flyto-core
        uses: actions/checkout@v4
        with:
          repository: flytohub/flyto-core
          path: flyto-core
          ref: ${{ github.event.client_payload.ref || inputs.core_ref || 'main' }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Sync keys
        run: |
          python scripts/sync-from-core.py --core-path ./flyto-core

      - name: Check for changes
        id: changes
        run: |
          if git diff --quiet; then
            echo "changed=false" >> $GITHUB_OUTPUT
          else
            echo "changed=true" >> $GITHUB_OUTPUT
          fi

      - name: Create PR
        if: steps.changes.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v5
        with:
          title: "sync: update keys from flyto-core"
          body: |
            Auto-synced i18n keys from flyto-core.

            Triggered by: ${{ github.event.client_payload.ref || 'manual' }}
          branch: sync/core-keys
          commit-message: "sync: update keys from flyto-core"
```

#### 12.12.2 flyto-i18n 發布流程

```yaml
# flyto-i18n/.github/workflows/release.yml

name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Validate all locales
        run: python scripts/validate.py --strict

      - name: Build distribution
        run: |
          mkdir -p dist
          # 為每個 locale 打包
          for locale_dir in locales/*/; do
            locale=$(basename "$locale_dir")
            # 合併為單檔
            python scripts/build.py --locale $locale --output dist/${locale}.json
            # 打包 zip
            zip -r dist/flyto-i18n-${locale}-${{ github.ref_name }}.zip locales/$locale
          done
          # 全部打包
          zip -r dist/flyto-i18n-all-${{ github.ref_name }}.zip locales manifest.json

      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: dist/*
          generate_release_notes: true

      # 可選：同步到自建 CDN
      - name: Sync to CDN
        if: false  # 啟用時設為 true
        run: |
          aws s3 sync dist/ s3://cdn.flyto2.net/i18n/${{ github.ref_name }}/
```

### 12.13 flyto-core i18n Lint 規則

確保社群開發者遵守 i18n 規範。

#### 12.13.1 規則清單

| 規則 ID | 嚴重性 | 規則描述 |
|---------|--------|----------|
| CORE-I18N-001 | ERROR | `label_key` 必須符合格式 `modules.{category}.{name}.label` |
| CORE-I18N-002 | ERROR | `description_key` 必須符合格式 `modules.{category}.{name}.description` |
| CORE-I18N-003 | WARN | `label` fallback 必須存在（英文預設值） |
| CORE-I18N-004 | WARN | `description` fallback 必須存在 |
| CORE-I18N-005 | ERROR | params_schema 中的 `label_key` 必須符合 `modules.{category}.{name}.params.{param}.label` |
| CORE-I18N-006 | ERROR | output_schema 若使用 `description_key` 必須符合格式 |
| CORE-I18N-007 | INFO | 建議使用 `description_key` 而非硬編碼 `description` |

#### 12.13.2 規則實作

```python
# scripts/lint_i18n.py

import re
from pathlib import Path
from typing import List, Dict

I18N_KEY_PATTERN = re.compile(
    r'^modules\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*'
    r'(\.(label|description|params\.[a-z][a-z0-9_]*\.(label|description)|output\.[a-z][a-z0-9_]*\.description))?$'
)

class I18nLintRule:
    """Base class for i18n lint rules."""

    rule_id: str
    severity: str  # ERROR, WARN, INFO
    message: str

    def check(self, module_data: Dict) -> List[Dict]:
        """Return list of violations."""
        raise NotImplementedError


class LabelKeyFormatRule(I18nLintRule):
    rule_id = "CORE-I18N-001"
    severity = "ERROR"
    message = "label_key must match pattern: modules.{category}.{name}.label"

    def check(self, module_data: Dict) -> List[Dict]:
        violations = []
        label_key = module_data.get('label_key')

        if label_key:
            expected_pattern = f"modules.{module_data['category']}.{module_data['name']}.label"
            if label_key != expected_pattern:
                violations.append({
                    'rule': self.rule_id,
                    'severity': self.severity,
                    'message': f"{self.message}. Got: {label_key}, Expected: {expected_pattern}",
                    'file': module_data.get('file'),
                    'line': module_data.get('line')
                })

        return violations


class DescriptionKeyFormatRule(I18nLintRule):
    rule_id = "CORE-I18N-002"
    severity = "ERROR"
    message = "description_key must match pattern: modules.{category}.{name}.description"

    def check(self, module_data: Dict) -> List[Dict]:
        violations = []
        desc_key = module_data.get('description_key')

        if desc_key:
            expected_pattern = f"modules.{module_data['category']}.{module_data['name']}.description"
            if desc_key != expected_pattern:
                violations.append({
                    'rule': self.rule_id,
                    'severity': self.severity,
                    'message': f"{self.message}. Got: {desc_key}",
                    'file': module_data.get('file'),
                    'line': module_data.get('line')
                })

        return violations


class FallbackRequiredRule(I18nLintRule):
    rule_id = "CORE-I18N-003"
    severity = "WARN"
    message = "label fallback (English) should be provided"

    def check(self, module_data: Dict) -> List[Dict]:
        violations = []

        if module_data.get('label_key') and not module_data.get('label'):
            violations.append({
                'rule': self.rule_id,
                'severity': self.severity,
                'message': self.message,
                'file': module_data.get('file')
            })

        return violations


def run_i18n_lint(modules_dir: Path) -> List[Dict]:
    """Run all i18n lint rules on modules."""
    rules = [
        LabelKeyFormatRule(),
        DescriptionKeyFormatRule(),
        FallbackRequiredRule(),
    ]

    all_violations = []

    for py_file in modules_dir.rglob('*.py'):
        module_data = extract_module_data(py_file)
        if module_data:
            for rule in rules:
                violations = rule.check(module_data)
                all_violations.extend(violations)

    return all_violations
```

#### 12.13.3 CI 整合

```yaml
# flyto-core/.github/workflows/lint.yml

name: Lint

on: [push, pull_request]

jobs:
  i18n-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Run i18n lint
        run: |
          python scripts/lint_i18n.py --strict
          # --strict: ERROR 等級違規會導致 CI 失敗
```

#### 12.13.4 開發者指南

```python
# ✅ 正確寫法
@register_module(
    module_id="browser.click",
    category="browser",

    # i18n keys
    label_key="modules.browser.click.label",
    description_key="modules.browser.click.description",

    # Fallback (英文預設值，在語言包載入失敗時使用)
    label="Click Element",
    description="Click on an element in the page",

    params_schema={
        'selector': {
            'type': 'string',
            'label_key': 'modules.browser.click.params.selector.label',
            'label': 'Selector',  # Fallback
            'description_key': 'modules.browser.click.params.selector.description',
            'description': 'CSS selector for the element'  # Fallback
        }
    },

    output_schema={
        'success': {
            'type': 'boolean',
            'description_key': 'modules.browser.click.output.success.description',
            'description': 'Whether the click succeeded'  # Fallback
        }
    }
)
async def browser_click(selector: str, timeout: int = 5000) -> dict:
    ...
```

```python
# ❌ 錯誤寫法 - 會被 lint 擋下
@register_module(
    module_id="browser.click",

    # ERROR: label_key 格式錯誤
    label_key="browser.click.label",  # 缺少 modules. 前綴

    # ERROR: 與 module_id 不匹配
    description_key="modules.browser.tap.description",  # 應該是 click

    # WARN: 缺少 fallback
    # label="Click Element",  # 缺少
)
```

### 12.14 flyto-cloud 整合

flyto-cloud 前端如何載入和使用翻譯。

#### 12.14.1 Vue Plugin

```typescript
// src/plugins/i18n.ts

import { App, ref, computed } from 'vue';

const CDN_BASE = 'https://cdn.jsdelivr.net/gh/flytohub/flyto-i18n@latest';

interface I18nPlugin {
  locale: Ref<string>;
  t: (key: string) => string;
  setLocale: (locale: string) => Promise<void>;
  loadCategory: (category: string) => Promise<void>;
}

export function createI18n(): I18nPlugin {
  const locale = ref('en');
  const bundles = ref<Record<string, Record<string, string>>>({});

  async function setLocale(newLocale: string): Promise<void> {
    try {
      const response = await fetch(`${CDN_BASE}/dist/${newLocale}.json`);
      if (!response.ok) throw new Error(`Failed to load ${newLocale}`);
      bundles.value[newLocale] = await response.json();
      locale.value = newLocale;

      // 快取到 localStorage
      localStorage.setItem(`flyto-i18n-${newLocale}`, JSON.stringify(bundles.value[newLocale]));
    } catch (error) {
      console.warn(`Failed to load locale ${newLocale}, falling back to en`);
      if (newLocale !== 'en') {
        await setLocale('en');
      }
    }
  }

  async function loadCategory(category: string): Promise<void> {
    const url = `${CDN_BASE}/locales/${locale.value}/modules.${category}.json`;
    try {
      const response = await fetch(url);
      const data = await response.json();
      bundles.value[locale.value] = {
        ...bundles.value[locale.value],
        ...data.translations
      };
    } catch (error) {
      console.warn(`Failed to load category ${category}`);
    }
  }

  function t(key: string): string {
    // 1. 嘗試當前語言
    const localBundle = bundles.value[locale.value];
    if (localBundle?.[key]) return localBundle[key];

    // 2. Fallback 到英文
    const enBundle = bundles.value['en'];
    if (enBundle?.[key]) return enBundle[key];

    // 3. 返回 key
    return key;
  }

  return {
    locale,
    t,
    setLocale,
    loadCategory
  };
}

// Vue plugin
export default {
  install(app: App) {
    const i18n = createI18n();
    app.provide('i18n', i18n);
    app.config.globalProperties.$t = i18n.t;
  }
};
```

#### 12.14.2 組件使用

```vue
<template>
  <div class="module-card">
    <h3>{{ $t(module.label_key) || module.label }}</h3>
    <p>{{ $t(module.description_key) || module.description }}</p>

    <div v-for="(param, key) in module.params_schema" :key="key">
      <label>{{ $t(param.label_key) || param.label }}</label>
      <span class="hint">{{ $t(param.description_key) || param.description }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { inject, onMounted } from 'vue';

const i18n = inject('i18n');
const props = defineProps<{ module: ModuleInfo }>();

onMounted(async () => {
  // 按需載入該模組的類別翻譯
  await i18n.loadCategory(props.module.category);
});
</script>
```

#### 12.14.3 語言切換 UI

```vue
<template>
  <select v-model="currentLocale" @change="changeLocale">
    <option v-for="loc in availableLocales" :key="loc.code" :value="loc.code">
      {{ loc.native_name }} ({{ loc.coverage }}%)
    </option>
  </select>
</template>

<script setup lang="ts">
import { ref, inject, onMounted } from 'vue';

const i18n = inject('i18n');
const currentLocale = ref('en');
const availableLocales = ref([]);

onMounted(async () => {
  // 從 manifest 取得可用語言列表
  const response = await fetch('https://cdn.jsdelivr.net/gh/flytohub/flyto-i18n@latest/manifest.json');
  const manifest = await response.json();

  availableLocales.value = Object.entries(manifest.locales).map(([code, info]) => ({
    code,
    ...info
  }));

  // 偵測瀏覽器語言
  const browserLang = navigator.language;
  if (manifest.locales[browserLang]) {
    await changeLocale(browserLang);
  }
});

async function changeLocale(locale: string) {
  await i18n.setLocale(locale);
  currentLocale.value = locale;
}
</script>
```

---

## 變更歷史

| 版本 | 日期 | 變更內容 |
|------|------|----------|
| 1.0.0 | 2026-01-07 | 初始版本 |
| 1.1.0 | 2026-01-07 | 新增國際化架構 (i18n) 章節 |
| 1.2.0 | 2026-01-07 | 完善 i18n 工作流程、repo 架構、命名決策 |
| 1.3.0 | 2026-01-07 | 新增 CDN 分發架構、GitHub Actions 自動同步、i18n Lint 規則、flyto-cloud 整合 |

---

> **文件維護者**: Flyto2 Team
> **最後更新**: 2026-01-07
