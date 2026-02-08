"""
Verify Module - Design-to-Code and Spec-as-Test verification

两种验证模式：
1. Style Verification: 比较浏览器渲染与设计稿 (Figma)
2. Spec Verification: 动态组合任意模组进行规格验证

Style Verification:
- verify.capture: 从浏览器获取计算样式
- verify.compare: 样式比较
- verify.figma: Figma API
- verify.report: 生成报告
- verify.ruleset: 加载 YAML 规则
- verify.run: 执行验证

Spec Verification (动态模式):
- verify.spec: 通过 YAML 配置动态组合任意模组

Usage:
    # Style 验证
    execute_module("verify.run", {
        "url": "http://localhost:3000",
        "selectors": ["button.primary"],
    })

    # Spec 验证 (动态组合)
    execute_module("verify.spec", {
        "ruleset_path": "./i18n-verify.yaml",
    })

    # 或者 inline ruleset
    execute_module("verify.spec", {
        "ruleset": {
            "name": "i18n check",
            "rules": [{
                "name": "translation coverage",
                "source": {
                    "module": "api.google_sheets.read",
                    "params": {"spreadsheet_id": "xxx", "range": "A:B"},
                    "key_field": "key"
                },
                "target": {
                    "module": "file.read_json",
                    "params": {"path": "locales/en.json"},
                },
                "compare": "bidirectional"
            }]
        }
    })
"""

# Style verification
from .capture import VerifyCaptureModule, CapturedElement
from .compare import VerifyCompareModule, CompareResult, Violation, Severity
from .figma import VerifyFigmaModule, FigmaStyle, FigmaNode
from .report import VerifyReportModule
from .ruleset import VerifyRulesetModule, Ruleset, Rule, load_ruleset, save_ruleset
from .runner import VerifyRunModule, VerifyRunner

# Spec verification (dynamic)
from .spec_runner import (
    VerifySpecModule,
    SpecResult,
    run_spec_rule,
    run_spec_ruleset,
    load_spec_ruleset,
    extract_keys,
    compare_keys,
)

# Visual annotation & diff
from .annotate import VerifyAnnotateModule, draw_annotations
from .visual_diff import VerifyVisualDiffModule

# Aliases
StyleComparator = VerifyCompareModule
BrowserCapture = VerifyCaptureModule

__all__ = [
    # Style verification
    "VerifyCaptureModule",
    "VerifyCompareModule",
    "VerifyFigmaModule",
    "VerifyReportModule",
    "VerifyRulesetModule",
    "VerifyRunModule",
    "VerifyRunner",
    "CapturedElement",
    "CompareResult",
    "Violation",
    "Severity",
    "FigmaStyle",
    "FigmaNode",
    "Ruleset",
    "Rule",
    "load_ruleset",
    "save_ruleset",

    # Spec verification (dynamic)
    "VerifySpecModule",
    "SpecResult",
    "run_spec_rule",
    "run_spec_ruleset",
    "load_spec_ruleset",
    "extract_keys",
    "compare_keys",

    # Visual annotation & diff
    "VerifyAnnotateModule",
    "draw_annotations",
    "VerifyVisualDiffModule",

    # Aliases
    "StyleComparator",
    "BrowserCapture",
]
