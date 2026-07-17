"""Credentials must be redacted from the execution trace (returned to clients)
and from on-disk checkpoint/params artifacts (P1-5 follow-up to evidence redaction)."""

import json
import os
import stat

from core.engine.trace import ExecutionTrace, StepInput


class TestExecutionTraceBoundary:
    """The headline bypass (pass-2 P1-5): a credential passed as a top-level
    recipe param is echoed back via ExecutionTrace.to_dict().inputParams (and
    output / error message). The full trace boundary must redact."""

    def test_input_params_redacted_in_returned_trace(self):
        trace = ExecutionTrace.create("wf", "My WF", {
            "api_key": "openai-redaction-placeholder",
            "dsn": "postgres://user:p4ssw0rd@db.internal/app",
            "label": "harmless",
        })
        d = trace.to_dict()
        blob = json.dumps(d)
        assert "openai-redaction-placeholder" not in blob
        assert "p4ssw0rd" not in blob
        assert "harmless" in blob  # non-secret preserved
        # the api_key key-name path also redacts
        assert d["inputParams"]["api_key"] == "[REDACTED]"

    def test_output_and_error_redacted(self):
        trace = ExecutionTrace.create("wf", "My WF", {})
        trace.complete({"leaked": "Bearer redaction-token-placeholder"})
        trace.fail(Exception("connect failed for postgres://u:secretpw@h/db"))
        blob = json.dumps(trace.to_dict())
        assert "redaction-token-placeholder" not in blob
        assert "secretpw" not in blob

    def test_private_key_and_basic_auth_redacted(self):
        from core.engine.redaction import redact_text
        pem = "-----BEGIN PRIVATE KEY-----\nMIIabc123\n-----END PRIVATE KEY-----"
        assert redact_text(pem) == "[REDACTED]"
        assert "dXNlcjpwYXNz" not in redact_text("Authorization: Basic dXNlcjpwYXNz")
        assert "placeholdertoken123456" not in redact_text(
            "Authorization: Bearer placeholdertoken123456"
        )


class TestTraceRedaction:
    def test_step_input_to_dict_redacts_params(self):
        si = StepInput(
            params={
                "url": "postgres://u:p4ssw0rd@db/app",
                "token": "step-redaction-placeholder",
            },
            paramsRaw={"password": "hunter2"},
        )
        d = si.to_dict()
        assert "p4ssw0rd" not in json.dumps(d["params"])
        assert "step-redaction-placeholder" not in json.dumps(d["params"])
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
            {"password": "topsecret", "note": "Bearer redaction-token-placeholder"}
        ))
        text = (run_dir / "params.json").read_text()
        assert "topsecret" not in text
        assert "redaction-token-placeholder" not in text
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
