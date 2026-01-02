# Flyto Core Validation API Plan

> Single Source of Truth: 所有驗證、規則、編排邏輯集中在 flyto-core
> Cloud/Pro 只做消費者，不做判斷

---

## 架構概覽

```
┌─────────────────────────────────────────────────────────────────┐
│                     flyto-core (PyPI 發布)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  modules/   │  │ validation/ │  │  catalog/   │              │
│  │  atomic     │  │  connection │  │  outline    │              │
│  │  composite  │  │  workflow   │  │  detail     │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                    pip install flyto-core
                         (熱更新下載)
                              │
           ┌──────────────────┴──────────────────┐
           ▼                                     ▼
┌─────────────────────┐               ┌─────────────────────┐
│    flyto-cloud      │               │     flyto-pro       │
│                     │               │                     │
│ from flyto_core     │               │ from flyto_core     │
│   .validation import│               │   .catalog import   │
│   validate_workflow │               │   get_outline       │
│                     │               │                     │
│  - 只負責渲染        │               │  - LLM 選擇用大綱    │
│  - 呼叫 validation  │               │  - 取得 module 細節  │
│  - 顯示錯誤          │               │  - 組裝 workflow    │
└─────────────────────┘               └─────────────────────┘
```

### 熱更新流程

```
1. flyto-core 發布新版到 PyPI (e.g., 1.7.0)
2. flyto-cloud / flyto-pro 檢測到新版本
3. 執行 pip install --upgrade flyto-core
4. 重新載入模組，獲得新的 validation/catalog API
```

### Import 方式

```python
# flyto-cloud backend
from core.validation import (
    validate_connection,
    validate_workflow,
    get_connectable,
    get_startable_modules,
)

# flyto-pro
from core.catalog import (
    get_outline,
    get_category_detail,
    get_module_detail,
)
```

---

## P0 必做（第一階段）

### 1. Module 起點規則 (`can_be_start`)

**目標**: 定義哪些 module 可以當流程起點

#### 1.1 更新 `@register_module` 裝飾器

```python
# src/core/modules/atomic/base/decorator.py

@register_module(
    module_id='flow.switch',
    # ... existing fields ...

    # 新增：起點規則
    can_be_start=False,  # switch 不能當起點
    start_requires_params=['condition'],  # 如果當起點，必須設定這些參數
)
```

#### 1.2 起點規則定義

| can_be_start | 說明 | 例子 |
|--------------|------|------|
| `True` | 可當起點 | `trigger.*`, `browser.launch`, `http.request` |
| `False` | 不能當起點 | `flow.switch`, `flow.merge`, `transform.*` |
| `None` (預設) | 自動推導：`input_types=[]` 或 `['*']` 時可當起點 |

#### 1.3 需要設定的 Modules

```python
# 不能當起點 (can_be_start=False)
- flow.switch
- flow.merge
- flow.filter
- flow.loop
- transform.*（需要輸入才能轉換）
- data.json.parse（需要輸入 string）

# 可當起點 (can_be_start=True)
- trigger.*
- browser.launch
- http.request（可以直接發請求）
- file.read
- database.query
```

---

### 2. Validation API (`src/core/validation/`)

#### 2.1 目錄結構

```
src/core/
├── modules/           # 現有 (atomic + composite)
├── validation/        # 新增
│   ├── __init__.py
│   ├── connection.py  # validate_connection, get_connectable
│   ├── workflow.py    # validate_workflow, validate_start
│   ├── errors.py      # 統一錯誤碼定義
│   └── index.py       # ConnectionIndex 預計算
└── catalog/           # 新增
    ├── __init__.py
    ├── outline.py     # get_outline
    ├── category.py    # get_category_detail
    └── module.py      # get_module_detail
```

#### 2.2 Connection Validation

