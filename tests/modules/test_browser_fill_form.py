"""browser.fill_form fills, uploads and submits a whole form in one call.

The real-browser classes render ``tests/fixtures/fill_form_page.html`` into
Chromium and check the page itself afterwards, not the module's own report: the
label association, the selected option and the attached file are decided by the
DOM, and a stub would only test that the stub agrees with itself.

The unmarked classes cover parameter validation, redaction and the registered
contract, which need no browser and run in every CI job.
"""
import contextlib
from pathlib import Path

import pytest

from core.engine.redaction import SENSITIVE_PARAMS_KEY, redact_step_params
from core.modules import atomic  # noqa: F401 - registers every module
from core.modules.registry import ModuleRegistry

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "fill_form_page.html"


async def run(params, context):
    return await ModuleRegistry.get("browser.fill_form")(params, context).execute()


# ---------------------------------------------------------------------------
# No browser
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_contract_declares_an_external_non_idempotent_effect(self):
        """An external write (level 3), not a real-world actuation (level 4).

        ``actuates: true`` would make hosts grade every form fill as a
        DANGER_FULL confirmation, above the browser.type calls it replaces.
        """
        meta = ModuleRegistry.get_metadata("browser.fill_form")
        contract = meta["contract"]
        assert contract["actuates"] is False
        assert contract["safety_class"] == "controlled"
        assert contract["idempotent"] is False
        assert contract["effects"] == ["external.record.changed"]
        assert meta["provides_capability"] == "browser.fill_form"

    def test_description_steers_to_one_call(self):
        description = ModuleRegistry.get_metadata("browser.fill_form")["ui_description"]
        assert "ONE call" in description
        assert "browser.snapshot" in description


class TestParameters:
    def build(self, params):
        return ModuleRegistry.get("browser.fill_form")(params, {})

    def test_needs_fields_or_uploads(self):
        with pytest.raises(ValueError, match="at least one"):
            self.build({})

    def test_a_field_needs_a_label_or_selector(self):
        with pytest.raises(ValueError, match="label"):
            self.build({"fields": [{"value": "x"}]})

    def test_a_field_needs_a_value(self):
        with pytest.raises(ValueError, match="value"):
            self.build({"fields": [{"label": "Name"}]})

    def test_confirm_requires_submit(self):
        with pytest.raises(ValueError, match="submit"):
            self.build({"fields": [{"label": "A", "value": "b"}], "confirm": {"text": "ok"}})

    def test_upload_outside_the_sandbox_is_refused(self, tmp_path, monkeypatch):
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        monkeypatch.setenv("FLYTO_SANDBOX_DIR", str(sandbox))
        monkeypatch.delenv("FLYTO_ALLOW_ABSOLUTE_PATHS", raising=False)
        outside = tmp_path / "secret.txt"
        outside.write_text("x")
        with pytest.raises(Exception):  # noqa: B017 - PathTraversalError or ValueError
            self.build({"uploads": [{"label": "Photo", "path": str(outside)}]})


class TestRedaction:
    def test_a_value_for_a_credential_label_withholds_the_whole_fields_list(self):
        params = {"fields": [
            {"label": "Email", "value": "a@example.test"},
            {"label": "Password", "value": "hunter2-not-real"},
        ]}
        recorded = redact_step_params("browser.fill_form", params)
        assert "hunter2-not-real" not in repr(recorded)

    def test_sensitive_value_is_redacted_by_its_name(self):
        params = {"fields": [
            {"label": "Email", "value": "a@example.test"},
            {"label": "Code", "sensitive_value": "123456-not-real"},
        ]}
        recorded = redact_step_params("browser.fill_form", params)
        assert "123456-not-real" not in repr(recorded)
        # Non-secret fields stay readable for debugging.
        assert "a@example.test" in repr(recorded)


# ---------------------------------------------------------------------------
# Real Chromium
# ---------------------------------------------------------------------------


@pytest.fixture
async def page_ctx():
    from core.browser.driver import BrowserDriver

    driver = BrowserDriver(headless=True)
    await driver.launch(stealth=False)
    try:
        await driver.real_page.set_content(FIXTURE.read_text(encoding="utf-8"))
        yield {"browser": driver}
    finally:
        with contextlib.suppress(Exception):
            await driver.close()


@pytest.fixture
def photo(sandboxed_tmp_path):
    path = sandboxed_tmp_path / "evidence.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    return path


FULL_FIELDS = [
    {"label": "Task ID", "value": "TASK-1"},
    {"label": "Result", "value": "Delivered"},
    {"label": "Distance moved", "value": 120},
    {"label": "Location", "value": "Room 501"},
    {"label": "Operator", "value": "Dana"},
    {"label": "Date", "value": "2026-10-04"},
    {"label": "Notes", "value": "Arrived without incident"},
    {"label": "Notify supervisor", "value": True},
    {"label": "Priority", "value": "High"},
]


