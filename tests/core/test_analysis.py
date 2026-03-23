"""
Tests for core.analysis.HTMLAnalyzer
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.analysis import HTMLAnalyzer


class TestHTMLAnalyzerInit:
    """Test HTMLAnalyzer initialization."""

    def test_default_args(self):
        analyzer = HTMLAnalyzer()
        assert analyzer.html == ""
        assert analyzer.url is None

    def test_with_html(self):
        analyzer = HTMLAnalyzer(html="<p>hello</p>")
        assert analyzer.html == "<p>hello</p>"
        assert analyzer.url is None

    def test_with_html_and_url(self):
        analyzer = HTMLAnalyzer(html="<p>hello</p>", url="https://example.com")
        assert analyzer.html == "<p>hello</p>"
        assert analyzer.url == "https://example.com"


class TestHTMLAnalyzerMethods:
    """Test HTMLAnalyzer stub methods."""

    @pytest.fixture
    def analyzer(self):
        return HTMLAnalyzer(html="<p>test</p>", url="https://example.com")

    def test_analyze_readability(self, analyzer):
        result = analyzer.analyze_readability()
        assert isinstance(result, dict)
        assert result["status"] == "stub"

    def test_extract_forms(self, analyzer):
        result = analyzer.extract_forms()
        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_tables(self, analyzer):
        result = analyzer.extract_tables()
        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_metadata(self, analyzer):
        result = analyzer.extract_metadata()
        assert isinstance(result, dict)
        assert result["status"] == "stub"

    def test_find_patterns(self, analyzer):
        result = analyzer.find_patterns("test")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_analyze_structure(self, analyzer):
        result = analyzer.analyze_structure()
        assert isinstance(result, dict)
        assert result["status"] == "stub"