```python
# src/core/validation/connection.py

from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class ConnectionResult:
    valid: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    meta: Optional[Dict] = None

def validate_connection(
    from_module_id: str,
    from_port: str,  # 'output' or specific port name
    to_module_id: str,
    to_port: str,    # 'input' or specific port name
) -> ConnectionResult:
    """
    驗證兩個 module 能否連接

    Returns:
        ConnectionResult with valid=True/False and error details

    Example:
        >>> validate_connection('browser.click', 'output', 'flow.switch', 'input')
        ConnectionResult(valid=True)

        >>> validate_connection('http.response', 'output', 'browser.click', 'input')
        ConnectionResult(
            valid=False,
            error_code='TYPE_MISMATCH',
            error_message='browser.click 需要 browser_page，但收到 http_response',
            meta={'expected': ['browser_page'], 'received': ['http_response']}
        )
    """
    pass

def get_connectable(
    module_id: str,
    direction: str = 'next',  # 'next' | 'prev'
    port: str = 'default',
    limit: int = 50,
    search: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Dict]:
    """
    取得某個 module 能連接的所有 modules

    Args:
        module_id: 當前 module
        direction: 'next' = 下游能接誰, 'prev' = 上游誰能接我
        port: 指定 port，預設為主要 port
        limit: 最多返回幾個
        search: 搜尋過濾
        category: 只返回特定 category

    Returns:
        [
            {
                'module_id': 'http.request',
                'label': 'HTTP Request',
                'category': 'http',
                'match_score': 1.0,  # 1.0=完全匹配, 0.5=可接受
            },
            ...
        ]
    """
    pass

def get_connectable_summary(
    module_id: str,
    direction: str = 'next',
) -> Dict[str, int]:
    """
    取得可連接的 modules 分類統計（給 UI 分組用）

    Returns:
        {
            'browser': 12,
            'http': 8,
            'data': 15,
            ...
        }
    """
    pass
```

#### 2.3 Workflow Validation

```python
# src/core/validation/workflow.py

from typing import List, Dict
from dataclasses import dataclass

@dataclass
class WorkflowError:
    code: str
    message: str
    path: str  # e.g., 'nodes[n1]', 'edges[e1]'
    meta: Dict = None

@dataclass
class WorkflowResult:
    valid: bool
    errors: List[WorkflowError]
    warnings: List[WorkflowError]  # 不阻擋但建議修復

def validate_workflow(
    nodes: List[Dict],
    edges: List[Dict],
) -> WorkflowResult:
    """
    驗證整個 workflow

    檢查項目:
    - 所有 edge 連接合法
    - 沒有孤島節點
    - 起點節點合法
    - 必填參數已設定
    - 沒有循環（除非是 loop module）

    Example:
        >>> validate_workflow(
        ...     nodes=[
        ...         {'id': 'n1', 'module_id': 'flow.switch'},  # 錯：switch 當起點
        ...         {'id': 'n2', 'module_id': 'http.request'},
        ...     ],
        ...     edges=[{'id': 'e1', 'source': 'n1', 'target': 'n2'}]
        ... )
        WorkflowResult(
            valid=False,
            errors=[
                WorkflowError(
                    code='INVALID_START_NODE',
                    message='flow.switch 不能當起點',
                    path='nodes[n1]',
                    meta={'module_id': 'flow.switch'}
                )
            ],
            warnings=[]
        )
    """
    pass

def validate_start(nodes: List[Dict], edges: List[Dict]) -> List[WorkflowError]:
    """只驗證起點是否合法"""
    pass

def get_startable_modules() -> List[Dict]:
    """返回所有可當起點的 modules"""
    pass
```

#### 2.4 統一錯誤碼

