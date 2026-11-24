"""Capture up-to-date screenshots and optional UI evidence for TimeIsMoneySim."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from playwright.sync_api import sync_playwright

REPO_DIR = Path(__file__).resolve().parent.parent


def _launch_browser(pw: Any) -> Any:
    """Launch headless Chromium first (Linux/CI), falling back to Edge channel if needed."""
    try:
        return pw.chromium.launch(headless=True)
    except Exception:  # noqa: 10
        return pw.chromium.launch(channel="msedge", headless=True)


def capture_screenshots(out_dir: Path, python_exe: str | None = None) -> None:
    """Boot headless loopback server and capture main Dashboard and Monte Carlo screenshots."""
    out_resolved = out_dir.expanduser().resolve()
    out_resolved.mkdir(parents=True, exist_ok=True)
    shot_main = out_resolved / "01_main.png"
    shot_analytics = out_resolved / "02_analytics.png"

    proc = subprocess.Popen(
        [python_exe or sys.executable, "-m", "lifesim.gui", "--headless-server", "0"],
        cwd=str(REPO_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        url = ""
        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline and proc.stdout is not None:
            line = proc.stdout.readline().strip()
            if line.startswith("READY "):
                url = line.split(" ", 1)[1].strip()
                break
        if not url:
            raise RuntimeError("TimeIsMoneySim headless server failed to start.")

        with sync_playwright() as pw:
            browser = _launch_browser(pw)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector('#kpiNetWorth:not(:has-text("--"))', timeout=20000)

            page.select_option('[data-testid="scenario.select"]', "example_401k_match.yaml")
            page.fill('[data-testid="scenario.days_input"]', "365")
            page.click('[data-testid="sim.run_btn"]')
            page.wait_for_function(
                "() => { const txt = document.getElementById('statusBanner')?.textContent || ''; return txt.length > 0 && !txt.includes('Running'); }",
                timeout=20000,
            )
            page.wait_for_timeout(400)
            page.screenshot(path=str(shot_main), full_page=False)

            page.click('[data-testid="sim.montecarlo_btn"]')
            page.wait_for_function(
                "() => (document.getElementById('statusBanner')?.textContent || '').includes('Completed 100 Monte Carlo')",
                timeout=30000,
            )
            page.wait_for_timeout(400)
            page.screenshot(path=str(shot_analytics), full_page=False)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture TimeIsMoneySim desktop screenshots.")
    parser.add_argument("--out-dir", type=Path, default=REPO_DIR / "assets" / "screenshots")
    parser.add_argument("--py", default=None, help="Optional Python interpreter to launch GUI backend")
    args = parser.parse_args()
    capture_screenshots(args.out_dir, python_exe=args.py)
    sys.stdout.write(f"Saved screenshots into {args.out_dir}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
