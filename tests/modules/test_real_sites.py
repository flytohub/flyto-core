"""
Real-world site tests for browser.detect_list + browser.readability

Tests the full pipeline: navigate → detect list → pick item → navigate → extract article
Against LIVE websites. These tests require internet access.

Run: pytest tests/modules/test_real_sites.py -v --timeout=60
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


@pytest.fixture
async def page():
    """Fresh browser + page per test (avoids event loop issues)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed")

    pw = await async_playwright().start()
    br = await pw.chromium.launch(headless=True)
    p = await br.new_page()
    yield p
    await br.close()
    await pw.stop()


def get_detect_js():
    from core.modules.atomic.browser.detect_list import _DETECT_LIST_JS
    return _DETECT_LIST_JS


def get_readability_js():
    from core.modules.atomic.browser.readability import _EXTRACT_JS
    return _EXTRACT_JS


# =============================================================================
# Hacker News
# =============================================================================

class TestHackerNews:
    URL = "https://news.ycombinator.com"

    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """HN front page should detect 30 story items."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[HN] detect_list: {result['count']} items, selector='{result['selector']}', consistency={result.get('consistency')}")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        assert result["content_found"], "Should detect story list"
        assert result["count"] >= 20, f"HN has 30 stories per page, got {result['count']}"
        assert result["items"][0].get("title"), "First item should have a title"
        assert result["items"][0].get("url"), "First item should have a URL"

    @pytest.mark.asyncio
    async def test_readability_on_hn_item(self, page):
        """Navigate to an HN discussion page and extract content."""
        # Go to HN and get first item's HN comments page (not external link)
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)

        # Get the comments link (item?id=xxx) for the first story
        hn_link = await page.evaluate("""
            () => {
                const subtext = document.querySelector('.subtext a[href*="item?id="]');
                return subtext ? subtext.href : null;
            }
        """)

        if not hn_link:
            pytest.skip("Could not find HN discussion link")

        await page.goto(hn_link, wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_readability_js(), {})

        print(f"\n[HN Item] title='{result['title'][:60]}', content_found={result['content_found']}, words={result['word_count']}")

        assert result["title"], "Should extract article title"


# =============================================================================
# GitHub Trending
# =============================================================================

class TestGitHubTrending:
    URL = "https://github.com/trending"

    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """GitHub trending should detect repository cards."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[GitHub] detect_list: {result['count']} items, selector='{result['selector']}'")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        assert result["content_found"], "Should detect repo list"
        assert result["count"] >= 5, f"GitHub trending has 25 repos, got {result['count']}"

    @pytest.mark.asyncio
    async def test_readability_on_repo_readme(self, page):
        """Navigate to a repo page and extract the README."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_detect_js(), {})

        if not result["items"] or not result["items"][0].get("url"):
            pytest.skip("No trending repos found")

        repo_url = result["items"][0]["url"]
        if not repo_url.startswith("http"):
            repo_url = "https://github.com" + repo_url

        await page.goto(repo_url, wait_until="domcontentloaded", timeout=30000)
        article = await page.evaluate(get_readability_js(), {})

        print(f"\n[GitHub Repo] title='{article['title'][:60]}', words={article['word_count']}, content_found={article['content_found']}")

        assert article["title"], "Should extract repo name or README title"


# =============================================================================
# Wikipedia
# =============================================================================

class TestWikipedia:
    URL = "https://en.wikipedia.org/wiki/Main_Page"

    @pytest.mark.asyncio
    async def test_readability_on_article(self, page):
        """Wikipedia article should extract cleanly."""
        await page.goto("https://en.wikipedia.org/wiki/Python_(programming_language)",
                        wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_readability_js(), {})

        print(f"\n[Wikipedia] title='{result['title'][:60]}', words={result['word_count']}, images={len(result['images'])}")
        print(f"  content preview: {result['content'][:150]}...")

        assert result["content_found"], "Wikipedia article should have content"
        assert result["word_count"] > 500, f"Python article should be long, got {result['word_count']} words"
        assert "Python" in result["title"], f"Title should mention Python, got '{result['title']}'"
        assert "programming" in result["content"].lower(), "Content should mention programming"


# =============================================================================
# BBC News
# =============================================================================

class TestBBCNews:
    URL = "https://www.bbc.com/news"

    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """BBC News should detect news article cards."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[BBC] detect_list: {result['count']} items, selector='{result['selector']}'")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        assert result["content_found"], "Should detect news list"
        assert result["count"] >= 3, f"BBC should have news stories, got {result['count']}"


# =============================================================================
# Dev.to
# =============================================================================

