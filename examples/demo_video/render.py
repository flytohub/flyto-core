#!/usr/bin/env python3
"""
Render video.html → MP4 + GIF using Playwright headless browser.

No manual screen recording needed.
Output: demo.mp4, demo.gif (in same directory as this script)

Usage:
    cd flyto-core
    python examples/demo_video/render.py          # MP4 only
    python examples/demo_video/render.py --gif     # MP4 + GIF
    python examples/demo_video/render.py --gif --width 1280 --height 720
"""

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HTML_FILE = HERE / "video.html"


async def render(width: int, height: int, make_gif: bool):
    from playwright.async_api import async_playwright

    output_dir = HERE
    mp4_path = output_dir / "demo.mp4"
    gif_path = output_dir / "demo.gif"

    print(f"  Resolution: {width}x{height}")
    print(f"  HTML:       {HTML_FILE}")
    print(f"  Output:     {mp4_path}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(output_dir),
            record_video_size={"width": width, "height": height},
        )

        page = await context.new_page()
        await page.goto(f"file://{HTML_FILE}")

        # Wait for the animation to complete.
        # The JS play() takes ~200s, started after 1.2s delay.
        # Add safety margin.
        total_wait = 210
        print(f"  Recording {total_wait}s ...")
        for elapsed in range(total_wait):
            await asyncio.sleep(1)
            pct = int((elapsed + 1) / total_wait * 100)
            print(f"\r  Recording ... {pct}%  ({elapsed+1}/{total_wait}s)", end="", flush=True)

        print()

        await context.close()
        await browser.close()

    # Playwright saves video with a random name — find it and rename
    videos = sorted(output_dir.glob("*.webm"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not videos:
        print("  ERROR: No video file found!")
        return

    raw_video = videos[0]
    print(f"  Raw video: {raw_video.name}")

    # Convert webm → mp4 with ffmpeg
    print(f"  Converting → {mp4_path.name} ...")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(raw_video),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        str(mp4_path),
    ], check=True, capture_output=True)

    raw_video.unlink()
    size_mb = mp4_path.stat().st_size / 1024 / 1024
    print(f"  ✓ {mp4_path.name} ({size_mb:.1f} MB)")

    # Optional: MP4 → GIF
    if make_gif:
        print(f"  Converting → {gif_path.name} ...")
        # Two-pass: generate palette, then use it for high-quality GIF
        palette = output_dir / "_palette.png"
        fps = 15
        scale = min(width, 960)

        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(mp4_path),
            "-vf", f"fps={fps},scale={scale}:-1:flags=lanczos,palettegen=stats_mode=diff",
            str(palette),
        ], check=True, capture_output=True)

        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(mp4_path),
            "-i", str(palette),
            "-lavfi", f"fps={fps},scale={scale}:-1:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
            str(gif_path),
        ], check=True, capture_output=True)

        palette.unlink(missing_ok=True)
        gif_mb = gif_path.stat().st_size / 1024 / 1024
        print(f"  ✓ {gif_path.name} ({gif_mb:.1f} MB)")

    print("\n  Done!")


def main():
    parser = argparse.ArgumentParser(description="Render flyto-core demo video")
    parser.add_argument("--width", type=int, default=1280, help="Video width (default 1280)")
    parser.add_argument("--height", type=int, default=720, help="Video height (default 720)")
    parser.add_argument("--gif", action="store_true", help="Also generate GIF")
    args = parser.parse_args()

    print("\n  flyto-core Demo Video Renderer\n")
    asyncio.run(render(args.width, args.height, args.gif))


if __name__ == "__main__":
    main()
