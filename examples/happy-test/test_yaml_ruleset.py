#!/usr/bin/env python3
"""
测试从 YAML 文件加载 ruleset

演示完整的 Spec-as-Test 工作流:
1. 从 YAML 读取验证规则
2. 动态执行任意 flyto-core 模组
3. 比较结果并生成报告
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.modules.atomic.verify.spec_runner import (
    load_spec_ruleset,
    run_spec_ruleset,
)


async def main():
    print("📂 从 YAML 加载 Ruleset\n")

    # 加载 YAML
    ruleset = load_spec_ruleset("./examples/happy-test/style-verify.yaml")

    print(f"   名称: {ruleset['name']}")
    print(f"   规则数: {len(ruleset['rules'])}")
    for rule in ruleset['rules']:
        print(f"   - {rule['name']}")
    print()

    # 执行验证
    print("🔍 执行验证...\n")
    result = await run_spec_ruleset(ruleset)

    # 显示结果
    print("=" * 50)
    print(f"📊 {result['name']}")
    print("=" * 50)
    print(f"   时间: {result['timestamp']}")
    print(f"   总规则: {result['summary']['total_rules']}")
    print(f"   通过率: {result['summary']['pass_rate']}%")
    print()

    for r in result['results']:
        status = "✅ PASS" if r['passed'] else "❌ FAIL"
        print(f"{status} | {r['name']}")
        print(f"       Coverage: {r['coverage']}%")
        print(f"       Source: {r['source_count']} keys")
        print(f"       Target: {r['target_count']} keys")
        print(f"       Matched: {r['matched_count']}")
        if r['missing_count'] > 0:
            print(f"       Missing: {r['missing_in_target']}")
        if r['orphaned_count'] > 0:
            print(f"       Orphaned: {r['orphaned_in_target']}")
        if r['error']:
            print(f"       Error: {r['error']}")
        print()

    # 最终状态
    all_passed = result['summary']['failed'] == 0
    print("=" * 50)
    print(f"{'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