class TestDevTo:
    URL = "https://dev.to"

    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """Dev.to should detect blog post cards."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[Dev.to] detect_list: {result['count']} items, selector='{result['selector']}'")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        assert result["content_found"], "Should detect post list"
        assert result["count"] >= 5, f"Dev.to should have many posts, got {result['count']}"

    @pytest.mark.asyncio
    async def test_readability_on_post(self, page):
        """Navigate to a dev.to post and extract content."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        list_result = await page.evaluate(get_detect_js(), {})

        if not list_result["items"]:
            pytest.skip("No dev.to posts found")

        # Find first item with a valid URL
        post_url = None
        for item in list_result["items"][:5]:
            url = item.get("url", "")
            if url and "//" in url and "dev.to" in url:
                post_url = url
                break
            elif url and url.startswith("/"):
                post_url = "https://dev.to" + url
                break

        if not post_url:
            pytest.skip("No valid dev.to post URL found")

        await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        article = await page.evaluate(get_readability_js(), {})

        print(f"\n[Dev.to Post] title='{article['title'][:60]}', author='{article['author']}', words={article['word_count']}")

        assert article["title"], "Should extract post title"
        assert article["content_found"], "Should extract post content"
        assert article["word_count"] > 50, f"Post should have content, got {article['word_count']} words"


# =============================================================================
# Full Pipeline Test: detect_list → loop simulation → readability
# =============================================================================

# =============================================================================
# Reddit
# =============================================================================

class TestReddit:
    URL = "https://old.reddit.com/r/programming/"

    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """Reddit should detect post listings (may be blocked by Cloudflare)."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[Reddit] detect_list: {result['count']} items, selector='{result['selector']}'")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        if result["count"] == 0:
            pytest.skip("Reddit blocked by Cloudflare (bot detection)")
        assert result["count"] >= 5


# =============================================================================
# Product Hunt
# =============================================================================

class TestProductHunt:
    URL = "https://www.producthunt.com"

    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """Product Hunt should detect product listings (SPA, needs wait)."""
        try:
            await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector('[data-test*="post"], .styles_item', timeout=10000)
        except Exception:
            pytest.skip("Product Hunt SPA did not render in time")

        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[PH] detect_list: {result['count']} items, selector='{result['selector']}'")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        if result["count"] == 0:
            pytest.skip("Product Hunt SPA content not detected")
        assert result["count"] >= 3


# =============================================================================
# Medium
# =============================================================================

class TestMedium:
    @pytest.mark.asyncio
    async def test_readability_on_article(self, page):
        """Medium article should extract cleanly (no paywall on this one)."""
        await page.goto("https://medium.com/@kentbeck_7670/test-commit-revert-870bbd756864",
                        wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_readability_js(), {})

        print(f"\n[Medium] title='{result['title'][:60]}', author='{result['author']}', words={result['word_count']}")

        if "just a moment" in result["title"].lower() or result["word_count"] == 0:
            pytest.skip("Medium blocked by Cloudflare challenge")
        assert result["title"], "Should extract article title"
        assert result["content_found"], "Should extract article content"


# =============================================================================
# Stack Overflow
# =============================================================================

class TestStackOverflow:
    URL = "https://stackoverflow.com/questions?tab=newest"

    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """SO should detect question listings (may be blocked by Cloudflare)."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[SO] detect_list: {result['count']} items, selector='{result['selector']}'")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        if result["count"] == 0:
            pytest.skip("Stack Overflow blocked by Cloudflare (bot detection)")
        assert result["count"] >= 5

    @pytest.mark.asyncio
    async def test_readability_on_question(self, page):
        """SO question page should extract question + answers."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        list_result = await page.evaluate(get_detect_js(), {})

        question_url = None
        for item in list_result["items"][:10]:
            url = item.get("url", "")
            if "stackoverflow.com/questions/" in url:
                question_url = url
                break

        if not question_url:
            pytest.skip("No SO question URL found")

        await page.goto(question_url, wait_until="domcontentloaded", timeout=30000)
        article = await page.evaluate(get_readability_js(), {})

        print(f"\n[SO Q] title='{article['title'][:60]}', words={article['word_count']}")

        assert article["title"], "Should extract question title"
        assert article["word_count"] > 20, f"Question should have content, got {article['word_count']}"


# =============================================================================
# Amazon (e-commerce)
# =============================================================================

class TestAmazon:
    URL = "https://www.amazon.com/gp/bestsellers/"

    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """Amazon bestsellers should detect product listings."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[Amazon] detect_list: {result['count']} items, selector='{result['selector']}'")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        # Amazon may block or show captcha — mark as soft assertion
        if result["count"] == 0:
            pytest.skip("Amazon likely blocked (captcha/bot detection)")
        assert result["count"] >= 3


# =============================================================================
# ArXiv (academic papers)
# =============================================================================

