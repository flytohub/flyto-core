#!/usr/bin/env python3
"""
测试 Spec Runner 动态验证

演示：
1. 使用 file.read 读取 Figma 提取的样式
2. 使用 file.read 读取期望样式
3. 动态比较两者的 key 覆盖率
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.modules.atomic.verify.spec_runner import (
    run_spec_ruleset,
    execute_module_dynamic,
    extract_keys,
)


async def test_dynamic_spec():
    """测试动态 spec 验证"""
    print("🧪 测试动态 Spec Runner\n")

    # 方式 1: 使用 YAML ruleset 格式 (内存中定义)
    ruleset = {
        "name": "Figma vs Expected Styles",
        "rules": [
            {
                "name": "style_keys_coverage",
                "source": {
                    "module": "file.read",
                    "params": {
                        "path": "./examples/happy-test/figma-styles.json"
                    }
                },
                "target": {
                    "module": "file.read",
                    "params": {
                        "path": "./examples/happy-test/expected-styles.json"
                    }
                },
                "compare": "bidirectional",
                "pass_criteria": "80%"  # 80% 覆盖率即通过
            }
        ]
    }

    print("📋 Ruleset:")
    print(f"   名称: {ruleset['name']}")
    print(f"   规则数: {len(ruleset['rules'])}")
    print()

    # 执行验证
    result = await run_spec_ruleset(ruleset)

    # 显示结果
    print("📊 验证结果:")
    print(f"   总规则数: {result['summary']['total_rules']}")
    print(f"   通过: {result['summary']['passed']}")
    print(f"   失败: {result['summary']['failed']}")
    print(f"   通过率: {result['summary']['pass_rate']}%")
    print()

    for r in result['results']:
        status = "✅" if r['passed'] else "❌"
        print(f"   {status} {r['name']}")
        print(f"      Source keys: {r['source_count']}")
        print(f"      Target keys: {r['target_count']}")
        print(f"      Matched: {r['matched_count']}")
        print(f"      Coverage: {r['coverage']}%")
        if r['missing_count'] > 0:
            print(f"      Missing in target: {r['missing_in_target'][:5]}...")
        if r['orphaned_count'] > 0:
            print(f"      Orphaned in target: {r['orphaned_in_target'][:5]}...")
        print()


async def test_module_execution():
    """测试单独模组执行"""
    print("🔧 测试单独模组执行\n")

    # 读取 Figma 样式
    result = await execute_module_dynamic("file.read", {
        "path": "./examples/happy-test/figma-styles.json"
    })

    if result.get('ok'):
        keys = extract_keys(result)
        print(f"   Figma styles keys: {sorted(keys)}")
    else:
        print(f"   ❌ Error: {result.get('error')}")

    # 读取期望样式
    result = await execute_module_dynamic("file.read", {
        "path": "./examples/happy-test/expected-styles.json"
    })

    if result.get('ok'):
        keys = extract_keys(result)
        print(f"   Expected styles keys: {sorted(keys)}")
    else:
        print(f"   ❌ Error: {result.get('error')}")


if __name__ == "__main__":
    print("=" * 60)
    asyncio.run(test_module_execution())
    print()
    print("=" * 60)
    asyncio.run(test_dynamic_spec())
