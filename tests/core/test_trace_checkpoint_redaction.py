"""Credentials must be redacted from the execution trace (returned to clients)
and from on-disk checkpoint/params artifacts (P1-5 follow-up to evidence redaction)."""

import json
import os
import stat

from core.engine.trace import StepInput


class TestTraceRedaction:
    def test_step_input_to_dict_redacts_params(self):
        si = StepInput(
            params={"url": "postgres://u:p4ssw0rd@db/app", "token": "sk-ABCDEFGHIJKLMNOPQRST"},
            paramsRaw={"password": "hunter2"},
        )
        d = si.to_dict()
        assert "p4ssw0rd" not in json.dumps(d["params"])
        assert "sk-ABCDEFGHIJKLMNOPQRST" not in json.dumps(d["params"])
        assert d["paramsRaw"]["password"] == "[REDACTED]"

    def test_items_redacted(self):
        si = StepInput(params={}, paramsRaw={}, items=[{"api_key": "x"}], itemCount=1)
        d = si.to_dict()
        assert d["items"][0]["api_key"] == "[REDACTED]"


class TestCheckpointArtifacts:
    def test_params_json_redacted_and_locked(self, tmp_path, monkeypatch):
        import cli.recipe as recipe

        monkeypatch.setattr(recipe, "RUNS_DIR", tmp_path)
        run_dir = tmp_path / "latest"
        run_dir.mkdir(parents=True, exist_ok=True)
        recipe._save_json(run_dir / "params.json", recipe.redact_for_persistence(
            {"password": "topsecret", "note": "Bearer abcdef0123456789ABCD"}
        ))
        text = (run_dir / "params.json").read_text()
        assert "topsecret" not in text
        assert "abcdef0123456789ABCD" not in text
        # owner-only file perms
        mode = stat.S_IMODE(os.stat(run_dir / "params.json").st_mode)
        assert mode == 0o600

    def test_checkpoint_snapshot_redacts(self, tmp_path):
        import cli.recipe as recipe

        recipe._save_checkpoint_snapshot(
            tmp_path, 1, "step1",
            {"context": {"db_password": "s3cr3t", "x": "ok"}, "params": {"token": "t"}},
            "success",
        )
        text = (tmp_path / "checkpoint_001_step1.json").read_text()
        assert "s3cr3t" not in text
        assert '"x": "ok"' in text  # non-secret preserved