```python
# src/core/validation/errors.py

class ErrorCode:
    # Connection errors
    TYPE_MISMATCH = 'TYPE_MISMATCH'
    PORT_NOT_FOUND = 'PORT_NOT_FOUND'
    MAX_CONNECTIONS = 'MAX_CONNECTIONS'
    SELF_CONNECTION = 'SELF_CONNECTION'

    # Start node errors
    INVALID_START_NODE = 'INVALID_START_NODE'
    MISSING_START_PARAMS = 'MISSING_START_PARAMS'
    NO_START_NODE = 'NO_START_NODE'
    MULTIPLE_START_NODES = 'MULTIPLE_START_NODES'

    # Workflow errors
    ORPHAN_NODE = 'ORPHAN_NODE'
    CYCLE_DETECTED = 'CYCLE_DETECTED'
    MISSING_REQUIRED_PARAM = 'MISSING_REQUIRED_PARAM'
    INVALID_PARAM_VALUE = 'INVALID_PARAM_VALUE'

# 錯誤訊息模板（支援 i18n）
ERROR_MESSAGES = {
    'TYPE_MISMATCH': '{to_module} 需要 {expected}，但收到 {received}',
    'INVALID_START_NODE': '{module_id} 不能當起點',
    'ORPHAN_NODE': '節點 {node_id} 沒有連接到任何其他節點',
    # ...
}
```

#### 2.5 Connection Index（預計算）

```python
# src/core/validation/index.py

class ConnectionIndex:
    """
    預計算的連接索引，用於快速查詢
    在 module registry 載入完成後建立
    """

    _instance = None

    def __init__(self):
        # module_id -> [可連接的 module_ids]
        self.connectable_next: Dict[str, List[str]] = {}
        self.connectable_prev: Dict[str, List[str]] = {}

        # module_id -> {category: count}
        self.connectable_summary: Dict[str, Dict[str, int]] = {}

        # 起點 modules
        self.startable_modules: List[str] = []

    @classmethod
    def get_instance(cls) -> 'ConnectionIndex':
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._build()
        return cls._instance

    def _build(self):
        """
        從 ModuleRegistry 建立索引
        複雜度: O(n²) 但只執行一次
        """
        from ..modules.registry import ModuleRegistry

        all_modules = ModuleRegistry.get_all_metadata()

        for module_id, meta in all_modules.items():
            # 建立 connectable_next
            can_connect_to = meta.get('can_connect_to', ['*'])
            output_types = meta.get('output_types', [])

            connectable = []
            for other_id, other_meta in all_modules.items():
                if self._can_connect(meta, other_meta):
                    connectable.append(other_id)

            self.connectable_next[module_id] = connectable

            # 建立 startable_modules
            if self._can_be_start(meta):
                self.startable_modules.append(module_id)

    def _can_connect(self, from_meta: Dict, to_meta: Dict) -> bool:
        """判斷兩個 module 能否連接"""
        # 1. 檢查 can_connect_to / can_receive_from
        # 2. 檢查 output_types / input_types 相容性
        pass

    def _can_be_start(self, meta: Dict) -> bool:
        """判斷能否當起點"""
        # 明確設定 > 從 input_types 推導
        if 'can_be_start' in meta:
            return meta['can_be_start']

        input_types = meta.get('input_types', [])
        return len(input_types) == 0 or '*' in input_types
```

---

### 3. Catalog API (`src/core/catalog/`)

#### 3.1 Outline（大綱）

```python
# src/core/catalog/outline.py

def get_outline() -> Dict[str, Dict]:
    """
    返回 category 大綱，給 LLM 第一輪選擇

    Token 估算: ~500 tokens

    Returns:
        {
            'browser': {
                'label': 'Browser Automation',
                'description': 'Control browser, navigate, click, extract data',
                'count': 12,
                'subcategories': ['navigation', 'interaction', 'extraction'],
                'common_use_cases': ['Web scraping', 'Form filling', 'Screenshots']
            },
            'http': {
                'label': 'HTTP & API',
                'description': 'Make HTTP requests, handle REST/GraphQL APIs',
                'count': 8,
                'subcategories': ['request', 'response', 'auth'],
                'common_use_cases': ['API calls', 'Webhooks', 'Data fetching']
            },
            'data': {
                'label': 'Data Transform',
                'description': 'JSON, CSV, text processing and transformation',
                'count': 15,
                'subcategories': ['json', 'csv', 'text', 'convert'],
                'common_use_cases': ['Data parsing', 'Format conversion', 'Filtering']
            },
            'flow': {
                'label': 'Flow Control',
                'description': 'Conditionals, loops, branching, error handling',
                'count': 10,
                'subcategories': ['condition', 'loop', 'error'],
                'common_use_cases': ['Conditional logic', 'Iteration', 'Error recovery']
            },
            # ... more categories
        }
    """
    pass
```

