"""What a host is told about a step: whether it failed, and what it was given.

Both reproduced from a real run log before this file existed
(``~/.flyto/runs/<id>/steps.jsonl``):

* A ``browser.type`` step under ``on_error: continue`` could not find its field.
  The engine absorbed the exception into ``{ok: False, error, outcome}`` and
  called the post-execute hook with ``error=None``. Every host decides success
  on ``context.error``, so the step was logged ``step_succeeded`` and the run
  carried on as if the login had been typed.
* The same step's ``input_params`` carried the password in plaintext under
  ``text``: the hook context held the raw step params, and neither ``text`` nor
  ``sensitive_text`` is named like a credential.
"""
import pytest

from core.engine.hooks import ExecutorHooks, HookResult
from core.engine.redaction import (
    SENSITIVE_PARAMS_KEY,
    is_sensitive_param_name,
    redact_step_params,
)
from core.engine.step_executor.executor import StepExecutor
from core.engine.trace import TraceCollector
from core.engine.variable_resolver import VariableResolver
from core.modules import atomic  # noqa: F401 - registers production modules
from core.modules.registry import ModuleRegistry, register_module

SECRET = "hunter2-not-real"


class RecordingHooks(ExecutorHooks):
    def __init__(self):
        self.pre = []
        self.post = []

    def on_pre_execute(self, context):
        self.pre.append(context)
        return HookResult.continue_execution()

    def on_post_execute(self, context):
        self.post.append(context)
        return HookResult.continue_execution()


def _executor(hooks):
    return StepExecutor(hooks=hooks, workflow_id="wf", workflow_name="wf", total_steps=1)


def _register(module_id, fn, params_schema=None):
    if not ModuleRegistry.has(module_id):
        register_module(
            module_id=module_id,
            version="1.0.0",
            category="testing",
            tags=["test"],
            label=module_id,
            description="test module",
            icon="Box",
            color="#000000",
            input_types=["any"],
            output_types=["any"],
            can_receive_from=["*"],
            can_connect_to=["*"],
            params_schema=params_schema,
        )(fn)
    return module_id


async def _raises(ctx):
    raise RuntimeError("Could not find input field")


async def _reports_sensitive(ctx):
    return {"status": "success", SENSITIVE_PARAMS_KEY: ["text"]}


async def _plain(ctx):
    return {"status": "success"}


async def run(step, hooks=None, collector=None, context=None):
    hooks = hooks or RecordingHooks()
    context = {} if context is None else context
    result = await _executor(hooks).execute_step(
        step_config=step,
        step_index=0,
        context=context,
        resolver=VariableResolver({}, context),
        trace_collector=collector,
    )
    return result, hooks


class TestAbsorbedFailureReachesTheHookAsAFailure:
    async def test_continue_still_continues(self):
        module_id = _register("test.record.raises", _raises)
        result, _ = await run({"id": "s", "module": module_id, "on_error": "continue"})
        assert result["ok"] is False

    async def test_the_post_execute_hook_sees_the_error(self):
        module_id = _register("test.record.raises", _raises)
        _, hooks = await run({"id": "s", "module": module_id, "on_error": "continue"})
        post = hooks.post[-1]
        assert post.error is not None
        assert "Could not find input field" in post.error_message
        assert post.metadata["outcome"]["rung"] == "failed"

    async def test_the_trace_records_a_failed_step(self):
        module_id = _register("test.record.raises", _raises)
        collector = TraceCollector("wf", "wf")
        collector.start()
        await run({"id": "s", "module": module_id, "on_error": "continue"},
                  collector=collector)
        step = collector.get_trace().steps[0]
        assert step.status == "error"
        assert collector.get_trace().failed_step_count == 1

    async def test_a_success_is_still_a_success(self):
        module_id = _register("test.record.plain", _plain)
        _, hooks = await run({"id": "s", "module": module_id, "on_error": "continue"})
        assert hooks.post[-1].error is None

    async def test_the_absorbed_error_does_not_leak_into_the_next_step(self):
        failing = _register("test.record.raises", _raises)
        plain = _register("test.record.plain", _plain)
        hooks = RecordingHooks()
        executor = _executor(hooks)
        context = {}
        for module_id in (failing, plain):
            await executor.execute_step(
                step_config={"id": "same", "module": module_id, "on_error": "continue"},
                step_index=0,
                context=context,
                resolver=VariableResolver({}, context),
            )
        assert hooks.post[0].error is not None
        assert hooks.post[1].error is None

    async def test_stop_policy_is_unchanged(self):
        from core.engine.exceptions import StepExecutionError

        module_id = _register("test.record.raises", _raises)
        hooks = RecordingHooks()
        with pytest.raises(StepExecutionError):
            await run({"id": "s", "module": module_id}, hooks=hooks)
        assert hooks.post[-1].error is not None


