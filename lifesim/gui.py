"""WebView desktop host and local loopback HTTP server for Life Money Simulator."""

from __future__ import annotations

import argparse
import base64
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any
from urllib.parse import urlparse
import urllib.request
import webbrowser

from .compare import run_sensitivity_analysis
from .config import load_scenario
from .engine import run
from .montecarlo import run_monte_carlo
from .plots import (
    plot_balances,
    plot_monte_carlo_fan,
    plot_monthly_cashflow,
    plot_net_worth_stack,
    plot_sensitivity_tornado,
)


def resolve_base_dir() -> Path:
    """Resolve PyInstaller bundle root or repository root directory."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def encode_png_data_url(image_path: Path) -> str:
    """Read PNG output and encode it as a base64 data URI."""
    if not image_path.is_file():
        return ""
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def list_available_scenarios(base_dir: Path) -> list[dict[str, object]]:
    """List bundled YAML scenario templates with day horizons."""
    scenarios_dir = base_dir / "scenarios"
    items: list[dict[str, object]] = []
    if not scenarios_dir.is_dir():
        return items
    for yaml_path in sorted(scenarios_dir.glob("*.yaml")):
        label = yaml_path.stem.replace("example_", "").replace("_", " ").title()
        days_val = 365
        try:
            loaded = load_scenario(str(yaml_path))
            days_val = loaded.days
        except Exception:
            days_val = 365
        items.append({"name": yaml_path.name, "label": label, "days": days_val})
    return items


def execute_simulation_payload(base_dir: Path, scenario_name: str, days_override: int | None) -> dict[str, Any]:
    """Run deterministic daily simulation and encode charts as base64 images."""
    safe_name = Path(scenario_name).name
    scenario_path = (base_dir / "scenarios" / safe_name).resolve()
    if not scenario_path.is_file():
        return {"ok": False, "error": f"Scenario file not found: {safe_name}"}

    overrides = [f"days={int(days_override)}"] if days_override and days_override > 0 else None
    scenario = load_scenario(str(scenario_path), overrides=overrides)
    ledger = run(scenario)

    nw_metrics = ledger.metrics.get("net_worth", {})
    debt_metrics = ledger.metrics.get("debt", {})
    achieved_count = sum(1 for item in ledger.goal_results if item.get("achieved"))
    total_goals = len(ledger.goal_results)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        bal_img = tmp_path / "balances.png"
        nw_img = tmp_path / "networth.png"
        cf_img = tmp_path / "cashflow.png"
        plot_balances(ledger.to_df(), str(bal_img))
        plot_net_worth_stack(ledger, str(nw_img))
        plot_monthly_cashflow(ledger, str(cf_img))
        charts = {
            "balances": encode_png_data_url(bal_img),
            "networth": encode_png_data_url(nw_img),
            "cashflow": encode_png_data_url(cf_img),
        }

    ledger_df = ledger.to_df()
    csv_text = ledger_df.to_csv(index=False) if not ledger_df.empty else "date,flow,amount,account,balance\n"
    rows = []
    if not ledger_df.empty:
        for rec in ledger_df.head(60).to_dict(orient="records"):
            rows.append({
                "date": str(rec.get("date", "")),
                "flow": str(rec.get("flow", "")),
                "account": str(rec.get("account", "")),
                "amount": float(rec.get("amount", 0.0)),
                "balance": float(rec.get("balance", 0.0)),
            })

    return {
        "ok": True,
        "message": f"Simulated {safe_name} across {scenario.days} days.",
        "defaultChart": "balances",
        "kpis": {
            "endingNetWorth": float(nw_metrics.get("ending", 0.0)),
            "liquidNetWorth": float(nw_metrics.get("ending_liquid", 0.0)),
            "totalDebt": float(debt_metrics.get("ending", 0.0)),
            "goalsMet": f"{achieved_count} / {total_goals}",
        },
        "charts": charts,
        "ledger": rows,
        "csv": csv_text,
    }


def execute_monte_carlo_payload(base_dir: Path, scenario_name: str, days_override: int | None) -> dict[str, Any]:
    """Execute 100 Monte Carlo runs and return base64 fan chart."""
    safe_name = Path(scenario_name).name
    scenario_path = (base_dir / "scenarios" / safe_name).resolve()
    if not scenario_path.is_file():
        return {"ok": False, "error": f"Scenario file not found: {safe_name}"}

    overrides = [f"days={int(days_override)}"] if days_override and days_override > 0 else None
    scenario = load_scenario(str(scenario_path), overrides=overrides)
    mc_result = run_monte_carlo(scenario, num_runs=100)
    with tempfile.TemporaryDirectory() as tmp_dir:
        mc_img = Path(tmp_dir) / "mc_fan.png"
        plot_monte_carlo_fan(mc_result, str(mc_img))
        chart_uri = encode_png_data_url(mc_img)
    return {
        "ok": True,
        "message": f"Completed {mc_result.num_runs} Monte Carlo trials for {safe_name}.",
        "defaultChart": "analytics",
        "charts": {"analytics": chart_uri},
    }


def execute_sensitivity_payload(base_dir: Path, scenario_name: str, days_override: int | None) -> dict[str, Any]:
    """Execute parameter sensitivity sweep and return base64 tornado chart."""
    safe_name = Path(scenario_name).name
    scenario_path = (base_dir / "scenarios" / safe_name).resolve()
    if not scenario_path.is_file():
        return {"ok": False, "error": f"Scenario file not found: {safe_name}"}

    overrides = [f"days={int(days_override)}"] if days_override and days_override > 0 else None
    scenario = load_scenario(str(scenario_path), overrides=overrides)
    sens_result = run_sensitivity_analysis(scenario)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tornado_img = Path(tmp_dir) / "tornado.png"
        plot_sensitivity_tornado(sens_result, str(tornado_img))
        chart_uri = encode_png_data_url(tornado_img)
    if not chart_uri:
        return {
            "ok": True,
            "message": f"No sweepable levers configured in {safe_name} for tornado sensitivity.",
            "defaultChart": "balances",
        }
    return {
        "ok": True,
        "message": f"Completed sensitivity sweep for {safe_name}.",
        "defaultChart": "analytics",
        "charts": {"analytics": chart_uri},
    }


class GuiHandler(BaseHTTPRequestHandler):
    """Serve Life Money Simulator WebView assets and simulation endpoints."""

    def __init__(self, base_dir: Path, *args: object, **kwargs: object) -> None:
        self.base_dir = base_dir
        self.static_dir = base_dir / "lifesim" / "gui_static"
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def log_message(self, format: str, *args: object) -> None:
        """Suppress HTTP server stderr logs."""
        return None

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, status: int, mime_type: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self) -> None:
        """Handle static UI files, icon, and GET APIs."""
        req_path = urlparse(self.path).path
        if req_path == "/api/health":
            self._send_json(HTTPStatus.OK, {"ok": True, "app": "TimeIsMoneySim"})
            return
        if req_path == "/api/scenarios":
            self._send_json(HTTPStatus.OK, {"ok": True, "scenarios": list_available_scenarios(self.base_dir)})
            return
        if req_path == "/icon.png":
            icon_file = self.base_dir / "assets" / "icon.png"
            if icon_file.is_file():
                self._send_bytes(HTTPStatus.OK, "image/png", icon_file.read_bytes())
                return
        rel = "index.html" if req_path in ("", "/") else req_path.lstrip("/")
        candidate = (self.static_dir / rel).resolve()
        if not str(candidate).startswith(str(self.static_dir.resolve())) or not candidate.is_file():
            self._send_bytes(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not Found")
            return
        mime_type, _ = mimetypes.guess_type(str(candidate))
        self._send_bytes(HTTPStatus.OK, mime_type or "application/octet-stream", candidate.read_bytes())

    def do_POST(self) -> None:
        """Handle simulation execution APIs."""
        req_path = urlparse(self.path).path
        try:
            payload = self._read_json()
            scenario_name = str(payload.get("scenario", "example_mvp.yaml"))
            raw_days = payload.get("days")
            days_override = int(raw_days) if raw_days is not None else None
            if req_path == "/api/simulate":
                self._send_json(HTTPStatus.OK, execute_simulation_payload(self.base_dir, scenario_name, days_override))
                return
            if req_path == "/api/montecarlo":
                self._send_json(HTTPStatus.OK, execute_monte_carlo_payload(self.base_dir, scenario_name, days_override))
                return
            if req_path == "/api/sensitivity":
                self._send_json(HTTPStatus.OK, execute_sensitivity_payload(self.base_dir, scenario_name, days_override))
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": f"Unknown endpoint: {req_path}"})
        except Exception as exc:
            self._send_json(HTTPStatus.OK, {"ok": False, "error": str(exc)})


def run_self_test(base_url: str) -> None:
    """Verify UI root, health check, scenario listing, and MVP simulation over HTTP."""
    with urllib.request.urlopen(base_url, timeout=5) as resp:
        html = resp.read().decode("utf-8")
        if "Life Money Simulator" not in html:
            raise RuntimeError("Self-test failed: root HTML missing title.")
    with urllib.request.urlopen(f"{base_url}api/health", timeout=5) as resp:
        if not json.loads(resp.read().decode("utf-8")).get("ok"):
            raise RuntimeError("Self-test failed: health check returned false.")
    with urllib.request.urlopen(f"{base_url}api/scenarios", timeout=5) as resp:
        scenarios = json.loads(resp.read().decode("utf-8")).get("scenarios", [])
        if not scenarios:
            raise RuntimeError("Self-test failed: no scenarios returned.")
    req = urllib.request.Request(
        f"{base_url}api/simulate",
        data=json.dumps({"scenario": scenarios[0]["name"], "days": 60}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        sim = json.loads(resp.read().decode("utf-8"))
        if not sim.get("ok") or not sim.get("charts", {}).get("balances"):
            raise RuntimeError("Self-test failed: simulation or balance chart missing.")
    sys.stdout.write(f"SELF_TEST_OK {base_url}\n")
    sys.stdout.flush()


def capture_screenshot(base_url: str, output_png: Path) -> None:
    """Capture headless browser screenshot using an isolated temporary profile."""
    output_png.parent.mkdir(parents=True, exist_ok=True)
    candidates = ["msedge", "microsoft-edge", "google-chrome", "chromium", "chromium-browser"]
    browser = next((shutil.which(name) for name in candidates if shutil.which(name)), None)
    if not browser:
        raise RuntimeError("No Chromium or Edge executable available.")
    with tempfile.TemporaryDirectory() as profile_dir:
        subprocess.run(
            [
                browser,
                "--headless",
                "--disable-gpu",
                f"--user-data-dir={profile_dir}",
                "--window-size=1440,900",
                f"--screenshot={output_png}",
                base_url,
            ],
            check=True,
            timeout=30,
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse desktop GUI launch arguments."""
    parser = argparse.ArgumentParser(description="Life Money Simulator Desktop GUI")
    parser.add_argument("--self-test", action="store_true", help="Run HTTP health and simulation check then exit")
    parser.add_argument("--headless-server", type=int, default=None, help="Bind local port without launching browser")
    parser.add_argument("--screenshot", default=None, help="Capture screenshot to output PNG path and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Launch Life Money Simulator loopback HTTP server and desktop UI."""
    args = parse_args(argv)
    base_dir = resolve_base_dir()
    port = int(args.headless_server) if args.headless_server is not None else 0
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(GuiHandler, base_dir))
    actual_port = server.server_address[1]
    base_url = f"http://127.0.0.1:{actual_port}/"

    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        if args.self_test:
            run_self_test(base_url)
            return 0
        if args.screenshot:
            capture_screenshot(base_url, Path(args.screenshot))
            return 0
        if args.headless_server is not None:
            sys.stdout.write(f"READY {base_url}\n")
            sys.stdout.flush()
            worker.join()
            return 0
        webbrowser.open(base_url)
        worker.join()
    except KeyboardInterrupt:
        sys.stderr.write("Shutting down TimeIsMoneySim GUI.\n")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
