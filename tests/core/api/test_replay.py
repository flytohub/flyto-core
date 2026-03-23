"""
Tests for the replay route: POST /v1/workflow/{execution_id}/replay/{step_id}

Covers:
- Auth enforcement (missing token, invalid token)
- Validation failures (nonexistent execution)
- Dry-run mode
- Full replay execution with mocked ReplayManager
- Error propagation from replay_from_step
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from starlette.testclient import TestClient

from core.api.server import create_app
from core.engine.replay.models import ReplayResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_header():
    """Return Authorization header dict with the active token."""
    from core.api import security as sec
    token = sec._active_token
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPLAY_URL = "/v1/workflow/{execution_id}/replay/{step_id}"


def _url(execution_id: str = "exec_123", step_id: str = "step_1") -> str:
    return REPLAY_URL.format(execution_id=execution_id, step_id=step_id)


# ---------------------------------------------------------------------------
# TestReplayAuth
# ---------------------------------------------------------------------------

class TestReplayAuth:
    """Verify that the replay endpoint enforces bearer-token auth."""

    def test_replay_requires_auth(self, client):
        resp = client.post(_url(), json={})
        assert resp.status_code == 401

    def test_replay_rejects_invalid_token(self, client):
        resp = client.post(
            _url(),
            json={},
            headers={"Authorization": "Bearer wrong_token"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestReplayValidation
# ---------------------------------------------------------------------------

class TestReplayValidation:
    """Validation failures should return ok=False with an error message."""

    def test_nonexistent_execution_returns_error(self, client, auth_header):
        """No evidence directory exists for exec_nonexistent, so validate_replay fails."""
        resp = client.post(
            _url(execution_id="exec_nonexistent"),
            json={},
            headers=auth_header,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "exec_nonexistent" in body.get("error", "")
        assert body["original_execution_id"] == "exec_nonexistent"
        assert body["start_step"] == "step_1"

    def test_validation_issues_forwarded(self, client, auth_header):
        """When validate_replay returns issues, they appear in the error field."""
        mock_validation = {
            "valid": False,
            "issues": ["Step s99 not found in execution"],
            "warnings": [],
        }
        manager = client.app.state.server.replay_manager

        with patch.object(
            manager, "validate_replay", new_callable=AsyncMock, return_value=mock_validation
        ):
            resp = client.post(
                _url(execution_id="exec_abc", step_id="s99"),
                json={},
                headers=auth_header,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "s99" in body["error"]


# ---------------------------------------------------------------------------
# TestReplayDryRun
# ---------------------------------------------------------------------------

class TestReplayDryRun:
    """dry_run=True should validate and return immediately without executing."""

    def test_dry_run_valid(self, client, auth_header):
        mock_validation = {"valid": True, "issues": [], "warnings": []}
        manager = client.app.state.server.replay_manager

        with patch.object(
            manager, "validate_replay", new_callable=AsyncMock, return_value=mock_validation
        ):
            resp = client.post(
                _url(execution_id="exec_test", step_id="step_1"),
                json={"dry_run": True},
                headers=auth_header,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["execution_id"] == "dry_run"
        assert body["original_execution_id"] == "exec_test"
        assert body["start_step"] == "step_1"

    def test_dry_run_does_not_call_replay_from_step(self, client, auth_header):
        """Ensure replay_from_step is never called when dry_run=True."""
        mock_validation = {"valid": True, "issues": [], "warnings": []}
        manager = client.app.state.server.replay_manager

        with patch.object(
            manager, "validate_replay", new_callable=AsyncMock, return_value=mock_validation
        ) as mock_validate, patch.object(
            manager, "replay_from_step", new_callable=AsyncMock
        ) as mock_replay:
            resp = client.post(
                _url(),
                json={"dry_run": True},
                headers=auth_header,
            )

        assert resp.status_code == 200
        mock_validate.assert_awaited_once()
        mock_replay.assert_not_awaited()

    def test_dry_run_invalid_returns_error(self, client, auth_header):
        """dry_run still fails if validation fails."""
        mock_validation = {
            "valid": False,
            "issues": ["Execution not found"],
            "warnings": [],
        }
        manager = client.app.state.server.replay_manager

        with patch.object(
            manager, "validate_replay", new_callable=AsyncMock, return_value=mock_validation
        ):
            resp = client.post(
                _url(),
                json={"dry_run": True},
                headers=auth_header,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False


# ---------------------------------------------------------------------------
# TestReplayExecution
# ---------------------------------------------------------------------------

class TestReplayExecution:
    """Full replay execution with mocked manager."""

    def test_replay_success(self, client, auth_header):
        mock_validation = {"valid": True, "issues": [], "warnings": []}
        mock_result = ReplayResult(
            ok=True,
            execution_id="replay_abc123",
            original_execution_id="exec_test",
            start_step="step_2",
            steps_executed=3,
            duration_ms=150,
        )
        manager = client.app.state.server.replay_manager

        with patch.object(
            manager, "validate_replay", new_callable=AsyncMock, return_value=mock_validation
        ), patch.object(
            manager, "replay_from_step", new_callable=AsyncMock, return_value=mock_result
        ):
            resp = client.post(
                _url(execution_id="exec_test", step_id="step_2"),
                json={"modified_context": {"user_id": "new_user"}},
                headers=auth_header,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["execution_id"] == "replay_abc123"
        assert body["original_execution_id"] == "exec_test"
        assert body["start_step"] == "step_2"
        assert body["steps_executed"] == 3
        assert body["duration_ms"] == 150
        assert body["error"] is None

    def test_replay_passes_config_to_manager(self, client, auth_header):
        """Verify that modified_context from the request body reaches replay_from_step."""
        mock_validation = {"valid": True, "issues": [], "warnings": []}
        mock_result = ReplayResult(
            ok=True,
            execution_id="replay_xyz",
            original_execution_id="exec_test",
            start_step="step_1",
            steps_executed=1,
            duration_ms=10,
        )
        manager = client.app.state.server.replay_manager

        with patch.object(
            manager, "validate_replay", new_callable=AsyncMock, return_value=mock_validation
        ), patch.object(
            manager, "replay_from_step", new_callable=AsyncMock, return_value=mock_result
        ) as mock_replay:
            resp = client.post(
                _url(execution_id="exec_test", step_id="step_1"),
                json={"modified_context": {"x": 42}},
                headers=auth_header,
            )

        assert resp.status_code == 200
        # Check replay_from_step was called with the right args
        mock_replay.assert_awaited_once()
        call_kwargs = mock_replay.call_args.kwargs
        assert call_kwargs["execution_id"] == "exec_test"
        assert call_kwargs["step_id"] == "step_1"
        assert call_kwargs["config"].modified_context == {"x": 42}
        assert call_kwargs["config"].start_step_id == "step_1"
        assert call_kwargs["config"].dry_run is False

    def test_replay_failure_returns_error(self, client, auth_header):
        """When replay_from_step returns ok=False, the response reflects it."""
        mock_validation = {"valid": True, "issues": [], "warnings": []}
        mock_result = ReplayResult(
            ok=False,
            execution_id="replay_fail",
            original_execution_id="exec_test",
            start_step="step_3",
            steps_executed=1,
            error="Module browser.goto failed: timeout",
            duration_ms=5000,
        )
        manager = client.app.state.server.replay_manager

        with patch.object(
            manager, "validate_replay", new_callable=AsyncMock, return_value=mock_validation
        ), patch.object(
            manager, "replay_from_step", new_callable=AsyncMock, return_value=mock_result
        ):
            resp = client.post(
                _url(execution_id="exec_test", step_id="step_3"),
                json={},
                headers=auth_header,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"] == "Module browser.goto failed: timeout"
        assert body["steps_executed"] == 1
        assert body["duration_ms"] == 5000

    def test_replay_no_modified_context(self, client, auth_header):
        """Request body without modified_context should default to empty dict in config."""
        mock_validation = {"valid": True, "issues": [], "warnings": []}
        mock_result = ReplayResult(
            ok=True,
            execution_id="replay_no_ctx",
            original_execution_id="exec_test",
            start_step="step_1",
            steps_executed=2,
            duration_ms=50,
        )
        manager = client.app.state.server.replay_manager

        with patch.object(
            manager, "validate_replay", new_callable=AsyncMock, return_value=mock_validation
        ), patch.object(
            manager, "replay_from_step", new_callable=AsyncMock, return_value=mock_result
        ) as mock_replay:
            resp = client.post(
                _url(),
                json={},
                headers=auth_header,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        call_kwargs = mock_replay.call_args.kwargs
        assert call_kwargs["config"].modified_context == {}


# ---------------------------------------------------------------------------
# TestReplayResponseModel
# ---------------------------------------------------------------------------

class TestReplayResponseModel:
    """Verify response shape matches ReplayResponse model."""

    def test_response_contains_all_fields(self, client, auth_header):
        """Even on failure, all ReplayResponse fields should be present."""
        resp = client.post(
            _url(execution_id="missing"),
            json={},
            headers=auth_header,
        )
        assert resp.status_code == 200
        body = resp.json()
        # All fields from ReplayResponse must be present
        assert "ok" in body
        assert "execution_id" in body
        assert "original_execution_id" in body
        assert "start_step" in body
        assert "steps_executed" in body
        assert "duration_ms" in body
        # error is Optional, but should be in the JSON (even if null)
        assert "error" in body