class TestParamsHandedToHooksAreRedacted:
    async def test_browser_type_password_by_label_is_redacted_before_the_step_runs(self):
        """The leaked shape: input_type text, label Password, literal text."""
        step = {
            "id": "s",
            "module": "browser.type",
            "on_error": "continue",
            "params": {"type_method": "label", "target": "Password",
                       "input_type": "text", "text": SECRET},
        }
        _, hooks = await run(step)   # no browser: fails, continues
        for ctx in hooks.pre + hooks.post:
            assert SECRET not in repr(ctx.params)
            assert ctx.params["text"] == "[REDACTED]"
            assert ctx.params["target"] == "Password"

    async def test_schema_secret_field_is_redacted(self):
        step = {
            "id": "s",
            "module": "browser.type",
            "on_error": "continue",
            "params": {"type_method": "id", "target": "pw", "input_type": "password",
                       "sensitive_text": SECRET},
        }
        _, hooks = await run(step)
        assert hooks.pre[0].params["sensitive_text"] == "[REDACTED]"

    async def test_ordinary_text_stays_readable(self):
        step = {
            "id": "s",
            "module": "browser.type",
            "on_error": "continue",
            "params": {"type_method": "label", "target": "Email", "text": "a@example.test"},
        }
        _, hooks = await run(step)
        assert hooks.pre[0].params["text"] == "a@example.test"

    async def test_runtime_report_redacts_the_post_hook_and_the_trace(self):
        module_id = _register(
            "test.record.reports_sensitive",
            _reports_sensitive,
            params_schema={"text": {"type": "string"}},
        )
        collector = TraceCollector("wf", "wf")
        collector.start()
        _, hooks = await run(
            {"id": "s", "module": module_id, "params": {"text": SECRET}},
            collector=collector,
        )
        assert hooks.post[-1].params["text"] == "[REDACTED]"
        trace = collector.get_trace().to_dict()
        assert SECRET not in repr(trace)

    async def test_resolved_env_secret_is_not_in_the_trace(self):
        module_id = _register(
            "test.record.plain_schema",
            _plain,
            params_schema={"password": {"type": "string"}},
        )
        collector = TraceCollector("wf", "wf")
        collector.start()
        context = {"creds": {"pw": SECRET}}
        await run(
            {"id": "s", "module": module_id, "params": {"password": "${creds.pw}"}},
            collector=collector,
            context=context,
        )
        assert SECRET not in repr(collector.get_trace().to_dict())

    async def test_the_module_still_receives_the_plaintext(self):
        seen = {}

        async def capture(ctx):
            seen.update(ctx["params"])
            return {"status": "success"}

        module_id = _register("test.record.capture", capture)
        _, hooks = await run({"id": "s", "module": module_id,
                              "params": {"password": SECRET}})
        assert seen["password"] == SECRET
        assert hooks.pre[0].params["password"] == "[REDACTED]"


class TestRedactStepParams:
    @pytest.mark.parametrize("name", [
        "password", "db_password", "passwd", "api_key", "apiKey", "client_secret",
        "access_token", "token", "sensitive_text", "private_key", "passphrase",
    ])
    def test_credential_names(self, name):
        assert is_sensitive_param_name(name)

    @pytest.mark.parametrize("name", [
        "text", "author", "session_id", "max_tokens", "case_sensitive", "keyword",
        "target", "selector",
    ])
    def test_ordinary_names(self, name):
        assert not is_sensitive_param_name(name)

    def test_bare_references_and_empty_values_stay_visible(self):
        out = redact_step_params(None, {
            "password": "{{env.LOGIN_PASSWORD}}",
            "api_key": "${env.KEY}",
            "secret": "",
            "token": None,
            "use_token": True,
        })
        assert out == {
            "password": "{{env.LOGIN_PASSWORD}}",
            "api_key": "${env.KEY}",
            "secret": "",
            "token": None,
            "use_token": True,
        }

    def test_nested_credential_names(self):
        out = redact_step_params(None, {"auth": {"password": SECRET, "user": "u"}})
        assert out == {"auth": {"password": "[REDACTED]", "user": "u"}}

    def test_input_is_not_mutated(self):
        params = {"password": SECRET}
        redact_step_params(None, params)
        assert params == {"password": SECRET}

    def test_unknown_module_falls_back_to_names(self):
        out = redact_step_params("no.such.module", {"text": "t", "password": SECRET})
        assert out == {"text": "t", "password": "[REDACTED]"}

    def test_template_invoke_suffix_is_looked_up_as_template_invoke(self):
        out = redact_step_params("template.invoke:abc", {"password": SECRET})
        assert out["password"] == "[REDACTED]"


