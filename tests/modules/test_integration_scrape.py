"""
Integration tests — run actual modules through the execution framework.

Tests the REAL module classes (not raw JS), with proper context passing:
  BrowserLaunchModule → BrowserDetectListModule → BrowserReadabilityModule

This validates:
  - Module instantiation with params
  - validate_params()
  - execute() with shared browser context
  - Output format matches output_schema
  - Context propagation between modules
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Import all modules to trigger registration
from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry


def get_module(module_id):
    """Get a registered module class by ID."""
    cls = ModuleRegistry.get(module_id)
    assert cls is not None, f"Module {module_id} not registered"
    return cls


class TestModuleExecution:
    """Test modules through their actual execute() methods."""

    @pytest.mark.asyncio
    async def test_launch_execute(self):
        """browser.launch should create a browser in context."""
        LaunchModule = get_module("browser.launch")

        context = {}
        module = LaunchModule({"headless": True, "stealth": True}, context)
        module.validate_params()
        result = await module.execute()

        assert result["status"] == "success"
        assert result["headless"] is True
        assert "browser" in context, "Browser driver should be stored in context"

        # Cleanup
        driver = context["browser"]
        await driver.close()

    @pytest.mark.asyncio
    async def test_detect_list_execute(self):
        """browser.detect_list should return items from a real page."""
        LaunchModule = get_module("browser.launch")
        DetectListModule = get_module("browser.detect_list")

        # Step 1: Launch browser
        context = {}
        launch = LaunchModule({"headless": True, "stealth": True}, context)
        launch.validate_params()
        await launch.execute()

        # Step 2: Navigate
        driver = context["browser"]
        await driver.goto("https://dev.to")

        # Step 3: Detect list through module execution
        detect = DetectListModule({"min_items": 3}, context)
        detect.validate_params()
        result = await detect.execute()

        print(f"\n[Integration] detect_list: status={result['status']}, count={result['count']}")
        if result["count"] > 0:
            print(f"  selector: {result['selector']}")
            for item in result["items"][:3]:
                print(f"  - {item.get('title', '?')[:50]}")

        assert result["status"] == "success"
        assert result["count"] >= 3, f"Dev.to should have posts, got {result['count']}"
        assert result["items"][0].get("title"), "Items should have titles"
        assert result["content_found"] is True

        await driver.close()

    @pytest.mark.asyncio
    async def test_readability_execute(self):
        """browser.readability should extract article content from a real page."""
        LaunchModule = get_module("browser.launch")
        ReadabilityModule = get_module("browser.readability")

        # Step 1: Launch browser
        context = {}
        launch = LaunchModule({"headless": True, "stealth": True}, context)
        launch.validate_params()
        await launch.execute()

        # Step 2: Navigate to Wikipedia
        driver = context["browser"]
        await driver.goto("https://en.wikipedia.org/wiki/Python_(programming_language)")

        # Step 3: Extract article through module execution
        readability = ReadabilityModule({}, context)
        readability.validate_params()
        result = await readability.execute()

        print(f"\n[Integration] readability: status={result['status']}, title='{result['title'][:50]}'")
        print(f"  words={result['word_count']}, images={len(result['images'])}")

        assert result["status"] == "success"
        assert result["content_found"] is True
        assert "Python" in result["title"]
        assert result["word_count"] > 500
        assert result["content"], "Content should not be empty"

        await driver.close()

    @pytest.mark.asyncio
    async def test_challenge_execute_no_challenge(self):
        """browser.challenge should pass through when no challenge present."""
        LaunchModule = get_module("browser.launch")
        ChallengeModule = get_module("browser.challenge")

        # Step 1: Launch browser
        context = {}
        launch = LaunchModule({"headless": True, "stealth": True}, context)
        launch.validate_params()
        await launch.execute()

        # Step 2: Navigate to a non-challenged site
        driver = context["browser"]
        await driver.goto("https://news.ycombinator.com")

        # Step 3: Challenge check should pass through
        challenge = ChallengeModule({"auto_wait_seconds": 0}, context)
        challenge.validate_params()
        result = await challenge.execute()

        print(f"\n[Integration] challenge: status={result['status']}, type={result['challenge_type']}")

        assert result["status"] == "no_challenge"
        assert result["challenge_type"] == "none"
        assert result["required_human"] is False

        await driver.close()


class TestFullPipelineIntegration:
    """Test the complete scrape pipeline through actual module execution."""

    @pytest.mark.asyncio
    async def test_devto_pipeline(self):
        """Dev.to: launch → challenge → detect_list → goto → readability."""
        LaunchModule = get_module("browser.launch")
        ChallengeModule = get_module("browser.challenge")
        DetectListModule = get_module("browser.detect_list")
        ReadabilityModule = get_module("browser.readability")

        context = {}

        # Step 1: Launch
        launch = LaunchModule({"headless": True, "stealth": True}, context)
        launch.validate_params()
        launch_result = await launch.execute()
        assert launch_result["status"] == "success"
        driver = context["browser"]

        # Step 2: Navigate
        await driver.goto("https://dev.to")

        # Step 3: Challenge check
        challenge = ChallengeModule({"auto_wait_seconds": 5}, context)
        challenge.validate_params()
        challenge_result = await challenge.execute()
        print(f"\n[Pipeline] Challenge: {challenge_result['status']}")
        assert challenge_result["status"] == "no_challenge"

        # Step 4: Detect list
        detect = DetectListModule({}, context)
        detect.validate_params()
        detect_result = await detect.execute()
        print(f"[Pipeline] Detect: {detect_result['count']} items")
        assert detect_result["count"] >= 3

        # Step 5: Navigate to first article + extract
        first_item = detect_result["items"][0]
        article_url = first_item.get("url", "")
        if article_url.startswith("/"):
            article_url = "https://dev.to" + article_url
        assert article_url, "First item should have a URL"

        await driver.goto(article_url)

        # Step 6: Readability
        readability = ReadabilityModule({}, context)
        readability.validate_params()
        article_result = await readability.execute()

        print(f"[Pipeline] Article: '{article_result['title'][:50]}', {article_result['word_count']} words, author='{article_result['author']}'")

        assert article_result["status"] == "success"
        assert article_result["title"], "Should have article title"
        assert article_result["content_found"] is True
        assert article_result["word_count"] > 30

        # Verify output schema fields exist
        for key in ["title", "author", "date", "content", "html", "excerpt",
                     "site_name", "image", "images", "videos", "links",
                     "word_count", "language", "url", "content_found"]:
            assert key in article_result, f"Missing output field: {key}"

        await driver.close()

    @pytest.mark.asyncio
    async def test_hn_pipeline(self):
        """HN: launch → detect_list → loop 2 articles → readability each."""
        LaunchModule = get_module("browser.launch")
        DetectListModule = get_module("browser.detect_list")
        ReadabilityModule = get_module("browser.readability")

        context = {}

        # Launch
        launch = LaunchModule({"headless": True}, context)
        launch.validate_params()
        await launch.execute()
        driver = context["browser"]

        # Navigate + detect
        await driver.goto("https://news.ycombinator.com")
        detect = DetectListModule({}, context)
        detect.validate_params()
        detect_result = await detect.execute()
        assert detect_result["count"] >= 20

        # Loop: pick first 2 external articles
        articles = []
        for item in detect_result["items"][:5]:
            url = item.get("url", "")
            from urllib.parse import urlparse
            if not url.startswith("http") or urlparse(url).hostname and urlparse(url).hostname.endswith("ycombinator.com"):
                continue
            if len(articles) >= 2:
                break

            try:
                await driver.goto(url, wait_until="domcontentloaded", timeout_ms=15000)

                readability = ReadabilityModule({}, context)
                readability.validate_params()
                result = await readability.execute()

                articles.append({
                    "hn_title": item.get("title", ""),
                    "extracted_title": result["title"],
                    "words": result["word_count"],
                    "found": result["content_found"],
                })
                print(f"  ✓ {item['title'][:40]} → {result['word_count']} words")
            except Exception as e:
                print(f"  ✗ {item.get('title', '?')[:40]} → {type(e).__name__}")

        print(f"\n[HN Pipeline] {len(articles)} articles extracted")
        assert len(articles) >= 1, "Should extract at least 1 article"

        await driver.close()
