# Flyto Item-Based Execution Pipeline Specification

> **Version:** 1.0.0-draft
> **Status:** Draft - Pending Review
> **Author:** Claude (Spec)
> **Date:** 2025-01-23

---

## 1. Executive Summary

本規範定義 Flyto 的 **Item-Based Execution Pipeline**，使其達到 n8n 等級的資料處理能力。

### 目標

1. **Item-Based 語意**：每個節點處理 `items[]` 陣列，支援多筆資料流
2. **動態 Schema 條件**：支援 `showIf`, `dependsOn`, `displayOptions`
3. **Field-Level Validation**：錯誤路徑對應到具體欄位

### 設計原則

- **Backend 驅動**：所有邏輯由 Core 提供，Frontend 只渲染
- **向後相容**：現有 workflow YAML 無需修改即可運行
- **漸進式採用**：模組可選擇性啟用 item-based 模式

### Scope（供 AI 實作的範圍說明）

本文件為「混合願景 + 可執行規格」，用途是指導 AI 逐步落地與拆解工作。
其中 1–12 章偏「可直接落地」的核心規格，13 章起屬於中長期能力規劃與設計方向。
AI 實作時請優先落地 1–12 章，並將 13+ 視為分階段能力擴展。

### AI 實作順序指引（Execution Order）

1. **Phase 1：Core Foundation（必做）**
   - Item-based execution pipeline
   - Dynamic schema conditions
   - Field-level validation
2. **Phase 2：Execution Trace（核心體驗）**
   - ExecutionTrace / StepTrace / ItemTrace
   - API 端點與前端渲染契約
3. **Phase 3：Merge/Split 與多輸入語意**
   - Merge/Split 策略落地
   - Multi-input 行為一致化（by_port / merged）
4. **Phase 4：Enterprise/AI 擴展**
   - 依 13+ 章節規劃分段實作

---

## 2. Item-Based Execution Model

### 2.1 核心概念

```
┌─────────────────────────────────────────────────────────────────┐
│                        Item Pipeline                            │
│                                                                 │
│  ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐  │
│  │  Node A │ ──▶ │  Node B │ ──▶ │  Node C │ ──▶ │  Node D │  │
│  │         │     │         │     │         │     │         │  │
│  │ items[] │     │ items[] │     │ items[] │     │ items[] │  │
│  └─────────┘     └─────────┘     └─────────┘     └─────────┘  │
│                                                                 │
│  每個節點接收 items[]，處理後輸出 items[]                        │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Item 結構

```python
@dataclass
class Item:
    """單一資料項目"""
    json: Dict[str, Any]           # 主要資料
    binary: Optional[Dict[str, BinaryData]] = None  # 二進制資料（檔案等）
    meta: Optional[ItemMeta] = None  # 元資料（來源、索引等）

    # 錯誤追蹤（per-item）
    error: Optional[ItemError] = None
    pairedItem: Optional[PairedItemInfo] = None  # 追蹤來源 item


@dataclass
class ItemMeta:
    """Item 元資料"""
    sourceNodeId: Optional[str] = None
    sourceItemIndex: Optional[int] = None
    executionIndex: Optional[int] = None


@dataclass
class ItemError:
    """Per-item 錯誤資訊"""
    message: str
    description: Optional[str] = None
    itemIndex: int = 0


@dataclass
class PairedItemInfo:
    """追蹤 item 來源（用於 merge/split 時保持對應）"""
    item: int  # 來源 item index
    input: Optional[int] = None  # 來源 input index（多輸入時）
```

### 2.3 NodeExecutionResult

```python
@dataclass
class NodeExecutionResult:
    """節點執行結果（取代現有 ModuleResult）"""

    # 主要輸出：二維陣列 [output_index][item_index]
    # 大多數節點只有一個 output，所以是 [[item1, item2, ...]]
    data: List[List[Item]]

    # 執行狀態
    status: ExecutionStatus  # 'success' | 'error' | 'partial'

    # 錯誤資訊（節點級別）
    error: Optional[NodeError] = None

    # 執行元資料
    meta: Optional[ExecutionMeta] = None

    # Hints for UI（如動態 ports）
    hints: Optional[Dict[str, Any]] = None


class ExecutionStatus(Enum):
    SUCCESS = "success"      # 所有 items 成功
    ERROR = "error"          # 整個節點失敗
    PARTIAL = "partial"      # 部分 items 失敗（繼續執行）


@dataclass
class ExecutionMeta:
    """執行元資料"""
    startTime: datetime
    endTime: datetime
    durationMs: int
    itemsProcessed: int
    itemsFailed: int
```

### 2.4 向後相容

現有模組返回 `{ ok, data }` 將自動轉換：

```python
def wrap_legacy_result(result: Dict[str, Any]) -> NodeExecutionResult:
    """將舊格式轉換為 item-based 格式"""
    if result.get('ok', True):
        # 成功：包裝為單一 item
        item = Item(json=result.get('data', {}))
        return NodeExecutionResult(
            data=[[item]],
            status=ExecutionStatus.SUCCESS
        )
    else:
        # 失敗：返回錯誤
        return NodeExecutionResult(
            data=[[]],
            status=ExecutionStatus.ERROR,
            error=NodeError(
                message=result.get('error', 'Unknown error'),
                code=result.get('error_code', 'UNKNOWN')
            )
        )
```

### 2.5 多輸入語意（Multi-Input Semantics）

許多節點會同時接收多個上游輸入（例如 merge、join、or、combine），因此需要明確的多輸入語意。

**核心規則：**

- Engine 會為每個步驟提供 `input_items_by_port`：以「輸入 port」為維度的 items 集合
- 若節點只有單一輸入 port，則 `input_items_by_port["input"]` 等同 `input_items`
- 多輸入節點可以選擇以「port 合併」或「保留多 input」模式處理

**資料結構（建議）：**

```python
@dataclass
class StepInputItems:
    # 以輸入 port 為 key 的 items
    by_port: Dict[str, List[Item]]

    # 扁平化合併（對多輸入節點可選）
    merged: List[Item]
```

**執行語意：**

- `execution_mode="items"`：預設只處理 `merged`（可在 module 內選擇讀取 `by_port`）
- `execution_mode="all"`：傳入完整 `by_port` 以支援多輸入策略（例如 combine by key）

### 2.6 Edge Type 與 Item 傳遞規則

為避免 runtime 行為不一致，需規範「edge_type」與 items 傳遞的行為。

**建議規則：**

- `edge_type="control"`：只影響流程路由，**不**傳遞 items（items 為空）
- `edge_type="data"`：傳遞 items，並作為下游 input
- `edge_type="iterate"`：傳遞 items，並標記為 loop body input
- `edge_type="done"`：不傳遞 items，僅觸發 loop done 分支

**相容策略：**

- 若未標註 edge_type，預設為 `data`（傳遞 items）
- 明確標註 `control` 才不傳 items
- 舊版 workflow 無 items 概念，仍能透過 `wrap_legacy_result` 轉換為單一 item

---

## 3. Module Interface

### 3.1 新版 BaseModule

```python
class BaseModule(ABC):
    """Base class for all modules (v2 with item support)"""

    # 模式聲明
    execution_mode: str = "single"  # "single" | "items" | "all"

    # single: 傳統模式，處理單一請求，返回單一結果
    # items:  逐個處理每個 input item
    # all:    接收所有 items，一次處理（用於 aggregate 類操作）

    @abstractmethod
    async def execute(self) -> Any:
        """傳統執行方法（向後相容）"""
        pass

    async def execute_item(self, item: Item, index: int, context: ItemContext) -> Item:
        """
        處理單一 item（execution_mode="items" 時使用）

        Args:
            item: 輸入 item
            index: item 索引
            context: item 執行上下文

        Returns:
            處理後的 item（或多個 items）
        """
        # 預設行為：呼叫 execute() 並包裝結果
        result = await self.execute()
        return Item(json=result.get('data', result))

    async def execute_all(self, items: List[Item], context: ExecutionContext) -> List[Item]:
        """
        處理所有 items（execution_mode="all" 時使用）

        用於需要看到所有資料的操作，如：
        - aggregate（聚合）
        - sort（排序）
        - limit（取前 N 筆）
        """
        # 預設行為：逐個處理
        results = []
        for i, item in enumerate(items):
            result = await self.execute_item(item, i, ItemContext(items=items))
            results.append(result)
        return results