#### 3.3 Category Detail（類別細節）

```python
# src/core/catalog/category.py

def get_category_detail(category: str) -> List[Dict]:
    """
    返回某 category 的所有 modules

    Token 估算: 每個 category 約 500-2000 tokens

    Args:
        category: 'browser', 'http', 'data', etc.

    Returns:
        [
            {
                'module_id': 'browser.launch',
                'label': 'Launch Browser',
                'description': 'Start a new browser instance',
                'input_types': [],
                'output_types': ['browser_context'],
                'params_summary': ['headless', 'browser_type'],
                'can_be_start': True,
                'common_next': ['browser.goto', 'browser.new_page']
            },
            {
                'module_id': 'browser.click',
                'label': 'Click Element',
                'description': 'Click on a webpage element by selector',
                'input_types': ['browser_page'],
                'output_types': ['browser_page'],
                'params_summary': ['selector', 'button', 'timeout'],
                'can_be_start': False,
                'common_prev': ['browser.goto', 'browser.wait']
            },
            ...
        ]
    """
    pass

def get_categories() -> List[str]:
    """返回所有 category 名稱"""
    pass
```

#### 3.4 Module Detail（單一 Module 完整資訊）

```python
# src/core/catalog/module.py

def get_module_detail(module_id: str) -> Dict:
    """
    返回單個 module 的完整資訊
    只在 LLM 確定要用這個 module 時才呼叫

    Returns:
        {
            'module_id': 'browser.click',
            'label': 'Click Element',
            'description': 'Click on a webpage element using CSS selector',

            # 完整參數定義
            'params_schema': {
                'selector': {
                    'type': 'string',
                    'required': True,
                    'label': 'CSS Selector',
                    'description': 'The CSS selector of the element to click',
                    'placeholder': '#submit-button',
                    'examples': ['#login', '.btn-primary', '[data-testid="submit"]']
                },
                'button': {
                    'type': 'string',
                    'required': False,
                    'default': 'left',
                    'options': ['left', 'right', 'middle'],
                    'label': 'Mouse Button'
                },
                'timeout': {
                    'type': 'number',
                    'required': False,
                    'default': 30000,
                    'label': 'Timeout (ms)'
                }
            },

            # 連接資訊
            'input_types': ['browser_page'],
            'output_types': ['browser_page'],
            'can_receive_from': ['browser.*'],
            'can_connect_to': ['browser.*', 'data.*'],
            'can_be_start': False,

            # 使用範例
            'examples': [
                {
                    'name': 'Click login button',
                    'params': {'selector': '#login-btn'},
                    'description': 'Click the login button on a page'
                }
            ]
        }
    """
    pass

def get_modules_batch(module_ids: List[str]) -> Dict[str, Dict]:
    """批量取得多個 modules 的詳細資訊"""
    pass
```

---

## P1 很快需要

### 4. Workflow Normalize（自動修復）

```python
# src/core/validation/normalize.py

def normalize_workflow(workflow: Dict) -> Dict:
    """
    自動修復 workflow

    功能:
    - 移除無效 edge（連接不存在的 node）
    - 補缺省欄位（id, position, etc.）
    - 舊版升級（migration）
    - 修復 port 名稱變更

    Returns:
        正規化後的 workflow
    """
    pass

def migrate_workflow(workflow: Dict, from_version: str, to_version: str) -> Dict:
    """版本升級"""
    pass
```

