"""Tests for CaptchaSolver — unit tests (no real API calls)."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.browser.captcha import CaptchaSolver, _EXTRACT_CAPTCHA_INFO_JS


class TestCaptchaSolverInit:
    def test_valid_providers(self):
        for provider in ('2captcha', 'capsolver', 'captchaai'):
            solver = CaptchaSolver(provider, 'test-key')
            assert solver.provider == provider

    def test_invalid_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            CaptchaSolver('invalid', 'key')

    def test_empty_api_key(self):
        with pytest.raises(ValueError, match="api_key is required"):
            CaptchaSolver('2captcha', '')

    def test_stats_initial(self):
        solver = CaptchaSolver('2captcha', 'key')
        assert solver.stats == {'solved': 0, 'failed': 0, 'total_time': 0.0}


class TestCaptchaDetection:
    @pytest.mark.asyncio
    async def test_detect_calls_evaluate(self):
        solver = CaptchaSolver('2captcha', 'key')
        page = AsyncMock()
        page.evaluate.return_value = {
            'type': 'recaptcha_v2',
            'sitekey': 'abc123',
            'url': 'https://example.com',
        }
        result = await solver.detect(page)
        assert result['type'] == 'recaptcha_v2'
        assert result['sitekey'] == 'abc123'
        page.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_detect_handles_error(self):
        solver = CaptchaSolver('2captcha', 'key')
        page = AsyncMock()
        page.evaluate.side_effect = Exception("page closed")
        result = await solver.detect(page)
        assert result['type'] is None


class TestCaptchaSolve:
    @pytest.mark.asyncio
    async def test_no_captcha_returns_immediately(self):
        solver = CaptchaSolver('2captcha', 'key')
        page = AsyncMock()
        page.url = 'https://example.com'

        result = await solver.solve(page, captcha_info={
            'type': None, 'sitekey': None, 'url': 'https://example.com'
        })
        assert result['status'] == 'no_captcha'

    @pytest.mark.asyncio
    async def test_missing_sitekey_returns_error(self):
        solver = CaptchaSolver('2captcha', 'key')
        page = AsyncMock()

        result = await solver.solve(page, captcha_info={
            'type': 'recaptcha_v2', 'sitekey': None, 'url': 'https://example.com'
        })
        assert result['status'] == 'error'
        assert 'sitekey' in result['error']

    @pytest.mark.asyncio
    async def test_submit_failure_increments_stats(self):
        solver = CaptchaSolver('2captcha', 'key')
        page = AsyncMock()

        with patch.object(solver, '_submit_task', return_value=None):
            result = await solver.solve(page, captcha_info={
                'type': 'recaptcha_v2', 'sitekey': 'abc', 'url': 'https://example.com'
            })
        assert result['status'] == 'error'
        assert solver.stats['failed'] == 1

    @pytest.mark.asyncio
    async def test_successful_solve(self):
        solver = CaptchaSolver('capsolver', 'key')
        page = AsyncMock()
        page.evaluate.return_value = {'injected': True, 'callback': 'test'}

        with patch.object(solver, '_submit_task', return_value='task-123'):
            with patch.object(solver, '_poll_result', return_value='token-xyz'):
                result = await solver.solve(page, captcha_info={
                    'type': 'hcaptcha', 'sitekey': 'abc', 'url': 'https://example.com'
                })
        assert result['status'] == 'solved'
        assert result['provider'] == 'capsolver'
        assert solver.stats['solved'] == 1

    @pytest.mark.asyncio
    async def test_poll_timeout_returns_error(self):
        solver = CaptchaSolver('2captcha', 'key')
        page = AsyncMock()

        with patch.object(solver, '_submit_task', return_value='task-123'):
            with patch.object(solver, '_poll_result', return_value=None):
                result = await solver.solve(page, captcha_info={
                    'type': 'turnstile', 'sitekey': 'abc', 'url': 'https://example.com'
                })
        assert result['status'] == 'error'
        assert 'timed out' in result['error']


class TestCaptchaAIProvider:
    """CaptchaAI is 2Captcha-API-compatible and reuses the in.php/res.php path."""

    @pytest.mark.asyncio
    async def test_submit_uses_captchaai_base_url(self):
        solver = CaptchaSolver('captchaai', 'key')
        with patch.object(solver, '_http_post', return_value={'status': 1, 'request': 'task-123'}) as post:
            task_id = await solver._submit_task('recaptcha_v2', 'sitekey-abc', 'https://example.com')
        assert task_id == 'task-123'
        url, params = post.call_args.args[0], post.call_args.args[1]
        assert url == 'https://ocr.captchaai.com/in.php'
        assert params['method'] == 'userrecaptcha'
        assert params['googlekey'] == 'sitekey-abc'

    @pytest.mark.asyncio
    async def test_poll_uses_captchaai_base_url(self):
        solver = CaptchaSolver('captchaai', 'key')
        with patch('asyncio.sleep', new=AsyncMock()):
            with patch.object(solver, '_http_post', return_value={'status': 1, 'request': 'token-xyz'}) as post:
                token = await solver._poll_result('task-123')
        assert token == 'token-xyz'
        assert post.call_args.args[0] == 'https://ocr.captchaai.com/res.php'
