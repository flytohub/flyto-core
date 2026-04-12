# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Tests for Evolution Engine — Self-Heal, Self-Learn, Self-Grow.
"""

import json
import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ══════════════════════════════════════════════════════════════════
# EvolutionMemory Tests
# ══════════════════════════════════════════════════════════════════


class TestEvolutionMemory:
    def _make_memory(self, tmp_path):
        from core.engine.evolution.memory import EvolutionMemory
        path = os.path.join(str(tmp_path), "evolution.json")
        return EvolutionMemory(path=path), path

    def test_create_new(self, tmp_path):
        mem, path = self._make_memory(tmp_path)
        assert not os.path.exists(path)  # Not saved until first write
        mem.record_run("test-recipe", success=True)
        assert os.path.exists(path)

    def test_record_runs(self, tmp_path):
        mem, _ = self._make_memory(tmp_path)
        mem.record_run("r1", success=True)
        mem.record_run("r1", success=True)
        mem.record_run("r1", success=False)
        stats = mem.get_stats("r1")
        assert stats["runs"] == 3
        assert stats["successes"] == 2
        assert stats["failures"] == 1
        assert abs(stats["success_rate"] - 0.666) < 0.01

    def test_add_patch(self, tmp_path):
        mem, _ = self._make_memory(tmp_path)
        mem.add_patch("r1", {
            "step_id": "step_3",
            "fix_type": "replace_param",
            "param_key": "selector",
            "old_value": ".btn-old",
            "new_value": ".btn-new",
            "reason": "Button class changed",
        })
        patches = mem.get_patches("r1")
        assert len(patches) == 1
        assert patches[0]["new_value"] == ".btn-new"
        assert "timestamp" in patches[0]

    def test_deduplicate_patches(self, tmp_path):
        mem, _ = self._make_memory(tmp_path)
        patch = {
            "step_id": "s1",
            "fix_type": "replace_param",
            "param_key": "selector",
            "old_value": ".a",
            "new_value": ".b",
        }
        mem.add_patch("r1", dict(patch))
        mem.add_patch("r1", dict(patch))  # Same patch again
        assert len(mem.get_patches("r1")) == 1

    def test_filter_by_step(self, tmp_path):
        mem, _ = self._make_memory(tmp_path)
        mem.add_patch("r1", {"step_id": "s1", "fix_type": "replace_param", "param_key": "a", "new_value": "1"})
        mem.add_patch("r1", {"step_id": "s2", "fix_type": "replace_param", "param_key": "b", "new_value": "2"})
        assert len(mem.get_patches("r1", step_id="s1")) == 1
        assert len(mem.get_patches("r1", step_id="s2")) == 1
        assert len(mem.get_patches("r1")) == 2

    def test_persistence(self, tmp_path):
        mem, path = self._make_memory(tmp_path)
        mem.record_run("r1", success=True)
        mem.add_patch("r1", {"step_id": "s1", "fix_type": "add_param", "param_key": "wait", "new_value": 2000})

        # Reload from disk
        from core.engine.evolution.memory import EvolutionMemory
        mem2 = EvolutionMemory(path=path)
        assert mem2.get_stats("r1")["runs"] == 1
        assert len(mem2.get_patches("r1")) == 1

    def test_max_patches(self, tmp_path):
        mem, _ = self._make_memory(tmp_path)
        for i in range(60):
            mem.add_patch("r1", {"step_id": f"s{i}", "fix_type": "replace_param", "param_key": f"p{i}", "new_value": i})
        assert len(mem.get_patches("r1")) == 50  # Capped

    def test_get_all_stats(self, tmp_path):
        mem, _ = self._make_memory(tmp_path)
        mem.record_run("r1", True)
        mem.record_run("r2", False)
        all_stats = mem.get_all_stats()
        assert "r1" in all_stats
        assert "r2" in all_stats


# ══════════════════════════════════════════════════════════════════
# StepHealer Tests
# ══════════════════════════════════════════════════════════════════


class TestIsHealable:
    def test_healable_selector_not_found(self):
        from core.engine.evolution.healer import is_healable
        assert is_healable("browser.click", Exception("Element selector '.btn' not found"))

    def test_healable_timeout(self):
        from core.engine.evolution.healer import is_healable
        assert is_healable("browser.wait", Exception("Timeout 30000ms exceeded"))

    def test_healable_not_visible(self):
        from core.engine.evolution.healer import is_healable
        assert is_healable("browser.click", Exception("Element is not visible"))

    def test_not_healable_non_browser(self):
        from core.engine.evolution.healer import is_healable
        assert not is_healable("data.json_parse", Exception("selector not found"))

    def test_not_healable_unknown_error(self):
        from core.engine.evolution.healer import is_healable
        assert not is_healable("browser.click", Exception("some random error"))


class TestStepHealerApplyPatches:
    def test_apply_replace_param(self, tmp_path):
        from core.engine.evolution.memory import EvolutionMemory
        from core.engine.evolution.healer import StepHealer

        mem = EvolutionMemory(path=os.path.join(str(tmp_path), "evo.json"))
        mem.add_patch("recipe1", {
            "step_id": "click_submit",
            "fix_type": "replace_param",
            "param_key": "selector",
            "old_value": ".btn-submit",
            "new_value": "button[type='submit']",
            "reason": "class changed",
        })

        healer = StepHealer(memory=mem)
        step = {"id": "click_submit", "module": "browser.click", "params": {"selector": ".btn-submit"}}
        patched = healer.apply_known_patches("recipe1", step)
        assert patched["params"]["selector"] == "button[type='submit']"

    def test_apply_add_param(self, tmp_path):
        from core.engine.evolution.memory import EvolutionMemory
        from core.engine.evolution.healer import StepHealer

        mem = EvolutionMemory(path=os.path.join(str(tmp_path), "evo.json"))
        mem.add_patch("recipe1", {
            "step_id": "wait_load",
            "fix_type": "add_param",
            "param_key": "duration_ms",
            "old_value": None,
            "new_value": 5000,
            "reason": "page loads slowly",
        })

        healer = StepHealer(memory=mem)
        step = {"id": "wait_load", "module": "browser.wait", "params": {}}
        patched = healer.apply_known_patches("recipe1", step)
        assert patched["params"]["duration_ms"] == 5000

    def test_no_patch_for_different_step(self, tmp_path):
        from core.engine.evolution.memory import EvolutionMemory
        from core.engine.evolution.healer import StepHealer

        mem = EvolutionMemory(path=os.path.join(str(tmp_path), "evo.json"))
        mem.add_patch("r1", {"step_id": "s1", "fix_type": "replace_param", "param_key": "x", "old_value": "a", "new_value": "b"})

        healer = StepHealer(memory=mem)
        step = {"id": "s2", "module": "browser.click", "params": {"x": "a"}}
        patched = healer.apply_known_patches("r1", step)
        assert patched["params"]["x"] == "a"  # Unchanged


class TestStepHealerParseResponse:
    def test_parse_valid_fix(self):
        from core.engine.evolution.healer import StepHealer
        healer = StepHealer()
        response = '{"fix_type": "replace_param", "param_key": "selector", "old_value": ".old", "new_value": ".new", "reason": "changed"}'
        fix = healer._parse_fix_response(response)
        assert fix is not None
        assert fix["param_key"] == "selector"

    def test_parse_none_fix(self):
        from core.engine.evolution.healer import StepHealer
        healer = StepHealer()
        assert healer._parse_fix_response('{"fix_type": "none"}') is None

    def test_parse_markdown_wrapped(self):
        from core.engine.evolution.healer import StepHealer
        healer = StepHealer()
        response = '```json\n{"fix_type": "replace_param", "param_key": "sel", "old_value": "a", "new_value": "b", "reason": "x"}\n```'
        fix = healer._parse_fix_response(response)
        assert fix is not None

    def test_parse_invalid_json(self):
        from core.engine.evolution.healer import StepHealer
        healer = StepHealer()
        assert healer._parse_fix_response("not json at all") is None


# ══════════════════════════════════════════════════════════════════
# WorkflowCompiler Tests
# ══════════════════════════════════════════════════════════════════


class TestActionRecorder:
    def test_record_actions(self):
        from core.engine.evolution.compiler import ActionRecorder
        rec = ActionRecorder()
        rec.record("browser.goto", {"url": "https://example.com"}, {"ok": True})
        rec.record("browser.click", {"selector": ".btn"}, {"ok": True})
        rec.record("browser.click", {"selector": ".missing"}, {"ok": False, "error": "not found"})
        assert len(rec.actions) == 3
        assert len(rec.get_successful_actions()) == 2

    def test_empty_recorder(self):
        from core.engine.evolution.compiler import ActionRecorder
        rec = ActionRecorder()
        assert rec.get_successful_actions() == []


class TestWorkflowCompiler:
    def test_compile_basic(self):
        from core.engine.evolution.compiler import ActionRecorder, WorkflowCompiler
        rec = ActionRecorder()
        rec.record("browser.goto", {"url": "https://example.com"}, {"ok": True})
        rec.record("browser.screenshot", {"path": "test.png"}, {"ok": True})

        compiler = WorkflowCompiler()
        yaml_str = compiler.compile(rec, name="test-recipe")
        assert "test-recipe" in yaml_str
        assert "browser.goto" in yaml_str
        assert "browser.screenshot" in yaml_str
        assert "browser.launch" in yaml_str  # Auto-added
        assert "browser.close" in yaml_str   # Auto-added

    def test_compile_empty(self):
        from core.engine.evolution.compiler import ActionRecorder, WorkflowCompiler
        rec = ActionRecorder()
        compiler = WorkflowCompiler()
        assert compiler.compile(rec) == ""

    def test_deduplicate(self):
        from core.engine.evolution.compiler import ActionRecorder, WorkflowCompiler
        rec = ActionRecorder()
        rec.record("browser.click", {"selector": ".btn"}, {"ok": True})
        rec.record("browser.click", {"selector": ".btn"}, {"ok": True})  # Duplicate
        rec.record("browser.click", {"selector": ".other"}, {"ok": True})  # Different

        compiler = WorkflowCompiler()
        yaml_str = compiler.compile(rec, name="test")
        # Should have launch + 2 clicks + close = 4 steps, not 5
        assert yaml_str.count("browser.click") == 2

    def test_templatize_variables(self):
        from core.engine.evolution.compiler import ActionRecorder, WorkflowCompiler
        rec = ActionRecorder()
        rec.record("browser.goto", {"url": "https://example.com/products"}, {"ok": True})

        compiler = WorkflowCompiler()
        yaml_str = compiler.compile(rec, name="test", variables={"url": "https://example.com/products"})
        assert "[[url]]" in yaml_str

    def test_compile_from_agent_steps(self):
        from core.engine.evolution.compiler import WorkflowCompiler
        steps = [
            {"type": "tool_call", "tool": "browser--goto", "arguments": {"url": "https://test.com"}},
            {"type": "tool_result", "tool": "browser--goto", "result": {"ok": True}},
            {"type": "tool_call", "tool": "browser--click", "arguments": {"selector": "#btn"}},
            {"type": "tool_call", "tool": "data--json_parse", "arguments": {"input": "{}"}},  # Non-browser, ignored
            {"type": "final_answer", "content": "done"},
        ]

        compiler = WorkflowCompiler()
        yaml_str = compiler.compile_from_steps(steps, name="from-agent")
        assert "browser.goto" in yaml_str
        assert "browser.click" in yaml_str
        assert "data" not in yaml_str  # Non-browser excluded
        assert "browser.launch" in yaml_str

    def test_optimize_merges_waits(self):
        from core.engine.evolution.compiler import ActionRecorder, WorkflowCompiler
        rec = ActionRecorder()
        rec.record("browser.wait", {"duration_ms": 1000}, {"ok": True})
        rec.record("browser.wait", {"duration_ms": 3000}, {"ok": True})

        compiler = WorkflowCompiler()
        yaml_str = compiler.compile(rec, name="test")
        # Should merge to one wait with max duration
        assert yaml_str.count("browser.wait") == 1
        assert "3000" in yaml_str

    def test_auto_generated_flag(self):
        import yaml as yaml_lib
        from core.engine.evolution.compiler import ActionRecorder, WorkflowCompiler
        rec = ActionRecorder()
        rec.record("browser.goto", {"url": "https://test.com"}, {"ok": True})

        compiler = WorkflowCompiler()
        yaml_str = compiler.compile(rec, name="test")
        parsed = yaml_lib.safe_load(yaml_str)
        assert parsed["auto_generated"] is True
        assert "generated_at" in parsed