```

### 3.2 執行模式說明

| Mode | 使用場景 | 輸入 | 輸出 |
|------|----------|------|------|
| `single` | HTTP 請求、API 呼叫 | params | 單一結果 → 包裝成 `[Item]` |
| `items` | 資料轉換、過濾 | 每個 item 獨立處理 | 1:1 或 1:N items |
| `all` | 聚合、排序、Merge | 所有 items | 處理後的 items |

### 3.3 範例：HTTP Request（single mode）

```python
@register_module(
    module_id='http.request',
    execution_mode='single',  # 預設，可省略
    ...
)
class HttpRequestModule(BaseModule):
    async def execute(self) -> Dict[str, Any]:
        # 現有邏輯不變
        response = await self._make_request()
        return self.success(response)
```

### 3.4 範例：Data Transform（items mode）

```python
@register_module(
    module_id='data.transform',
    execution_mode='items',
    ...
)
class DataTransformModule(BaseModule):
    async def execute_item(self, item: Item, index: int, context: ItemContext) -> Item:
        # 處理單一 item
        transformed = self._apply_transform(item.json)
        return Item(json=transformed, pairedItem=PairedItemInfo(item=index))
```

### 3.5 範例：Aggregate（all mode）

```python
@register_module(
    module_id='data.aggregate',
    execution_mode='all',
    ...
)
class AggregateModule(BaseModule):
    async def execute_all(self, items: List[Item], context: ExecutionContext) -> List[Item]:
        # 聚合所有 items
        field = self.params.get('field')
        total = sum(item.json.get(field, 0) for item in items)
        return [Item(json={'total': total, 'count': len(items)})]
```

---

## 4. Workflow Engine Changes

### 4.1 Step Executor 修改

```python
class StepExecutor:
    async def execute_step(self, step_config, input_items: List[Item], input_items_by_port: Dict[str, List[Item]], ...) -> NodeExecutionResult:
        """執行單一步驟"""

        module = self._get_module(step_config)
        mode = getattr(module, 'execution_mode', 'single')

        if mode == 'single':
            # 傳統模式：忽略 input_items，使用 params
            result = await module.run()
            return wrap_legacy_result(result)

        elif mode == 'items':
            # 逐個處理
            output_items = []
            errors = []

            for i, item in enumerate(input_items):
                try:
                    # 注入 item 到 params
                    module.params['$item'] = item.json
                    module.params['$index'] = i

                    result_item = await module.execute_item(item, i, context)
                    output_items.append(result_item)
                except Exception as e:
                    if self._on_error == 'continue':
                        output_items.append(Item(json={}, error=ItemError(str(e), itemIndex=i)))
                        errors.append(e)
                    else:
                        raise

            status = ExecutionStatus.PARTIAL if errors else ExecutionStatus.SUCCESS
            return NodeExecutionResult(data=[output_items], status=status)

        elif mode == 'all':
            # 批次處理（允許多輸入語意）
            output_items = await module.execute_all(input_items, context)
            return NodeExecutionResult(data=[output_items], status=ExecutionStatus.SUCCESS)
```

### 4.2 Context 變更

```python
# 現有 context 結構
context = {
    'step_id': { 'ok': True, 'data': {...} },
    ...
}

# 新增 items 存取
context = {
    'step_id': {
        'ok': True,
        'data': {...},  # 向後相容：第一個 item 的 json
        'items': [Item, Item, ...],  # 新增：所有 items
        'meta': ExecutionMeta
    },
    ...
}
```

### 4.3 變數解析擴充

```python
class VariableResolver:
    def resolve(self, template: str) -> Any:
        """
        支援的語法：

        ${step.data.field}      # 現有：取第一個 item 的欄位
        ${step.items}           # 新增：取所有 items
        ${step.items[0].field}  # 新增：取特定 item
        ${step.items.length}    # 新增：item 數量
        ${$item.field}          # 新增：當前 item（items mode）
        ${$index}               # 新增：當前 index
        """
```

---

## 5. Merge Strategies

### 5.1 Merge Node Types

當多個分支匯入同一節點時，需要 merge 策略：

```python
class MergeMode(Enum):
    APPEND = "append"           # 合併所有 items（預設）
    COMBINE_BY_INDEX = "index"  # 依 index 合併
    COMBINE_BY_KEY = "key"      # 依指定 key 合併
    MULTIPLEX = "multiplex"     # 笛卡爾積
    WAIT_ALL = "wait"           # 等待所有分支完成
```

### 5.2 Merge 行為

```
Branch A: [item1, item2]
Branch B: [item3, item4, item5]

APPEND:           [item1, item2, item3, item4, item5]
COMBINE_BY_INDEX: [{...item1, ...item3}, {...item2, ...item4}, {item5}]
COMBINE_BY_KEY:   依指定 key 合併相同值的 items
MULTIPLEX:        [A1+B1, A1+B2, A1+B3, A2+B1, A2+B2, A2+B3]
```

### 5.3 Split/Fork 行為

```python
class SplitMode(Enum):
    CLONE = "clone"      # 每個分支收到相同 items
    DISTRIBUTE = "dist"  # 平均分配 items 到各分支
    FILTER = "filter"    # 依條件分配
```

---

## 6. Dynamic Schema Conditions

### 6.1 Schema 擴充

```python
def field(
    key: str,
    *,
    type: str,
    # ... existing fields ...

    # === 新增：動態條件 ===
    showIf: Optional[Dict[str, Any]] = None,     # 顯示條件
    hideIf: Optional[Dict[str, Any]] = None,     # 隱藏條件
    dependsOn: Optional[List[str]] = None,       # 依賴欄位
    displayOptions: Optional[Dict[str, Any]] = None,  # n8n 相容格式

    # === 新增：動態選項 ===
    optionsFrom: Optional[str] = None,           # 動態選項來源
    loadOptions: Optional[Dict[str, Any]] = None,  # 載入選項配置

) -> Schema:
```

### 6.2 Condition 語法

```python
# showIf / hideIf 支援的條件格式
{
    "field": "value"                    # 等於
}

{
    "field": {"$ne": "value"}           # 不等於
}

{
    "field": {"$in": ["a", "b"]}        # 在列表中
}

{
    "field": {"$exists": True}          # 欄位存在且非空
}

{
    "$and": [                           # AND 組合
        {"field1": "value1"},
        {"field2": "value2"}
    ]
}