### 5. Explain Error（錯誤解釋）

```python
# src/core/validation/errors.py

def explain_error(code: str, meta: Dict, locale: str = 'en') -> Dict:
    """
    將錯誤碼轉換為人類可讀的訊息

    Args:
        code: 錯誤碼 e.g., 'TYPE_MISMATCH'
        meta: 錯誤上下文 e.g., {'expected': ['browser_page'], 'received': ['string']}
        locale: 語言 'en', 'zh-TW', 'zh-CN'

    Returns:
        {
            'title': 'Type Mismatch',
            'message': 'browser.click needs browser_page, but received string',
            'suggestion': 'Add a browser.launch node before browser.click',
            'docs_url': 'https://docs.flyto.dev/errors/TYPE_MISMATCH'
        }
    """
    pass
```

---

## P2 規模擴大後

### 6. Diff Validate（增量驗證）

```python
# src/core/validation/diff.py

def diff_validate(
    before: Dict,  # 修改前的 workflow
    after: Dict,   # 修改後的 workflow
) -> WorkflowResult:
    """
    只驗證變更的部分，不做全量驗證

    用於：拖一條線只檢查那條線
    """
    pass
```

### 7. Artifact Build（靜態產物）

```python
# src/core/catalog/build.py

def build_artifacts(output_dir: str):
    """
    編譯靜態 JSON 檔案，供 cloud 前端直接使用

    產出:
    - module_catalog.json      # 所有 module 基本資訊
    - connection_index.json    # 預計算的連接索引
    - category_outline.json    # 大綱
    - startable_modules.json   # 可當起點的 modules

    用途：
    - cloud 前端載入後可 0-call 即時提示「能不能連」
    - 真正 save/execute 仍由 core 做全量 validation
    """
    pass
```

---

## 實施 TODO List

### Phase 1: Core 基礎建設 (flyto-core)

- [ ] **1.1** 新增 `can_be_start` 到 `@register_module`
- [ ] **1.2** 更新所有 atomic modules 設定 `can_be_start`
  - [ ] `flow.*` → `can_be_start=False`
  - [ ] `transform.*` → `can_be_start=False`
  - [ ] `trigger.*` → `can_be_start=True`
  - [ ] `browser.launch` → `can_be_start=True`
- [ ] **1.3** 建立 `src/core/validation/` 目錄結構
- [ ] **1.4** 實作 `ConnectionIndex` 預計算
- [ ] **1.5** 實作 `validate_connection()`
- [ ] **1.6** 實作 `get_connectable()`
- [ ] **1.7** 實作 `validate_workflow()`
- [ ] **1.8** 實作 `validate_start()` + `get_startable_modules()`
- [ ] **1.9** 定義統一錯誤碼 `ErrorCode`
- [ ] **1.10** 建立 `src/core/catalog/` 目錄結構
- [ ] **1.11** 實作 `get_outline()`
- [ ] **1.12** 實作 `get_category_detail()`
- [ ] **1.13** 實作 `get_module_detail()`
- [ ] **1.14** 更新 `__init__.py` exports
- [ ] **1.15** 寫測試
- [ ] **1.16** Bump version, publish PyPI

### Phase 2: Cloud 接入 (flyto-cloud)

- [ ] **2.1** 移除 cloud 端的連接驗證邏輯
- [ ] **2.2** 移除 cloud 端的起點判斷邏輯
- [ ] **2.3** 新增 API endpoint: `POST /api/validation/connection`
- [ ] **2.4** 新增 API endpoint: `GET /api/validation/connectable`
- [ ] **2.5** 新增 API endpoint: `POST /api/validation/workflow`
- [ ] **2.6** 新增 API endpoint: `GET /api/modules/startable`
- [ ] **2.7** 前端接入：拖線時呼叫 validate_connection
- [ ] **2.8** 前端接入：顯示 connectable modules
- [ ] **2.9** 前端接入：儲存前呼叫 validate_workflow
- [ ] **2.10** 前端接入：錯誤顯示