@pytest.mark.browser
class TestFillAndSubmit:
    async def test_every_field_upload_and_submit_in_one_call(self, page_ctx, photo):
        result = await run({
            "fields": FULL_FIELDS,
            "uploads": [{"label": "Photo", "path": str(photo)}],
            "submit": {"label": "Save record"},
            "confirm": {"selector": "#receipt"},
        }, page_ctx)

        assert result["ok"] is True, result.get("error")
        assert result["submitted"] is True and result["confirmed"] is True
        assert all(f["matches"] for f in result["fields"]), result["fields"]
        assert result["uploads"][0]["files"] == ["evidence.png"]
        assert result["outcome"]["rung"] == "verified"
        # The page received what the module says it filled.
        receipt = result["readback"]
        for expected in (
            "task=TASK-1", "result=DELIVERED", "distance=120", "location=Room 501",
            "operator=Dana", "date=2026-10-04", "notes=Arrived without incident",
            "notify=yes", "priority=high", "photo=evidence.png",
        ):
            assert expected in receipt, (expected, receipt)

    async def test_exact_label_beats_partial_and_form_beats_filter(self, page_ctx):
        result = await run({"fields": [
            {"label": "Location", "value": "Room 7"},
            {"label": "Result", "value": "FAILED"},
        ]}, page_ctx)
        assert result["ok"] is True
        page = page_ctx["browser"].real_page
        assert await page.input_value("#f-location") == "Room 7"
        assert await page.input_value("#f-location-notes") == ""
        assert await page.input_value("#f-result") == "FAILED"
        assert await page.eval_on_selector("[aria-label='Result filter']", "e => e.value") == "All"

    async def test_without_confirmation_it_waits_for_the_page_to_settle(self, page_ctx):
        result = await run({
            "fields": FULL_FIELDS,
            "submit": {},
        }, page_ctx)
        assert result["ok"] is True
        assert result["submitted"] is True
        assert "Saved REC-1" in (result["readback"] or "")


@pytest.mark.browser
class TestNothingPartial:
    async def test_a_missing_field_fills_nothing(self, page_ctx):
        result = await run({
            "fields": [
                {"label": "Task ID", "value": "TASK-1"},
                {"label": "No such field", "value": "x"},
            ],
            "submit": {"label": "Save record"},
            "resolve_wait_ms": 0,
        }, page_ctx)
        assert result["ok"] is False
        assert result["error_code"] == "FIELDS_NOT_FOUND"
        assert result["missing"] == [{"kind": "field", "name": "No such field"}]
        assert result["submitted"] is False
        page = page_ctx["browser"].real_page
        assert await page.input_value("#f-task-id") == ""

    async def test_a_missing_submit_button_fills_nothing(self, page_ctx):
        result = await run({
            "fields": [{"label": "Task ID", "value": "TASK-1"}],
            "submit": {"label": "Publish"},
            "resolve_wait_ms": 0,
        }, page_ctx)
        assert result["ok"] is False
        assert result["missing"] == [{"kind": "submit", "name": "Publish"}]
        assert await page_ctx["browser"].real_page.input_value("#f-task-id") == ""

    async def test_an_unknown_option_fails_and_does_not_submit(self, page_ctx):
        result = await run({
            "fields": [
                {"label": "Task ID", "value": "TASK-1"},
                {"label": "Result", "value": "Teleported"},
            ],
            "submit": {"label": "Save record"},
        }, page_ctx)
        assert result["ok"] is False
        assert result["error_code"] == "FILL_FAILED"
        assert result["submitted"] is False
        assert await page_ctx["browser"].real_page.is_visible("#record-form")

    async def test_an_empty_required_field_is_reported_not_submitted(self, page_ctx):
        result = await run({
            "fields": [{"label": "Notes", "value": "only notes"}],
            "submit": {"label": "Save record"},
        }, page_ctx)
        assert result["ok"] is False
        assert result["error_code"] == "FORM_INVALID"
        assert any(i["label"].startswith("Task ID") for i in result["invalid"])
        assert result["submitted"] is False

    async def test_confirmation_that_never_appears_is_a_failure(self, page_ctx):
        result = await run({
            "fields": FULL_FIELDS,
            "submit": {"label": "Save record"},
            "confirm": {"text": "This text never appears", "timeout_ms": 1500},
        }, page_ctx)
        assert result["ok"] is False
        assert result["error_code"] == "CONFIRMATION_NOT_SEEN"
        assert result["submitted"] is True


@pytest.mark.browser
class TestSecretsAndTiming:
    async def test_a_password_field_value_is_never_returned(self, page_ctx):
        result = await run({"fields": [
            {"label": "Access code", "value": "s3cret-not-real"},
        ]}, page_ctx)
        assert result["ok"] is True
        assert "s3cret-not-real" not in repr(result)
        assert result["fields"][0]["value"] == "***"
        assert result["fields"][0]["matches"] is True
        assert result[SENSITIVE_PARAMS_KEY] == ["fields"]
        assert await page_ctx["browser"].real_page.input_value("#f-code") == "s3cret-not-real"

    async def test_a_field_that_renders_late_is_waited_for(self, page_ctx):
        page = page_ctx["browser"].real_page
        await page.evaluate("window.addLateField()")
        result = await run({"fields": [{"label": "Late field", "value": "here"}]}, page_ctx)
        assert result["ok"] is True
        assert await page.input_value("#f-late") == "here"

    async def test_selector_targets_work_alongside_labels(self, page_ctx):
        result = await run({"fields": [
            {"selector": "#f-task-id", "value": "BY-SELECTOR"},
            {"selector": "#f-notify", "value": "yes"},
        ]}, page_ctx)
        assert result["ok"] is True
        page = page_ctx["browser"].real_page
        assert await page.input_value("#f-task-id") == "BY-SELECTOR"
        assert await page.is_checked("#f-notify")