{
    "$or": [                            # OR 組合
        {"field1": "value1"},
        {"field2": "value2"}
    ]
}
```

### 6.3 範例

```python
params_schema = compose(
    field("operation", type="select", options=[
        {"value": "get", "label": "Get"},
        {"value": "create", "label": "Create"},
        {"value": "update", "label": "Update"},
    ]),

    field("id", type="string",
        label="Record ID",
        showIf={"operation": {"$in": ["get", "update"]}},
        required=True
    ),

    field("data", type="object",
        label="Record Data",
        showIf={"operation": {"$in": ["create", "update"]}}
    ),

    field("options", type="object",
        label="Options",
        showIf={
            "$and": [
                {"operation": "create"},
                {"advanced_mode": True}
            ]
        }
    ),
)
```

### 6.4 displayOptions（n8n 相容）

```python
field("body", type="object",
    displayOptions={
        "show": {
            "method": ["POST", "PUT", "PATCH"]
        },
        "hide": {
            "content_type": ["multipart/form-data"]
        }
    }
)
```

---

## 7. Field-Level Validation

### 7.1 ValidationResult 結構

```python
@dataclass
class ValidationResult:
    """驗證結果"""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationWarning] = field(default_factory=list)


@dataclass
class ValidationError:
    """單一驗證錯誤"""
    path: str              # 欄位路徑，如 "params.url" 或 "params.headers[0].value"
    message: str           # 錯誤訊息
    code: str              # 錯誤代碼

    # 可選詳情
    expected: Optional[Any] = None
    actual: Optional[Any] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationWarning:
    """驗證警告（非阻斷）"""
    path: str
    message: str
    code: str
```

### 7.2 Validator 擴充

```python
class ModuleValidator:
    def validate(self, params: Dict[str, Any], schema: Schema) -> ValidationResult:
        """驗證參數並返回詳細結果"""
        errors = []
        warnings = []

        for field_key, field_schema in schema.items():
            field_errors = self._validate_field(
                path=f"params.{field_key}",
                value=params.get(field_key),
                schema=field_schema,
                params=params  # 傳入完整 params 用於條件判斷
            )
            errors.extend(field_errors)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def _validate_field(self, path: str, value: Any, schema: dict, params: dict) -> List[ValidationError]:
        """驗證單一欄位"""
        errors = []

        # 1. 檢查條件顯示
        if not self._should_validate(schema, params):
            return []  # 欄位不顯示，跳過驗證

        # 2. 必填檢查
        if schema.get('required') and value in (None, '', []):
            errors.append(ValidationError(
                path=path,
                message=f"Field is required",
                code="REQUIRED"
            ))

        # 3. 類型檢查
        if value is not None:
            type_error = self._validate_type(path, value, schema.get('type'))
            if type_error:
                errors.append(type_error)

        # 4. Validation rules
        if value is not None and 'validation' in schema:
            rule_errors = self._validate_rules(path, value, schema['validation'])
            errors.extend(rule_errors)

        return errors

    def _should_validate(self, schema: dict, params: dict) -> bool:
        """根據 showIf/hideIf 判斷是否需要驗證"""
        if 'showIf' in schema:
            if not self._evaluate_condition(schema['showIf'], params):
                return False
        if 'hideIf' in schema:
            if self._evaluate_condition(schema['hideIf'], params):
                return False
        return True
```

### 7.3 前端對應

```typescript
// Frontend 接收 validation result
interface ValidationResult {
  valid: boolean
  errors: Array<{
    path: string      // "params.url"
    message: string
    code: string
  }>
}

// 前端將 path 對應到欄位
function getFieldError(path: string, errors: ValidationError[]): string | null {
  const fieldPath = path.replace('params.', '')
  const error = errors.find(e => e.path.replace('params.', '') === fieldPath)
  return error?.message || null
}

// 節點徽章：收集該節點的所有錯誤
function getNodeErrors(nodeId: string, validationResults: Map<string, ValidationResult>) {
  const result = validationResults.get(nodeId)
  return result?.errors || []
}
```

---

## 8. Execution Trace

### 8.1 Trace 結構

```python
@dataclass
class ExecutionTrace:
    """完整執行追蹤"""
    execution_id: str
    workflow_id: str
    workflow_name: str

    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    duration_ms: int

    # 輸入參數
    input_params: Dict[str, Any]

    # 步驟追蹤
    steps: List[StepTrace]

    # 最終輸出
    output: Optional[Dict[str, Any]]

    # 錯誤（如果失敗）
    error: Optional[TraceError]


@dataclass
class StepTrace:
    """單一步驟追蹤"""
    step_id: str
    step_index: int
    module_id: str

    status: str  # 'pending' | 'running' | 'success' | 'error' | 'skipped'
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_ms: int

    # 輸入（解析後的 params + input items）
    input: StepInput

    # 輸出（items + 錯誤）
    output: StepOutput

    # Per-item 追蹤（用於 items mode）
    item_traces: Optional[List[ItemTrace]]


@dataclass
class StepInput:
    """步驟輸入"""
    params: Dict[str, Any]           # 解析後的參數
    params_raw: Dict[str, Any]       # 原始參數（含變數）
    items: Optional[List[Item]]      # 輸入 items


@dataclass
class StepOutput:
    """步驟輸出"""
    items: List[List[Item]]          # 輸出 items [output][item]
    item_count: int
    error: Optional[str]


@dataclass
class ItemTrace:
    """單一 item 處理追蹤"""
    index: int
    status: str
    duration_ms: int
    input: Dict[str, Any]
    output: Dict[str, Any]
    error: Optional[str]
```

### 8.2 API 端點

```python
# GET /api/v1/executions/{execution_id}/trace
{
    "execution_id": "exec_123",
    "workflow_id": "wf_456",
    "status": "completed",
    "steps": [
        {
            "step_id": "fetch_data",
            "module_id": "http.request",
            "status": "success",
            "duration_ms": 234,
            "input": {
                "params": {"url": "https://api.example.com", "method": "GET"},
                "items": null
            },
            "output": {
                "items": [[{"json": {"status": 200, "body": {...}}}]],
                "item_count": 1
            }
        },
        {
            "step_id": "transform",
            "module_id": "data.transform",
            "status": "success",
            "duration_ms": 12,
            "input": {
                "params": {"expression": "$.data.items"},
                "items": [{"json": {"status": 200, "body": {...}}}]
            },
            "output": {
                "items": [[{"json": {...}}, {"json": {...}}, {"json": {...}}]],
                "item_count": 3
            },
            "item_traces": [
                {"index": 0, "status": "success", "duration_ms": 4},
                {"index": 1, "status": "success", "duration_ms": 4},
                {"index": 2, "status": "success", "duration_ms": 4}
            ]
        }
    ]
}
```

---

## 9. Frontend Contract

### 9.1 API 回應格式

```typescript
// 模組 schema（從 /api/v1/modules/{id} 取得）
interface ModuleSchema {
  id: string
  label: string
  description: string

  paramsSchema: {
    [fieldKey: string]: {
      type: string
      label: string
      required?: boolean
      default?: any

      // 動態條件
      showIf?: Condition
      hideIf?: Condition
      dependsOn?: string[]
      displayOptions?: DisplayOptions

      // 驗證
      validation?: ValidationRules
    }
  }

  outputSchema: {...}

  // Item-based 資訊
  executionMode: 'single' | 'items' | 'all'
}

