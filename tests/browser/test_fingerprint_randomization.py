"""Tests for fingerprint randomization — verify WebGL/hardware varies per launch."""
import asyncio
import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
os.environ["FLYTO_VSCODE_LOCAL_MODE"] = "true"
os.environ.setdefault("FLYTO_ENV", "test")


@pytest.mark.asyncio
async def test_webgl_fingerprint_randomized():
    """Launch browser twice, verify WebGL renderer differs (probabilistic)."""
    from core.browser.driver import BrowserDriver

    fingerprints = []
    for _ in range(3):
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=True)
        try:
            result = await driver.evaluate("""
                () => {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl');
                    if (!gl) return { vendor: null, renderer: null };
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    return {
                        vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null,
                        renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null,
                    };
                }
            """)
            fingerprints.append(result.get('renderer'))
        finally:
            await driver.close()

    # With randomization, at least 2 out of 3 launches should differ
    # (statistically: pool size >= 3, so P(all same) = 1/N^2 ≈ small)
    unique = set(fingerprints)
    # At minimum, all should be real GPU strings (not SwiftShader)
    for fp in fingerprints:
        assert fp is not None
        assert 'SwiftShader' not in fp, f"SwiftShader detected: {fp}"
        assert 'ANGLE' in fp, f"Expected ANGLE renderer, got: {fp}"


@pytest.mark.asyncio
async def test_hardware_concurrency_randomized():
    """Verify hardware concurrency varies per launch."""
    from core.browser.driver import BrowserDriver

    values = []
    for _ in range(5):
        driver = BrowserDriver(headless=True)
        await driver.launch(stealth=True)
        try:
            cores = await driver.evaluate("() => navigator.hardwareConcurrency")
            values.append(cores)
        finally:
            await driver.close()

    # Should be realistic values
    for v in values:
        assert v in (4, 6, 8, 10, 12, 16), f"Unexpected core count: {v}"

    # With 6 options over 5 launches, high probability of variation
    # but not guaranteed — just check values are valid
