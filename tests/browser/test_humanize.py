"""Tests for HumanBehavior profiles."""
import pytest
from core.browser.humanize import HumanBehavior, PROFILES


class TestHumanBehavior:
    def test_all_profiles_exist(self):
        for profile in ['fast', 'normal', 'careful', 'human_like']:
            hb = HumanBehavior(profile)
            assert hb.profile == profile

    def test_invalid_profile(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            HumanBehavior('turbo')

    def test_fast_is_fast(self):
        hb = HumanBehavior('fast')
        assert hb.is_fast is True
        assert hb.get_type_delay() == 0
        assert hb.typo_rate == 0.0

    def test_normal_has_delays(self):
        hb = HumanBehavior('normal')
        assert hb.is_fast is False
        # Type delay should be in range
        delays = [hb.get_type_delay() for _ in range(20)]
        assert any(d > 0 for d in delays)

    def test_human_like_has_typo_rate(self):
        hb = HumanBehavior('human_like')
        assert hb.typo_rate > 0

    def test_careful_has_mouse_move(self):
        hb = HumanBehavior('careful')
        config = PROFILES['careful']
        assert config['mouse_move'] is True
        assert config['random_scroll'] is True

    @pytest.mark.asyncio
    async def test_before_click_fast_noop(self):
        hb = HumanBehavior('fast')
        # Should return immediately without error
        await hb.before_click(None, None)

    @pytest.mark.asyncio
    async def test_after_navigation_fast_noop(self):
        hb = HumanBehavior('fast')
        await hb.after_navigation(None)

    @pytest.mark.asyncio
    async def test_before_scroll_fast_noop(self):
        hb = HumanBehavior('fast')
        await hb.before_scroll(None)