// 條件格式
type Condition =
  | { [field: string]: any }  // 等於
  | { [field: string]: { $ne: any } }  // 不等於
  | { [field: string]: { $in: any[] } }
  | { $and: Condition[] }
  | { $or: Condition[] }
```

### 9.2 前端職責

| 職責 | 來源 | 前端行為 |
|------|------|----------|
| 欄位顯示/隱藏 | `showIf`/`hideIf` | 評估條件，控制欄位渲染 |
| 欄位驗證狀態 | `ValidationResult.errors` | 將 `path` 對應到欄位，顯示錯誤 |
| Item 數量顯示 | `StepOutput.item_count` | 節點上顯示 item 徽章 |
| Trace 視覺化 | `ExecutionTrace` | 渲染執行流程圖 |

### 9.3 條件評估（前端實作）

```typescript
function evaluateCondition(condition: Condition, params: Record<string, any>): boolean {
  if ('$and' in condition) {
    return condition.$and.every(c => evaluateCondition(c, params))
  }
  if ('$or' in condition) {
    return condition.$or.some(c => evaluateCondition(c, params))
  }

  for (const [field, expected] of Object.entries(condition)) {
    const value = params[field]

    if (typeof expected === 'object' && expected !== null) {
      if ('$ne' in expected) return value !== expected.$ne
      if ('$in' in expected) return expected.$in.includes(value)
      if ('$exists' in expected) return expected.$exists ? value != null : value == null
    }

    if (value !== expected) return false
  }

  return true
}
```

---

## 10. Migration Path

### 10.1 Phase 1: Foundation（Core）

1. 新增 `Item`, `NodeExecutionResult` 類別
2. 修改 `StepExecutor` 支援 `execution_mode`
3. 擴充 `VariableResolver` 支援 `items` 語法
4. 新增 `ValidationResult` 結構

### 10.2 Phase 2: Schema（Core）

1. 擴充 `field()` 支援 `showIf`, `hideIf`, `dependsOn`
2. 實作條件評估器
3. 修改 validator 返回 field-level errors

### 10.3 Phase 3: Execution Trace（Core）

1. 實作 `ExecutionTrace`, `StepTrace` 類別
2. 修改 engine 記錄完整 trace
3. 新增 trace API 端點

### 10.4 Phase 4: Frontend

1. 實作條件評估
2. 實作 validation error 對應
3. 實作 trace UI

---

## 11. Open Questions

1. **Binary Data 處理**：檔案上傳/下載的 binary 資料如何在 items 中傳遞？
2. **Memory 限制**：大量 items 時如何處理記憶體？是否需要 streaming？
3. **並行處理**：`items` mode 是否支援並行處理多個 items？
4. **Error Recovery**：部分 items 失敗時，如何恢復/重試？

---

## 12. Appendix: n8n Comparison

| 功能 | n8n | Flyto 現況 | Flyto 目標 |
|------|-----|------------|------------|
| Item-based | ✅ 原生支援 | ❌ 單一結果 | ✅ 完整支援 |
| Merge strategies | ✅ Append/Combine/Multiplex | ❌ 無 | ✅ 完整支援 |
| Dynamic schema | ✅ displayOptions | ❌ 靜態 | ✅ showIf/hideIf |
| Field validation | ✅ 即時欄位錯誤 | ⚠️ 節點級 | ✅ 欄位級 |
| Execution trace | ✅ 完整 I/O | ⚠️ 基礎 | ✅ Per-item trace |
| Paired items | ✅ 追蹤來源 | ❌ 無 | ✅ pairedItem |

---

## 13. Enterprise RPA Capabilities（超越 UiPath）

### 13.1 Desktop Automation

**目標**：支援跨平台桌面自動化（Windows/macOS/Linux）

**Prerequisites / Assumptions：**
- 需要本機 Agent（Desktop Runner）與權限授權流程
- 需有安全沙盒與可觀測性（screenshot / recording / audit log）

```python
@dataclass
class DesktopAutomationCapabilities:
    """桌面自動化能力"""

    # UI 元素定位策略
    selectors: List[SelectorStrategy] = field(default_factory=list)

    # 支援的操作
    actions: List[str] = field(default_factory=lambda: [
        "click",           # 點擊
        "double_click",    # 雙擊
        "right_click",     # 右鍵
        "type_text",       # 輸入文字
        "send_keys",       # 發送按鍵組合
        "drag_drop",       # 拖放
        "scroll",          # 滾動
        "hover",           # 懸停
        "focus",           # 聚焦
        "get_text",        # 取得文字
        "get_attribute",   # 取得屬性
        "screenshot",      # 截圖
        "wait_element",    # 等待元素
        "wait_vanish",     # 等待元素消失
    ])


class SelectorStrategy(Enum):
    """元素定位策略"""
    ACCESSIBILITY = "accessibility"  # Accessibility API（推薦）
    IMAGE = "image"                  # 圖像識別
    OCR = "ocr"                      # 文字識別
    COORDINATES = "coordinates"      # 座標（最後手段）
    NATIVE = "native"                # 原生 API（Windows UI Automation, macOS Accessibility）
```

**跨平台實作：**

| 平台 | 技術 | 優先級 |
|------|------|--------|
| Windows | UI Automation API + pywinauto | P0 |
| macOS | Accessibility API + pyobjc | P0 |
| Linux | AT-SPI2 + python-atspi | P1 |
| Web | Playwright（已有） | ✅ Done |

**範例模組：**

```python
@register_module(
    module_id='desktop.click',
    category='rpa',
    subcategory='desktop',
    label='Click Element',
    params_schema=compose(
        field("selector", type="string",
            label="Element Selector",
            description="Accessibility selector or image path",
            required=True
        ),
        field("selector_type", type="select",
            options=[
                {"value": "accessibility", "label": "Accessibility (推薦)"},
                {"value": "image", "label": "Image Match"},
                {"value": "ocr", "label": "OCR Text"},
                {"value": "coordinates", "label": "Coordinates"},
            ],
            default="accessibility"
        ),
        field("click_type", type="select",
            options=[
                {"value": "single", "label": "Single Click"},
                {"value": "double", "label": "Double Click"},
                {"value": "right", "label": "Right Click"},
            ],
            default="single"
        ),
        field("timeout_ms", type="number", default=30000),
        field("confidence", type="number",
            label="Match Confidence",
            showIf={"selector_type": {"$in": ["image", "ocr"]}},
            default=0.9,
            min=0.5,
            max=1.0
        ),
    )
)
class DesktopClickModule(BaseModule):
    pass
```

### 13.2 Image Recognition & OCR

```python
@dataclass
class VisionCapabilities:
    """視覺識別能力"""

    # 圖像匹配
    image_match: ImageMatchConfig

    # OCR 引擎
    ocr_engines: List[OCREngine]

    # 物件偵測（AI）
    object_detection: ObjectDetectionConfig


@dataclass
class ImageMatchConfig:
    """圖像匹配配置"""
    algorithms: List[str] = field(default_factory=lambda: [
        "template_matching",    # OpenCV 模板匹配
        "feature_matching",     # SIFT/ORB 特徵匹配
        "deep_learning",        # CNN 特徵（更強健）
    ])
    default_confidence: float = 0.9
    multi_scale: bool = True   # 支援不同縮放比例


@dataclass
class OCREngine:
    """OCR 引擎"""
    name: str
    provider: str  # "tesseract" | "paddleocr" | "azure" | "google" | "aws"
    languages: List[str]
    capabilities: List[str]  # ["text", "table", "handwriting", "layout"]