### Phase 3: Pro 接入 (flyto-pro)

- [ ] **3.1** 新增 API endpoint: `GET /api/catalog/outline`
- [ ] **3.2** 新增 API endpoint: `GET /api/catalog/category/{category}`
- [ ] **3.3** 新增 API endpoint: `GET /api/catalog/module/{module_id}`
- [ ] **3.4** 更新 LLM prompt：使用三層 catalog
- [ ] **3.5** 更新 workflow 組裝邏輯：使用 validate_workflow

### Phase 4: 優化 (後續)

- [ ] **4.1** 實作 `normalize_workflow()`
- [ ] **4.2** 實作 `explain_error()` + i18n
- [ ] **4.3** 實作 `diff_validate()` 增量驗證
- [ ] **4.4** 實作 `build_artifacts()` 靜態產物
- [ ] **4.5** Cloud 前端載入靜態產物做即時提示

---

## API 接口總覽

### Validation API

| Function | 用途 | 呼叫者 |
|----------|------|--------|
| `validate_connection(from, to)` | 驗證單一連線 | Cloud (拖線) |
| `get_connectable(module_id, direction)` | 取得可連接的 modules | Cloud (UI 提示) |
| `get_connectable_summary(module_id)` | 取得分類統計 | Cloud (UI 分組) |
| `validate_workflow(nodes, edges)` | 驗證整個流程 | Cloud (儲存/執行前) |
| `validate_start(nodes, edges)` | 只驗證起點 | Cloud (快速檢查) |
| `get_startable_modules()` | 取得可當起點的 modules | Cloud (新增節點) |
| `normalize_workflow(workflow)` | 自動修復 | Cloud (載入舊 workflow) |
| `explain_error(code, meta)` | 錯誤解釋 | Cloud (顯示錯誤) |

### Catalog API

| Function | 用途 | 呼叫者 |
|----------|------|--------|
| `get_outline()` | 取得 category 大綱 | Pro (LLM 第一輪) |
| `get_category_detail(category)` | 取得類別細節 | Pro (LLM 第二輪) |
| `get_module_detail(module_id)` | 取得單一 module 完整資訊 | Pro (組裝 workflow) |
| `get_modules_batch(module_ids)` | 批量取得 | Pro (效能優化) |

---

## 效能預估

| 操作 | 複雜度 | 預估時間 |
|------|--------|---------|
| `validate_connection` | O(1) 索引查詢 | < 0.1ms |
| `get_connectable` | O(1) + slice | < 0.5ms |
| `validate_workflow` | O(n + e) 節點+邊 | < 5ms (100 nodes) |
| `get_outline` | O(c) categories | < 0.5ms |
| `get_category_detail` | O(m) modules in category | < 1ms |
| `ConnectionIndex._build` | O(n²) 一次性 | < 100ms (1000 modules) |

---

## 版本規劃

| 版本 | 內容 | 狀態 |
|------|------|------|
| 1.6.5 | Composite 簡化 | ✅ 已發布 |
| 1.7.0 | Validation API + Catalog API | 🔄 待實作 |
| 1.8.0 | Normalize + Error Explain | 📋 計劃中 |
| 1.9.0 | Diff Validate + Artifacts | 📋 計劃中 |

---

## 注意事項

1. **向後相容**: 新增欄位都有預設值，舊 module 不用改也能運作
2. **效能優先**: 使用預計算索引，避免每次都遍歷
3. **錯誤明確**: 統一錯誤碼 + i18n，Cloud 只負責顯示
4. **單一真理**: 所有規則只在 Core 定義，Cloud/Pro 只消費