class TestArXiv:
    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """ArXiv new submissions should detect paper listings."""
        await page.goto("https://arxiv.org/list/cs.AI/recent", wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[ArXiv] detect_list: {result['count']} items, selector='{result['selector']}'")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        assert result["content_found"], "Should detect paper list"
        assert result["count"] >= 5

    @pytest.mark.asyncio
    async def test_readability_on_abstract(self, page):
        """ArXiv abstract page should extract paper details."""
        await page.goto("https://arxiv.org/abs/2301.07041", wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_readability_js(), {})

        print(f"\n[ArXiv Paper] title='{result['title'][:60]}', author='{result['author'][:40]}', words={result['word_count']}")

        assert result["title"], "Should extract paper title"
        assert result["content_found"], "Should extract abstract"


# =============================================================================
# TechCrunch (news)
# =============================================================================

class TestTechCrunch:
    URL = "https://techcrunch.com"

    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """TechCrunch should detect article listings."""
        await page.goto(self.URL, wait_until="domcontentloaded", timeout=30000)
        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[TC] detect_list: {result['count']} items, selector='{result['selector']}'")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        assert result["content_found"], "Should detect article list"
        assert result["count"] >= 3


# =============================================================================
# YouTube (video listings)
# =============================================================================

class TestYouTube:
    URL = "https://www.youtube.com/results?search_query=python+tutorial"

    @pytest.mark.asyncio
    async def test_detect_list(self, page):
        """YouTube search results should detect video listings."""
        await page.goto(self.URL, wait_until="networkidle", timeout=30000)
        # YouTube is SPA, wait for results
        try:
            await page.wait_for_selector('ytd-video-renderer, #contents ytd-item-section-renderer', timeout=10000)
        except Exception:
            pass
        result = await page.evaluate(get_detect_js(), {})

        print(f"\n[YT] detect_list: {result['count']} items, selector='{result['selector']}'")
        for item in result["items"][:3]:
            print(f"  - {item.get('title', '?')[:60]}  →  {item.get('url', '?')[:50]}")

        # YouTube is heavily JS, may not work without full render
        if result["count"] == 0:
            pytest.skip("YouTube SPA did not render (requires full JS execution)")
        assert result["count"] >= 3


# =============================================================================
# Full Pipeline Tests
# =============================================================================

class TestFullPipeline:
    """Simulate the complete workflow: list detection → article extraction."""

    @pytest.mark.asyncio
    async def test_hn_full_pipeline(self, page):
        """HN: detect list → pick top 3 → extract each article."""
        # Step 1: Go to HN
        await page.goto("https://news.ycombinator.com", wait_until="domcontentloaded", timeout=30000)

        # Step 2: Detect list
        list_result = await page.evaluate(get_detect_js(), {})
        assert list_result["content_found"], "Should detect HN story list"

        print(f"\n[Pipeline] Detected {list_result['count']} items on HN")

        # Step 3: Loop through first 3 items (simulate flow.loop)
        extracted = []
        for item in list_result["items"][:3]:
            url = item.get("url", "")
            if not url or url.startswith("item?id="):
                # Skip HN self-posts (no external URL)
                continue
            if not url.startswith("http"):
                continue

            try:
                # Step 3a: Navigate to article
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)

                # Step 3b: Extract article
                article = await page.evaluate(get_readability_js(), {})

                extracted.append({
                    "hn_title": item.get("title", ""),
                    "article_title": article.get("title", ""),
                    "author": article.get("author", ""),
                    "word_count": article.get("word_count", 0),
                    "content_found": article.get("content_found", False),
                    "content_preview": article.get("content", "")[:100],
                    "url": url,
                })

                print(f"  ✓ {item['title'][:50]} → {article['word_count']} words, content_found={article['content_found']}")

            except Exception as e:
                print(f"  ✗ {item.get('title', '?')[:50]} → {type(e).__name__}: {e}")
                continue

        print(f"\n[Pipeline] Extracted {len(extracted)} articles from top 3 HN stories")

        # At least 1 should succeed (some URLs may timeout or be PDFs)
        assert len(extracted) >= 1, "Should extract at least 1 article"
        success = [a for a in extracted if a["content_found"]]
        print(f"[Pipeline] {len(success)}/{len(extracted)} had content_found=True")

    @pytest.mark.asyncio
    async def test_devto_full_pipeline(self, page):
        """Dev.to: detect posts → pick top 3 → extract each article."""
        await page.goto("https://dev.to", wait_until="domcontentloaded", timeout=30000)
        list_result = await page.evaluate(get_detect_js(), {})
        assert list_result["content_found"], "Should detect dev.to post list"
        print(f"\n[DevTo Pipeline] Detected {list_result['count']} items")

        extracted = []
        for item in list_result["items"][:3]:
            url = item.get("url", "")
            if not url:
                continue
            if url.startswith("/"):
                url = "https://dev.to" + url
            if "dev.to" not in url:
                continue

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                article = await page.evaluate(get_readability_js(), {})
                extracted.append(article)
                print(f"  ✓ {article['title'][:50]} → {article['word_count']} words, author='{article['author']}'")
            except Exception as e:
                print(f"  ✗ {url[:50]} → {type(e).__name__}")

        assert len(extracted) >= 1, "Should extract at least 1 article"
        success = [a for a in extracted if a["content_found"] and a["word_count"] > 50]
        print(f"[DevTo Pipeline] {len(success)}/{len(extracted)} extracted with content")
        assert len(success) >= 1, "At least 1 article should have substantial content"