# OCR 模組範例
@register_module(
    module_id='vision.ocr',
    category='rpa',
    subcategory='vision',
    label='OCR - Extract Text',
    params_schema=compose(
        field("image", type="file",
            label="Image Source",
            description="Screenshot, file path, or base64",
            required=True
        ),
        field("engine", type="select",
            options=[
                {"value": "paddleocr", "label": "PaddleOCR (推薦, 離線)"},
                {"value": "tesseract", "label": "Tesseract (離線)"},
                {"value": "azure", "label": "Azure Computer Vision"},
                {"value": "google", "label": "Google Cloud Vision"},
            ],
            default="paddleocr"
        ),
        field("languages", type="array",
            label="Languages",
            default=["en", "zh-TW", "zh-CN", "ja"]
        ),
        field("output_format", type="select",
            options=[
                {"value": "text", "label": "Plain Text"},
                {"value": "structured", "label": "Structured (with positions)"},
                {"value": "table", "label": "Table Detection"},
            ],
            default="text"
        ),
        field("region", type="object",
            label="Region of Interest",
            description="Optional: {x, y, width, height}",
            required=False
        ),
    )
)
class OCRModule(BaseModule):
    pass
```

---

## 14. AI Document Processing (IDP)

**目標**：超越 UiPath Document Understanding，提供端到端的文件處理能力。

**Prerequisites / Assumptions：**
- 需要文件儲存與索引（S3/MinIO + metadata store）
- 需要人機協作介面（Review UI）與任務指派機制

### 14.1 Document Processing Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AI Document Processing Pipeline                       │
│                                                                          │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐│
│  │ Ingest   │──▶│ Classify │──▶│ Extract  │──▶│ Validate │──▶│ Export ││
│  │          │   │          │   │          │   │          │   │        ││
│  │ PDF/IMG  │   │ AI 分類  │   │ AI 擷取  │   │ 人工審核 │   │ 結構化 ││
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘   └────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

### 14.2 Document Types

```python
class DocumentType(Enum):
    """支援的文件類型"""
    # 財務文件
    INVOICE = "invoice"
    RECEIPT = "receipt"
    PURCHASE_ORDER = "purchase_order"
    BANK_STATEMENT = "bank_statement"

    # 身份文件
    ID_CARD = "id_card"
    PASSPORT = "passport"
    DRIVERS_LICENSE = "drivers_license"

    # 合約文件
    CONTRACT = "contract"
    NDA = "nda"
    AGREEMENT = "agreement"

    # 表單
    FORM = "form"
    APPLICATION = "application"
    SURVEY = "survey"

    # 其他
    EMAIL = "email"
    LETTER = "letter"
    REPORT = "report"
    CUSTOM = "custom"
```

### 14.3 Extraction Schema

```python
@dataclass
class ExtractionSchema:
    """文件擷取 schema"""
    document_type: DocumentType
    fields: List[ExtractionField]
    tables: List[TableSchema]
    validation_rules: List[ValidationRule]


@dataclass
class ExtractionField:
    """擷取欄位定義"""
    name: str
    label: str
    field_type: str  # "string" | "number" | "date" | "currency" | "address" | "phone"
    required: bool = False
    aliases: List[str] = field(default_factory=list)  # 欄位可能的別名
    extraction_hints: List[str] = field(default_factory=list)  # 給 AI 的提示
    validation: Optional[Dict[str, Any]] = None


# Invoice 擷取 schema 範例
INVOICE_SCHEMA = ExtractionSchema(
    document_type=DocumentType.INVOICE,
    fields=[
        ExtractionField(
            name="invoice_number",
            label="Invoice Number",
            field_type="string",
            required=True,
            aliases=["inv no", "invoice #", "bill no"]
        ),
        ExtractionField(
            name="invoice_date",
            label="Invoice Date",
            field_type="date",
            required=True
        ),
        ExtractionField(
            name="due_date",
            label="Due Date",
            field_type="date"
        ),
        ExtractionField(
            name="vendor_name",
            label="Vendor Name",
            field_type="string",
            required=True
        ),
        ExtractionField(
            name="total_amount",
            label="Total Amount",
            field_type="currency",
            required=True
        ),
        ExtractionField(
            name="tax_amount",
            label="Tax Amount",
            field_type="currency"
        ),
    ],
    tables=[
        TableSchema(
            name="line_items",
            columns=["description", "quantity", "unit_price", "amount"]
        )
    ],
    validation_rules=[
        ValidationRule(
            rule="total_amount == sum(line_items.amount) + tax_amount",
            message="Total doesn't match line items"
        )
    ]
)
```

### 14.4 Human-in-the-Loop Validation

```python
@dataclass
class ValidationTask:
    """人工驗證任務"""
    task_id: str
    document_id: str
    extraction_result: Dict[str, Any]
    confidence_scores: Dict[str, float]

    # 需要人工確認的欄位（confidence < threshold）
    fields_to_review: List[str]

    # 狀態
    status: str  # "pending" | "in_review" | "approved" | "rejected"
    assigned_to: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_corrections: Optional[Dict[str, Any]] = None


class ValidationQueue:
    """驗證佇列"""

    async def submit_for_review(self, task: ValidationTask) -> str:
        """提交人工審核"""
        pass

    async def get_pending_tasks(self, assignee: str = None) -> List[ValidationTask]:
        """取得待審核任務"""
        pass

    async def approve(self, task_id: str, corrections: Dict[str, Any] = None) -> ValidationTask:
        """審核通過（可選修正）"""
        pass

    async def reject(self, task_id: str, reason: str) -> ValidationTask:
        """審核拒絕"""
        pass
```

---

## 15. Process Mining

**目標**：從執行日誌中發現流程瓶頸與優化機會。

**Prerequisites / Assumptions：**
- 需要完整且一致的執行事件日誌（含 trace / timing）
- 需要長期儲存與批次分析能力

### 15.1 Event Log Format

```python
@dataclass
class ProcessEvent:
    """流程事件（符合 XES 標準）"""
    case_id: str                    # 案例 ID
    activity: str                   # 活動名稱
    timestamp: datetime             # 時間戳
    resource: Optional[str] = None  # 執行者
    lifecycle: str = "complete"     # "start" | "complete" | "suspend" | "resume"

    # 額外屬性
    attributes: Dict[str, Any] = field(default_factory=dict)

    # 成本相關
    cost: Optional[float] = None
    duration_ms: Optional[int] = None


@dataclass
class EventLog:
    """事件日誌"""
    log_id: str
    name: str
    events: List[ProcessEvent]

    # 統計
    case_count: int
    event_count: int
    activity_count: int
    start_time: datetime
    end_time: datetime
```

### 15.2 Process Discovery

```python
class ProcessDiscovery:
    """流程發現"""

    def discover_model(self, event_log: EventLog, algorithm: str = "alpha") -> ProcessModel:
        """
        從事件日誌發現流程模型

        Algorithms:
        - "alpha": Alpha Miner（快速，適合結構化流程）
        - "heuristic": Heuristic Miner（容忍雜訊）
        - "inductive": Inductive Miner（保證 soundness）
        - "dfg": Directly-Follows Graph（最簡單）
        """
        pass

    def calculate_metrics(self, event_log: EventLog) -> ProcessMetrics:
        """計算流程指標"""
        pass


