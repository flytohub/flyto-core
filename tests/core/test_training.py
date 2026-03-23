"""
Tests for core.training.DailyPracticeEngine
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.training import DailyPracticeEngine


class TestDailyPracticeEngineInit:
    """Test DailyPracticeEngine initialization."""

    def test_default_config(self):
        engine = DailyPracticeEngine()
        assert engine.config == {}

    def test_custom_config(self):
        config = {"max_items": 5, "timeout": 30}
        engine = DailyPracticeEngine(config=config)
        assert engine.config == config
        assert engine.config["max_items"] == 5


class TestDailyPracticeEngineMethods:
    """Test DailyPracticeEngine stub methods."""

    @pytest.fixture
    def engine(self):
        return DailyPracticeEngine()

    def test_analyze(self, engine):
        result = engine.analyze("https://example.com")
        assert isinstance(result, dict)
        assert result["status"] == "stub"
        assert result["url"] == "https://example.com"

    def test_execute(self, engine):
        result = engine.execute("practice-1")
        assert isinstance(result, dict)
        assert result["status"] == "stub"
        assert result["practice_id"] == "practice-1"

    def test_infer_schema(self, engine):
        result = engine.infer_schema({"a": 1})
        assert isinstance(result, dict)
        assert result["status"] == "stub"

    def test_get_stats(self, engine):
        result = engine.get_stats()
        assert isinstance(result, dict)
        assert result["total_sessions"] == 0
        assert result["success_rate"] == 0.0
