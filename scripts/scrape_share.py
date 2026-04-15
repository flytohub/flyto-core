"""Render a ChatGPT share URL and dump the conversation as JSON + markdown."""
import json, sys, pathlib
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else (
    "https://chatgpt.com/share/69dee485-fc04-83a2-9ce3-08194a81f9cb"
)
OUT = pathlib.Path(__file__).parent.parent / "out"
OUT.mkdir(exist_ok=True)
share_id = URL.rstrip("/").split("/")[-1]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        locale="zh-TW",
        viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle", timeout=45000)
    try:
        page.wait_for_selector("[data-message-author-role]", timeout=15000)
    except Exception:
        pass

    # Scroll through the page to force lazy turns to render
    page.evaluate(
        """
        async () => {
          const main = document.querySelector('main') || document.body;
          const step = 800;
          let y = 0;
          while (y < main.scrollHeight) {
            window.scrollTo(0, y);
            await new Promise(r => setTimeout(r, 200));
            y += step;
          }
          window.scrollTo(0, 0);
        }
        """
    )
    page.wait_for_timeout(2000)

    data = page.evaluate(
        """
        () => {
          const out = [];
          // Prefer the conversation-turn container; fall back to role attrs.
          const turns = document.querySelectorAll("article[data-testid^='conversation-turn'], [data-testid^='conversation-turn']");
          if (turns.length) {
            turns.forEach((el, i) => {
              const roleEl = el.querySelector('[data-message-author-role]');
              const role = roleEl ? roleEl.getAttribute('data-message-author-role')
                                  : (i % 2 === 0 ? 'user' : 'assistant');
              const text = (el.innerText || '').trim();
              if (text) out.push({ index: i, role, text });
            });
          } else {
            document.querySelectorAll('[data-message-author-role]').forEach((el, i) => {
              out.push({
                index: i,
                role: el.getAttribute('data-message-author-role'),
                text: (el.innerText || '').trim(),
              });
            });
          }
          return { title: document.title, url: location.href, turns: out };
        }
        """
    )
    browser.close()

(OUT / f"chatgpt_share_{share_id}.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
)
md = [f"# {data['title']}\n", f"Source: {data['url']}\n"]
for t in data["turns"]:
    md.append(f"\n## {t['role'].upper()}\n\n{t['text']}\n\n---\n")
(OUT / f"chatgpt_share_{share_id}.md").write_text("".join(md), encoding="utf-8")

print(f"turns: {len(data['turns'])}")
print(f"wrote: out/chatgpt_share_{share_id}.json")
print(f"wrote: out/chatgpt_share_{share_id}.md")