@dataclass
class ProcessMetrics:
    """流程指標"""
    # 時間指標
    avg_case_duration: timedelta
    median_case_duration: timedelta
    throughput_per_day: float

    # 效率指標
    rework_rate: float              # 重工率
    automation_rate: float          # 自動化率
    first_time_right_rate: float    # 一次通過率

    # 瓶頸分析
    bottleneck_activities: List[BottleneckInfo]
    waiting_time_breakdown: Dict[str, timedelta]

    # 變異分析
    variant_count: int
    top_variants: List[ProcessVariant]


@dataclass
class BottleneckInfo:
    """瓶頸資訊"""
    activity: str
    avg_waiting_time: timedelta
    avg_processing_time: timedelta
    utilization: float
    suggestions: List[str]  # AI 生成的優化建議
```

### 15.3 Conformance Checking

```python
class ConformanceChecker:
    """一致性檢查"""

    def check_conformance(
        self,
        event_log: EventLog,
        process_model: ProcessModel
    ) -> ConformanceResult:
        """檢查實際執行與模型的一致性"""
        pass


@dataclass
class ConformanceResult:
    """一致性結果"""
    fitness: float          # 0-1, 實際行為符合模型的程度
    precision: float        # 0-1, 模型是否過度允許
    generalization: float   # 0-1, 模型泛化能力

    # 偏差詳情
    deviations: List[Deviation]


@dataclass
class Deviation:
    """偏差"""
    case_id: str
    deviation_type: str  # "missing_activity" | "unexpected_activity" | "wrong_order"
    expected: str
    actual: str
    timestamp: datetime
```

---

## 16. Enterprise Orchestrator

**目標**：提供企業級的流程調度、監控、與治理能力。

**Prerequisites / Assumptions：**
- 需要多節點部署與分散式執行能力
- 需要高可用儲存與佇列系統（PostgreSQL/Redis/S3）

### 16.1 Orchestrator Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Flyto Orchestrator                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Scheduler  │  │   Queue     │  │   Robots    │  │  Dashboard  │    │
│  │             │  │   Manager   │  │   Manager   │  │             │    │
│  │ • Cron jobs │  │ • Work items│  │ • Register  │  │ • Monitoring│    │
│  │ • Triggers  │  │ • Priority  │  │ • Health    │  │ • Analytics │    │
│  │ • SLA       │  │ • Retry     │  │ • Scale     │  │ • Alerts    │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                         Execution Engine                         │    │
│  │  • Distributed execution    • State persistence                  │    │
│  │  • Checkpoint & recovery    • Long-running support               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                         Storage Layer                            │    │
│  │  • PostgreSQL (metadata)    • Redis (queue, state)               │    │
│  │  • S3/MinIO (artifacts)     • Elasticsearch (logs)               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 16.2 Robot Management

```python
@dataclass
class Robot:
    """機器人（執行代理）"""
    robot_id: str
    name: str
    machine_name: str
    robot_type: RobotType

    # 狀態
    status: RobotStatus
    last_heartbeat: datetime
    current_job: Optional[str]

    # 能力
    capabilities: List[str]  # ["browser", "desktop", "vision", "ai"]
    environments: List[str]  # ["production", "staging"]

    # 資源
    max_concurrent_jobs: int = 1
    current_load: int = 0


class RobotType(Enum):
    ATTENDED = "attended"      # 有人值守（互動模式）
    UNATTENDED = "unattended"  # 無人值守（後台執行）
    DEVELOPMENT = "development" # 開發測試


