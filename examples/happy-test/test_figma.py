#!/usr/bin/env python3
"""
测试 Figma API 连接

使用方式:
    export FIGMA_TOKEN="your-token"
    python test_figma.py
"""
import asyncio
import os
import sys

# 添加项目路径
sys.path.insert(0, '/Library/其他專案/flytohub/flyto-core')

from src.core.modules.atomic.verify.spec_runner import execute_module_dynamic


async def test_figma():
    token = os.environ.get('FIGMA_TOKEN')
    if not token:
        print("❌ 需要设置 FIGMA_TOKEN 环境变量")
        print("   export FIGMA_TOKEN='your-figma-personal-access-token'")
        print("\n获取方式: Figma → Settings → Account → Personal access tokens")
        return

    print("🎨 测试 Figma API...")
    print(f"   File ID: xE5iMjQQLKOinPwWaoCVOw")

    try:
        result = await execute_module_dynamic("verify.figma", {
            "file_id": "xE5iMjQQLKOinPwWaoCVOw",
            "token": token,
        })

        if result.get('ok'):
            data = result.get('data', {})
            node = data.get('node', {})
            print(f"\n✅ 成功获取 Figma 文件!")
            print(f"   文件名: {node.get('name', 'unknown')}")
            print(f"   类型: {node.get('type', 'unknown')}")

            # 显示子节点
            children = node.get('children', [])
            if children:
                print(f"\n   子节点 ({len(children)} 个):")
                for i, child in enumerate(children[:10]):
                    print(f"     {i+1}. {child.get('name', 'unnamed')} ({child.get('type', '')})")
                if len(children) > 10:
                    print(f"     ... 还有 {len(children) - 10} 个节点")
        else:
            print(f"\n❌ 失败: {result.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"\n❌ 错误: {e}")


if __name__ == "__main__":
    asyncio.run(test_figma())