class ResolvesReferences(ExecutorHooks):
    """A host's pre-execute hook: rewrites credential references in place.

    Mirrors the shape Cloud's credential resolver uses -- a mapping
    ``{"type": "secretRef", "credential_name": ...}`` replaced by the value --
    which only works if what the hook rewrites reaches the module.
    """

    def __init__(self):
        self.seen = []

    def on_pre_execute(self, context):
        self.seen.append(context.params)

        def walk(value):
            if isinstance(value, dict):
                if value.get("type") == "secretRef":
                    return f"resolved:{value.get('credential_name')}"
                for key in list(value):
                    value[key] = walk(value[key])
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    value[index] = walk(item)
            return value

        walk(context.params)
        return HookResult.continue_execution()


async def _echo_params(ctx):
    return {"status": "success", "got": dict(ctx["params"])}


class TestPreExecuteHookRewritesReachTheModule:
    """Regression: 2.36.1 handed hooks a redacted copy and dropped their edits.

    A host that resolves credential references in ``on_pre_execute`` then
    passed the unresolved reference to the module -- every credential-backed
    step ran without its credential.
    """

    async def test_resolved_references_reach_the_module(self):
        module_id = _register("test.record.echo_params_ref", _echo_params)
        step = {"id": "s", "module": module_id, "params": {
            "value": {"type": "secretRef", "credential_name": "api"},
            "api_key": {"type": "secretRef", "credential_name": "api"},
            "headers": {"Authorization": {"type": "secretRef", "credential_name": "tok"}},
            "items": [{"type": "secretRef", "credential_name": "x"}],
            "password": "literal-not-a-ref",
            "url": "https://example.test",
        }}
        hooks = ResolvesReferences()
        result, _ = await run(step, hooks=hooks)
        got = result["got"]
        assert got["value"] == "resolved:api"
        assert got["api_key"] == "resolved:api"
        assert got["headers"] == {"Authorization": "resolved:tok"}
        assert got["items"] == ["resolved:x"]
        # What the hook saw as [REDACTED] never overwrites the real value.
        assert got["password"] == "literal-not-a-ref"
        assert got["url"] == "https://example.test"

    async def test_the_hook_sees_references_not_secrets(self):
        module_id = _register("test.record.echo_params_ref", _echo_params)
        hooks = ResolvesReferences()
        step = {"id": "s", "module": module_id, "params": {
            "api_key": {"type": "secretRef", "credential_name": "api"},
            "password": SECRET,
        }}
        await run(step, hooks=hooks)
        assert SECRET not in repr(hooks.seen)

    async def test_a_hook_that_changes_nothing_changes_nothing(self):
        module_id = _register("test.record.echo_params_ref", _echo_params)
        step = {"id": "s", "module": module_id, "params": {"password": SECRET, "n": 1}}
        result, _ = await run(step)
        got = {k: v for k, v in result["got"].items() if not k.startswith("$")}
        assert got == {"password": SECRET, "n": 1}
        assert step["params"] == {"password": SECRET, "n": 1}


class TestNameRuleCoversHeadersAndCamelCase:
    @pytest.mark.parametrize("name", [
        "Authorization", "Cookie", "accessToken", "refreshToken", "idToken",
        "authToken", "clientSecret", "x-api-key",
    ])
    def test_credential_names(self, name):
        assert is_sensitive_param_name(name)

    @pytest.mark.parametrize("name", [
        "maxTokens", "max_tokens", "credential_name", "secret_id", "api_key_ref",
        "author", "session_id", "tokenizer",
    ])
    def test_labels_and_lookalikes_stay_visible(self, name):
        assert not is_sensitive_param_name(name)

    def test_a_header_value_is_redacted_for_hooks(self):
        redacted = redact_step_params("http.request", {
            "headers": {"Authorization": f"Bearer {SECRET}", "Accept": "json"},
        })
        assert redacted["headers"] == {"Authorization": "[REDACTED]", "Accept": "json"}

    def test_a_list_under_a_credential_name_is_redacted(self):
        assert redact_step_params("x.y", {"api_keys": [SECRET]})["api_keys"] == "[REDACTED]"


class TestResourceSubNodeHooks:
    """A resource sub-node (an ``ai.model`` carrying ``api_key``) reaches the
    same hooks as a step; it used to hand them its raw params."""

    async def test_sub_node_params_are_redacted_and_rewrites_kept(self):
        from core.engine.workflow.engine import WorkflowEngine

        module_id = _register("test.record.echo_params_ref", _echo_params)
        hooks = ResolvesReferences()
        engine = WorkflowEngine({"steps": []}, hooks=hooks)
        engine._router._step_map = {"model": {"id": "model", "module": module_id, "params": {
            "api_key": SECRET,
            "token": {"type": "secretRef", "credential_name": "tok"},
        }}}
        engine._router._resource_edges = {"agent": {"model": ["model"]}}
        await engine._execute_resource_sub_nodes("agent")

        assert SECRET not in repr(hooks.seen)
        got = engine.context["inputs"]["model"]["got"]
        assert got["api_key"] == SECRET
        assert got["token"] == "resolved:tok"
