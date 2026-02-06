"""
Spec-as-Test Dynamic Runner

核心思想：YAML 描述要调用哪些模组，Runner 动态组合执行。
不写死 i18n/tracking 等类型，而是通用的 key 集合比较。

YAML 配置范例：
```yaml
name: "i18n 验证"
rules:
  - name: "翻译 key 覆盖"
    source:
      module: "api.google_sheets.read"
      params:
        spreadsheet_id: "xxx"
        range: "Sheet1!A:B"
      key_field: "key"      # 从结果中取哪个字段作为 key
    target:
      module: "file.glob"   # 或任意能返回 keys 的模组
      params:
        pattern: "locales/**/*.json"
      key_field: "keys"
    compare: "bidirectional"  # source_to_target | target_to_source | bidirectional
```
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union, Callable

from ...base import BaseModule
from ...registry import get_module, register_module
from ...schema import compose, field as schema_field


logger = logging.getLogger(__name__)


@dataclass
class SpecResult:
    """单条规则的验证结果"""
    name: str
    passed: bool
    source_keys: Set[str] = field(default_factory=set)
    target_keys: Set[str] = field(default_factory=set)
    matched: Set[str] = field(default_factory=set)
    missing_in_target: List[str] = field(default_factory=list)  # source 有但 target 没有
    orphaned_in_target: List[str] = field(default_factory=list)  # target 有但 source 没有
    error: Optional[str] = None

    @property
    def coverage(self) -> float:
        """计算覆盖率百分比

        Returns:
            100.0 if source_keys is empty (no spec = 100% coverage)
            Otherwise: matched / source_keys * 100
        """
        if not self.source_keys:
            return 100.0  # No source keys means nothing to cover
        return round(len(self.matched) / len(self.source_keys) * 100, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "coverage": self.coverage,
            "source_count": len(self.source_keys),
            "target_count": len(self.target_keys),
            "matched_count": len(self.matched),
            "missing_count": len(self.missing_in_target),
            "orphaned_count": len(self.orphaned_in_target),
            "missing_in_target": self.missing_in_target[:20],  # 限制输出
            "orphaned_in_target": self.orphaned_in_target[:20],
            "error": self.error,
        }


async def execute_module_dynamic(module_id: str, params: Dict[str, Any], context: Optional[Dict] = None) -> Dict[str, Any]:
    """动态执行任意 flyto-core 模组

    Args:
        module_id: 模组 ID，如 "file.read", "api.google_sheets.read"
        params: 模组参数
        context: 执行上下文

    Returns:
        模组执行结果 {"ok": bool, "data": ...}

    Raises:
        ValueError: 模组不存在
        Exception: 模组执行失败
    """
    try:
        module_class = get_module(module_id)
        if not module_class:
            raise ValueError(f"Module not found: {module_id}")

        ctx = context or {}
        instance = module_class(params, ctx)
        return await instance.execute()
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Module '{module_id}' execution failed: {e}")
        return {"ok": False, "error": str(e)}


def extract_keys(data: Any, key_field: Optional[str] = None) -> Set[str]:
    """从模组输出中提取 keys

    支持多种格式：
    - {"data": ["key1", "key2"]}
    - {"data": [{"key": "k1"}, {"key": "k2"}]}
    - {"data": {"content": "{json string}"}}  # file.read 返回的 JSON
    - {"keys": [...]}
    - {"items": [{"key": "..."}]}
    """
    if not data:
        return set()

    # 如果是 module 返回格式 {"ok": true, "data": {...}}
    if isinstance(data, dict) and "data" in data:
        inner = data["data"]
        # 处理 file.read 返回的 {"content": "..."}
        if isinstance(inner, dict) and "content" in inner:
            content = inner["content"]
            # 尝试解析为 JSON
            if isinstance(content, str):
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    # 不是 JSON，当作普通文本
                    return set()
            else:
                data = content
        else:
            data = inner

    # 指定了 key_field
    if key_field:
        if isinstance(data, dict):
            data = data.get(key_field, [])
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            return {str(item.get(key_field, "")) for item in data if item.get(key_field)}

    # 自动推断
    if isinstance(data, set):
        return {str(k) for k in data}

    if isinstance(data, list):
        if not data:
            return set()  # Empty list
        if isinstance(data[0], str):
            return set(data)  # List of strings
        if isinstance(data[0], dict):
            # 尝试常见字段名
            for field_name in ["key", "id", "name", "code"]:
                if field_name in data[0]:
                    return {str(item.get(field_name, "")) for item in data if item.get(field_name)}
            return set()  # List of dicts but no matching field

    if isinstance(data, dict):
        # 尝试常见容器字段
        for container in ["keys", "items", "data", "values", "rows"]:
            if container in data:
                return extract_keys(data[container], key_field)
        # 直接用 dict keys
        return set(data.keys())

    return set()


def compare_keys(
    source_keys: Set[str],
    target_keys: Set[str],
    direction: str = "bidirectional",
) -> tuple:
    """比较两个 key 集合

    Args:
        source_keys: 规格来源的 keys
        target_keys: 验证目标的 keys
        direction: source_to_target | target_to_source | bidirectional

    Returns:
        (matched, missing_in_target, orphaned_in_target)
    """
    matched = source_keys & target_keys
    missing_in_target = []
    orphaned_in_target = []

    if direction in ("source_to_target", "bidirectional"):
        missing_in_target = sorted(source_keys - target_keys)

    if direction in ("target_to_source", "bidirectional"):
        orphaned_in_target = sorted(target_keys - source_keys)

    return matched, missing_in_target, orphaned_in_target


async def run_spec_rule(rule: Dict[str, Any]) -> SpecResult:
    """执行单条验证规则"""
    name = rule.get("name", "unnamed")

    try:
        # 1. 执行 source 模组取得 keys
        source_config = rule.get("source", {})
        source_module = source_config.get("module")
        source_params = source_config.get("params", {})
        source_key_field = source_config.get("key_field")

        if source_module:
            source_result = await execute_module_dynamic(source_module, source_params)
            source_keys = extract_keys(source_result, source_key_field)
        else:
            # 直接提供 keys
            source_keys = set(source_config.get("keys", []))

        # 2. 执行 target 模组取得 keys
        target_config = rule.get("target", {})
        target_module = target_config.get("module")
        target_params = target_config.get("params", {})
        target_key_field = target_config.get("key_field")

        if target_module:
            target_result = await execute_module_dynamic(target_module, target_params)
            target_keys = extract_keys(target_result, target_key_field)
        else:
            target_keys = set(target_config.get("keys", []))

        # 3. 比较
        direction = rule.get("compare", "bidirectional")
        matched, missing, orphaned = compare_keys(source_keys, target_keys, direction)

        # 4. 判断是否通过
        # 默认：有 missing 就 fail
        pass_criteria = rule.get("pass_criteria", "no_missing")
        if pass_criteria == "no_missing":
            passed = len(missing) == 0
        elif pass_criteria == "no_orphaned":
            passed = len(orphaned) == 0
        elif pass_criteria == "exact":
            passed = len(missing) == 0 and len(orphaned) == 0
        else:
            # 自定义覆盖率
            min_coverage = float(pass_criteria.replace("%", "")) if "%" in str(pass_criteria) else 100
            coverage = len(matched) / len(source_keys) * 100 if source_keys else 100
            passed = coverage >= min_coverage

        return SpecResult(
            name=name,
            passed=passed,
            source_keys=source_keys,
            target_keys=target_keys,
            matched=matched,
            missing_in_target=missing,
            orphaned_in_target=orphaned,
        )

    except Exception as e:
        logger.error(f"Rule '{name}' failed: {e}")
        return SpecResult(name=name, passed=False, error=str(e))


async def run_spec_ruleset(ruleset: Dict[str, Any]) -> Dict[str, Any]:
    """执行整个 ruleset"""
    results = []
    for rule in ruleset.get("rules", []):
        if rule.get("enabled", True):
            result = await run_spec_rule(rule)
            results.append(result)

    # 汇总
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    total_missing = sum(len(r.missing_in_target) for r in results)
    total_orphaned = sum(len(r.orphaned_in_target) for r in results)

    return {
        "name": ruleset.get("name", "unnamed"),
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_rules": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total * 100, 1) if total else 100,
            "total_missing": total_missing,
            "total_orphaned": total_orphaned,
        },
        "results": [r.to_dict() for r in results],
    }


def load_spec_ruleset(path: Union[str, Path]) -> Dict[str, Any]:
    """从 YAML 文件加载 ruleset"""
    import yaml

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Ruleset not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# 模组注册
@register_module(
    module_id="verify.spec",
    version="1.0.0",
    category="verify",
    tags=["verify", "spec", "dynamic", "i18n", "tracking"],
    label="Run Spec Verification",
    label_key="modules.verify.spec.label",
    description="Dynamic spec verification - compose any modules via YAML",
    description_key="modules.verify.spec.description",
    icon="CheckSquare",
    color="#8B5CF6",
    input_types=["string", "object"],
    output_types=["object"],
    can_receive_from=["*"],
    can_connect_to=["*"],
    timeout_ms=300000,
    params_schema=compose(
        schema_field("ruleset_path", type="string", required=False,
                    description="Path to YAML ruleset file"),
        schema_field("ruleset", type="object", required=False,
                    description="Inline ruleset object"),
    ),
    output_schema={
        "passed": {"type": "boolean"},
        "summary": {"type": "object"},
        "results": {"type": "array"},
    },
)
class VerifySpecModule(BaseModule):
    """动态 Spec 验证模组"""

    module_name = "Spec Verification"
    module_description = "Compose any modules for spec verification"

    def validate_params(self) -> None:
        self.ruleset_path = self.params.get("ruleset_path")
        self.ruleset = self.params.get("ruleset")
        if not self.ruleset_path and not self.ruleset:
            raise ValueError("Either ruleset_path or ruleset is required")

    async def execute(self) -> Dict[str, Any]:
        if self.ruleset_path:
            ruleset = load_spec_ruleset(self.ruleset_path)
        else:
            ruleset = self.ruleset

        result = await run_spec_ruleset(ruleset)

        return {
            "ok": True,
            "data": {
                "passed": result["summary"]["failed"] == 0,
                **result,
            }
        }