class RobotStatus(Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    DISCONNECTED = "disconnected"


class RobotManager:
    """機器人管理器"""

    async def register(self, robot: Robot) -> str:
        """註冊機器人"""
        pass

    async def heartbeat(self, robot_id: str, status: Dict[str, Any]) -> None:
        """心跳更新"""
        pass

    async def get_available_robots(
        self,
        capabilities: List[str] = None,
        environment: str = None
    ) -> List[Robot]:
        """取得可用機器人"""
        pass

    async def assign_job(self, robot_id: str, job_id: str) -> bool:
        """分配任務"""
        pass

    async def scale_robots(self, target_count: int, robot_type: RobotType) -> None:
        """自動擴縮（雲端機器人）"""
        pass
```

### 16.3 Job Scheduling

```python
@dataclass
class ScheduledJob:
    """排程任務"""
    job_id: str
    workflow_id: str
    name: str

    # 排程設定
    schedule_type: str  # "cron" | "interval" | "once" | "event"
    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = None
    run_at: Optional[datetime] = None
    trigger_event: Optional[str] = None

    # 執行設定
    params: Dict[str, Any] = field(default_factory=dict)
    robot_requirements: RobotRequirements = None
    timeout_minutes: int = 60
    retry_policy: RetryPolicy = None

    # SLA
    sla_deadline_minutes: Optional[int] = None
    priority: int = 5  # 1-10, 10 = highest

    # 狀態
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None


@dataclass
class RetryPolicy:
    """重試策略"""
    max_retries: int = 3
    retry_delay_seconds: int = 60
    backoff_multiplier: float = 2.0
    max_delay_seconds: int = 3600
    retry_on: List[str] = field(default_factory=lambda: ["timeout", "system_error"])


class Scheduler:
    """排程器"""

    async def create_schedule(self, job: ScheduledJob) -> str:
        pass

    async def update_schedule(self, job_id: str, updates: Dict[str, Any]) -> ScheduledJob:
        pass

    async def delete_schedule(self, job_id: str) -> bool:
        pass

    async def trigger_now(self, job_id: str, params: Dict[str, Any] = None) -> str:
        """立即觸發"""
        pass

    async def get_upcoming_jobs(self, hours: int = 24) -> List[ScheduledJob]:
        pass
```

---

## 17. Queue & Transaction System

**目標**：支援大規模資料處理與可靠的任務執行。

**Prerequisites / Assumptions：**
- 需要具備 idempotency 與 exactly-once 的儲存設計
- 需要可觀測性（重試、失敗率、SLA）

### 17.1 Work Queue

```python
@dataclass
class QueueItem:
    """佇列項目"""
    item_id: str
    queue_name: str
    reference: str                  # 業務參考（如訂單號）
    data: Dict[str, Any]            # 項目資料
    priority: int = 5               # 1-10

    # 狀態
    status: QueueItemStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 處理資訊
    robot_id: Optional[str] = None
    execution_id: Optional[str] = None
    retry_count: int = 0
    error: Optional[str] = None

    # 期限
    deadline: Optional[datetime] = None
    defer_until: Optional[datetime] = None


class QueueItemStatus(Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    RETRYING = "retrying"
    DEFERRED = "deferred"


class WorkQueue:
    """工作佇列"""

    async def add_item(self, queue_name: str, item: QueueItem) -> str:
        """新增項目"""
        pass

    async def add_bulk(self, queue_name: str, items: List[QueueItem]) -> List[str]:
        """批次新增"""
        pass

    async def get_next_item(
        self,
        queue_name: str,
        robot_id: str,
        filter: Dict[str, Any] = None
    ) -> Optional[QueueItem]:
        """取得下一個待處理項目"""
        pass

    async def complete_item(
        self,
        item_id: str,
        output: Dict[str, Any] = None
    ) -> QueueItem:
        """完成項目"""
        pass

    async def fail_item(
        self,
        item_id: str,
        error: str,
        retry: bool = True
    ) -> QueueItem:
        """標記失敗"""
        pass

    async def get_queue_stats(self, queue_name: str) -> QueueStats:
        """取得佇列統計"""
        pass


@dataclass
class QueueStats:
    """佇列統計"""
    queue_name: str
    total_items: int
    new_items: int
    in_progress: int
    completed_today: int
    failed_today: int
    avg_processing_time_ms: int
    throughput_per_hour: float
```

### 17.2 Transaction Support

```python
@dataclass
class Transaction:
    """交易（確保 exactly-once 處理）"""
    transaction_id: str
    queue_item_id: str
    workflow_id: str

    status: TransactionStatus
    started_at: datetime
    completed_at: Optional[datetime] = None

    # 檢查點
    checkpoints: List[TransactionCheckpoint] = field(default_factory=list)

    # 補償動作（用於 rollback）
    compensation_actions: List[CompensationAction] = field(default_factory=list)


class TransactionStatus(Enum):
    STARTED = "started"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class TransactionCheckpoint:
    """交易檢查點"""
    checkpoint_id: str
    step_id: str
    timestamp: datetime
    state: Dict[str, Any]


@dataclass
class CompensationAction:
    """補償動作"""
    action_id: str
    step_id: str
    compensation_workflow_id: str
    params: Dict[str, Any]
    executed: bool = False


class TransactionManager:
    """交易管理器"""

    async def begin_transaction(self, queue_item_id: str, workflow_id: str) -> Transaction:
        """開始交易"""
        pass

    async def checkpoint(
        self,
        transaction_id: str,
        step_id: str,
        state: Dict[str, Any],
        compensation: CompensationAction = None
    ) -> TransactionCheckpoint:
        """建立檢查點"""
        pass

    async def commit(self, transaction_id: str) -> Transaction:
        """提交交易"""
        pass

    async def rollback(self, transaction_id: str) -> Transaction:
        """回滾交易（執行補償動作）"""
        pass
```

---

## 18. Long-Running Workflows (State Machine)

**目標**：支援可暫停數天/數週的長時間流程。

**Prerequisites / Assumptions：**
- 需要狀態持久化與版本化
- 需要外部事件匯入機制（Webhook/Event Bus）

### 18.1 State Machine Definition

```python
@dataclass
class StateMachine:
    """狀態機定義"""
    machine_id: str
    name: str
    initial_state: str
    states: Dict[str, StateDefinition]
    transitions: List[Transition]

    # 持久化設定
    persistence: PersistenceConfig

    # 超時設定
    global_timeout: Optional[timedelta] = None


@dataclass
class StateDefinition:
    """狀態定義"""
    state_id: str
    state_type: StateType
    name: str

    # Entry/Exit actions
    on_enter: Optional[str] = None  # workflow_id to run
    on_exit: Optional[str] = None

    # 子狀態機（nested）
    child_machine: Optional[str] = None

    # 超時
    timeout: Optional[timedelta] = None
    on_timeout: Optional[str] = None  # transition name


class StateType(Enum):
    INITIAL = "initial"
    NORMAL = "normal"
    FINAL = "final"
    WAITING = "waiting"      # 等待外部事件
    PARALLEL = "parallel"    # 並行執行多個子狀態


@dataclass
class Transition:
    """狀態轉換"""
    name: str
    from_state: str
    to_state: str

    # 觸發條件
    trigger: TransitionTrigger

    # Guard condition
    guard: Optional[str] = None  # expression

    # 轉換時執行的 workflow
    action: Optional[str] = None


@dataclass
class TransitionTrigger:
    """轉換觸發器"""
    trigger_type: str  # "event" | "timeout" | "condition" | "manual"
    event_name: Optional[str] = None
    timeout: Optional[timedelta] = None
    condition: Optional[str] = None
```

### 18.2 State Machine Instance

```python
@dataclass
class StateMachineInstance:
    """狀態機實例"""
    instance_id: str
    machine_id: str
    correlation_id: str  # 業務關聯 ID

    # 當前狀態
    current_state: str
    state_data: Dict[str, Any]

    # 歷史
    state_history: List[StateHistoryEntry]

    # 時間
    created_at: datetime
    last_transition_at: datetime
    expires_at: Optional[datetime] = None

    # 狀態
    status: InstanceStatus


class InstanceStatus(Enum):
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class StateHistoryEntry:
    """狀態歷史記錄"""
    from_state: str
    to_state: str
    transition_name: str
    timestamp: datetime
    trigger: str
    data_snapshot: Dict[str, Any]


class StateMachineEngine:
    """狀態機引擎"""

    async def create_instance(
        self,
        machine_id: str,
        correlation_id: str,
        initial_data: Dict[str, Any] = None
    ) -> StateMachineInstance:
        """建立實例"""
        pass

    async def send_event(
        self,
        instance_id: str,
        event_name: str,
        event_data: Dict[str, Any] = None
    ) -> StateMachineInstance:
        """發送事件"""
        pass

    async def get_instance(self, instance_id: str) -> StateMachineInstance:
        """取得實例"""
        pass

    async def get_by_correlation(self, correlation_id: str) -> List[StateMachineInstance]:
        """依關聯 ID 查詢"""
        pass

    async def cancel(self, instance_id: str, reason: str) -> StateMachineInstance:
        """取消實例"""
        pass
```

### 18.3 Waiting for External Events

```python
# 範例：審批流程

APPROVAL_MACHINE = StateMachine(
    machine_id="approval_process",
    name="Document Approval",
    initial_state="draft",
    states={
        "draft": StateDefinition(
            state_id="draft",
            state_type=StateType.INITIAL,
            name="Draft"
        ),
        "pending_review": StateDefinition(
            state_id="pending_review",
            state_type=StateType.WAITING,
            name="Pending Review",
            on_enter="notify_reviewer",  # 發送通知
            timeout=timedelta(days=7),
            on_timeout="escalate"
        ),
        "pending_approval": StateDefinition(
            state_id="pending_approval",
            state_type=StateType.WAITING,
            name="Pending Approval",
            on_enter="notify_approver",
            timeout=timedelta(days=3),
            on_timeout="auto_reject"
        ),
        "approved": StateDefinition(
            state_id="approved",
            state_type=StateType.FINAL,
            name="Approved",
            on_enter="process_approved_document"
        ),
        "rejected": StateDefinition(
            state_id="rejected",
            state_type=StateType.FINAL,
            name="Rejected",
            on_enter="notify_rejection"
        ),
    },
    transitions=[
        Transition(
            name="submit",
            from_state="draft",
            to_state="pending_review",
            trigger=TransitionTrigger(trigger_type="event", event_name="submit")
        ),
        Transition(
            name="review_pass",
            from_state="pending_review",
            to_state="pending_approval",
            trigger=TransitionTrigger(trigger_type="event", event_name="review_complete"),
            guard="review_result == 'pass'"
        ),
        Transition(
            name="approve",
            from_state="pending_approval",
            to_state="approved",
            trigger=TransitionTrigger(trigger_type="event", event_name="approval_decision"),
            guard="decision == 'approve'"
        ),
        Transition(
            name="reject",
            from_state="pending_approval",
            to_state="rejected",
            trigger=TransitionTrigger(trigger_type="event", event_name="approval_decision"),
            guard="decision == 'reject'"
        ),
        Transition(
            name="escalate",
            from_state="pending_review",
            to_state="pending_approval",
            trigger=TransitionTrigger(trigger_type="timeout")
        ),
    ]
)
```

---

## 19. AI-Native Features（超越 UiPath/n8n）

**目標**：成為第一個 AI-Native 的自動化平台。

**Prerequisites / Assumptions：**
- 需要模型供應策略（雲端 + 本地）
- 需要安全與成本治理（rate limit / quota / audit）

### 19.1 LLM Integration

```python
@register_module(
    module_id='ai.llm.chat',
    category='ai',
    subcategory='llm',
    label='LLM Chat',
    params_schema=compose(
        field("provider", type="select",
            options=[
                {"value": "openai", "label": "OpenAI (GPT-4)"},
                {"value": "anthropic", "label": "Anthropic (Claude)"},
                {"value": "google", "label": "Google (Gemini)"},
                {"value": "local", "label": "Local (Ollama)"},
                {"value": "azure", "label": "Azure OpenAI"},
            ],
            default="openai"
        ),
        field("model", type="string",
            label="Model",
            dependsOn=["provider"],
            optionsFrom="getAvailableModels"  # 動態載入
        ),
        field("system_prompt", type="string",
            label="System Prompt",
            format="multiline"
        ),
        field("messages", type="array",
            label="Messages",
            description="Chat history"
        ),
        field("temperature", type="number",
            default=0.7,
            min=0,
            max=2,
            visibility="expert"
        ),
        field("max_tokens", type="number",
            default=4096,
            visibility="expert"
        ),
        field("tools", type="array",
            label="Available Tools",
            description="Functions the LLM can call",
            visibility="expert"
        ),
    )
)
class LLMChatModule(BaseModule):
    execution_mode = "single"
```

### 19.2 AI Agent Loop

```python
@register_module(
    module_id='ai.agent',
    category='ai',
    subcategory='agent',
    label='AI Agent',
    description='Autonomous agent that can use tools to accomplish tasks',
    params_schema=compose(
        field("task", type="string",
            label="Task Description",
            required=True,
            format="multiline"
        ),
        field("tools", type="array",
            label="Available Tools",
            description="Modules the agent can invoke"
        ),
        field("max_iterations", type="number",
            label="Max Iterations",
            default=10,
            min=1,
            max=100
        ),
        field("strategy", type="select",
            options=[
                {"value": "react", "label": "ReAct (Reasoning + Acting)"},
                {"value": "plan_execute", "label": "Plan then Execute"},
                {"value": "reflexion", "label": "Reflexion (Self-reflection)"},
            ],
            default="react"
        ),
        field("memory_type", type="select",
            options=[
                {"value": "buffer", "label": "Buffer (Recent N)"},
                {"value": "summary", "label": "Summary"},
                {"value": "vector", "label": "Vector Store"},
            ],
            default="buffer"
        ),
    )
)
class AIAgentModule(BaseModule):
    execution_mode = "single"

    async def execute(self) -> Dict[str, Any]:
        """執行 AI Agent loop"""
        task = self.params["task"]
        tools = self.params["tools"]
        max_iter = self.params["max_iterations"]
        strategy = self.params["strategy"]

        agent = self._create_agent(strategy)
        result = await agent.run(task, tools, max_iter)

        return self.success({
            "result": result.final_answer,
            "iterations": result.iteration_count,
            "tool_calls": result.tool_call_history,
            "reasoning_trace": result.reasoning_trace
        })
```

### 19.3 Workflow Self-Evolution

```python
@dataclass
class EvolutionSuggestion:
    """演化建議"""
    suggestion_id: str
    workflow_id: str
    suggestion_type: EvolutionType

    # 建議內容
    title: str
    description: str
    confidence: float  # 0-1

    # 變更
    proposed_changes: List[WorkflowChange]

    # 預期影響
    expected_improvement: Dict[str, float]  # {"success_rate": 0.05, "duration": -0.2}

    # 狀態
    status: str  # "pending" | "approved" | "rejected" | "applied"


class EvolutionType(Enum):
    ERROR_RECOVERY = "error_recovery"       # 自動修復常見錯誤
    PERFORMANCE = "performance"             # 效能優化
    RELIABILITY = "reliability"             # 可靠性改善
    SIMPLIFICATION = "simplification"       # 流程簡化
    COST_REDUCTION = "cost_reduction"       # 成本降低


class WorkflowEvolutionEngine:
    """Workflow 演化引擎"""

    async def analyze_execution_history(
        self,
        workflow_id: str,
        time_range: timedelta = timedelta(days=7)
    ) -> List[EvolutionSuggestion]:
        """分析執行歷史，生成演化建議"""
        pass

    async def apply_suggestion(
        self,
        suggestion_id: str,
        create_version: bool = True
    ) -> str:
        """套用建議，返回新版本 ID"""
        pass

    async def evaluate_suggestion(
        self,
        suggestion_id: str,
        test_cases: List[Dict[str, Any]]
    ) -> EvaluationResult:
        """評估建議效果"""
        pass
```

### 19.4 Natural Language to Workflow

```python
@register_module(
    module_id='ai.workflow.generate',
    category='ai',
    subcategory='workflow',
    label='Generate Workflow from Description',
    params_schema=compose(
        field("description", type="string",
            label="Workflow Description",
            required=True,
            format="multiline",
            placeholder="Describe what you want to automate..."
        ),
        field("context", type="object",
            label="Context",
            description="Available integrations, credentials, etc."
        ),
    )
)
class WorkflowGeneratorModule(BaseModule):
    """從自然語言生成 Workflow"""

    async def execute(self) -> Dict[str, Any]:
        description = self.params["description"]
        context = self.params.get("context", {})

        # 使用 LLM 生成 workflow YAML
        workflow_yaml = await self._generate_workflow(description, context)

        # 驗證生成的 workflow
        validation = await self._validate_workflow(workflow_yaml)

        return self.success({
            "workflow": workflow_yaml,
            "validation": validation,
            "explanation": self._generate_explanation(workflow_yaml)
        })
```

---

## 20. Updated Comparison

| 功能 | UiPath | n8n | Flyto 目標 |
|------|--------|-----|------------|
| Item-based execution | ✅ | ✅ | ✅ |
| Desktop automation | ✅ | ❌ | ✅ |
| AI Document Processing | ✅ | ❌ | ✅ |
| Process Mining | ✅ | ❌ | ✅ |
| Enterprise Orchestrator | ✅ | ⚠️ | ✅ |
| Queue & Transaction | ✅ | ❌ | ✅ |
| State Machine | ✅ | ❌ | ✅ |
| AI Agent | ⚠️ | ⚠️ | ✅ **超越** |
| Workflow Evolution | ❌ | ❌ | ✅ **獨創** |
| NL to Workflow | ⚠️ | ❌ | ✅ **超越** |
| Local-first | ❌ | ✅ | ✅ |
| Open Source Core | ❌ | ✅ | ✅ |

---

## 21. Implementation Priority

### Phase 1: Core Foundation（1-2 months）
1. Item-based execution pipeline
2. Dynamic schema conditions
3. Field-level validation

### Phase 2: RPA Capabilities（2-3 months）
4. Desktop automation (Windows/macOS)
5. Image recognition & OCR
6. AI Document Processing

### Phase 3: Enterprise（2-3 months）
7. Orchestrator (Scheduler, Queue, Robot Management)
8. State Machine (Long-running workflows)
9. Transaction support

### Phase 4: AI-Native（1-2 months）
10. LLM integration
11. AI Agent
12. Workflow Evolution
13. NL to Workflow

---

**End of Specification**
