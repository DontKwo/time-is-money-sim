"""WebView desktop host and local loopback HTTP server for Life Money Simulator."""

from __future__ import annotations

import argparse
import base64
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse
import urllib.request
import webbrowser

import yaml

from lifesim.compare import compare_scenarios, run_sensitivity_analysis
from lifesim.config import ScenarioModel, load_scenario
from lifesim.engine import run
from lifesim.montecarlo import run_monte_carlo
from lifesim.plots import (
    plot_balances,
    plot_monte_carlo_fan,
    plot_monthly_cashflow,
    plot_net_worth_stack,
    plot_scenario_comparison,
    plot_sensitivity_tornado,
)


def _install_exception_hook() -> None:
    """Install top-level exception hook for desktop GUI error reporting."""

    def _log_unhandled(exc_type: type[BaseException], exc_value: BaseException, exc_tb: Any) -> None:
        del exc_tb
        sys.stderr.write(f"Unhandled TimeIsMoneySim GUI error ({exc_type.__name__}): {exc_value}\n")

    sys.excepthook = _log_unhandled


def resolve_base_dir() -> Path:
    """Resolve PyInstaller bundle root or repository root directory."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def find_chromium_browser() -> str | None:
    """Locate Edge or Chrome binary for app-mode WebView window or headless screenshots."""
    if os.name == "nt":
        win_candidates = [
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]
        for candidate in win_candidates:
            if candidate and Path(candidate).is_file():
                return candidate

    posix_candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "msedge",
        "microsoft-edge",
        "google-chrome",
        "chromium",
        "chromium-browser",
    ]
    for candidate in posix_candidates:
        if os.path.sep in candidate:
            if Path(candidate).is_file():
                return candidate
        else:
            found = shutil.which(candidate)
            if found:
                return found
    return None


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
            days_val = loaded.days or 365
        except Exception:
            days_val = 365
        items.append({"name": yaml_path.name, "label": label, "days": days_val})
    return items


def _resolve_scenario_model(base_dir: Path, payload: dict[str, Any]) -> tuple[ScenarioModel, str]:
    """Load and validate a ScenarioModel from bundled filename, YAML text, or Studio dict."""
    raw_days = payload.get("days")
    days_override = int(raw_days) if raw_days is not None and int(raw_days) > 0 else None

    yaml_text = payload.get("yamlText")
    if isinstance(yaml_text, str) and yaml_text.strip():
        raw_data = yaml.safe_load(yaml_text)
        if not isinstance(raw_data, dict):
            raise ValueError("Uploaded YAML must define a mapping at the root level.")
        if days_override is not None:
            raw_data["days"] = days_override
            raw_data.pop("end", None)
        return ScenarioModel.model_validate(raw_data), "Custom YAML Scenario"

    custom_cfg = payload.get("config")
    if isinstance(custom_cfg, dict):
        copied_cfg = dict(custom_cfg)
        if days_override is not None:
            copied_cfg["days"] = days_override
            copied_cfg.pop("end", None)
        return ScenarioModel.model_validate(copied_cfg), str(payload.get("label") or "Custom Studio Scenario")

    safe_name = Path(str(payload.get("scenario", "example_mvp.yaml"))).name
    scenario_path = (base_dir / "scenarios" / safe_name).resolve()
    if not scenario_path.is_file():
        raise FileNotFoundError(f"Scenario file not found: {safe_name}")
    overrides = [f"days={days_override}"] if days_override is not None else None
    return load_scenario(str(scenario_path), overrides=overrides), safe_name


def _scenario_to_json_yaml(scenario: ScenarioModel) -> tuple[dict[str, Any], str]:
    """Serialize validated ScenarioModel into clean JSON dict and YAML text."""
    clean_dict = scenario.model_dump(mode="json", by_alias=True, exclude_none=True)
    clean_dict.pop("end", None)
    clean_yaml = yaml.safe_dump(clean_dict, sort_keys=False)
    return clean_dict, clean_yaml


def load_scenario_detail_payload(base_dir: Path, scenario_name: str) -> dict[str, Any]:
    """Load bundled scenario fields and normalized YAML for Visual Scenario Studio."""
    safe_name = Path(scenario_name).name
    scenario_path = (base_dir / "scenarios" / safe_name).resolve()
    if not scenario_path.is_file():
        return {"ok": False, "error": f"Scenario file not found: {safe_name}"}
    scenario = load_scenario(str(scenario_path))
    clean_dict, clean_yaml = _scenario_to_json_yaml(scenario)
    return {"ok": True, "name": safe_name, "config": clean_dict, "yamlText": clean_yaml}


def validate_scenario_payload(base_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize Visual Scenario Studio or uploaded YAML payload."""
    try:
        scenario, label = _resolve_scenario_model(base_dir, payload)
        clean_dict, clean_yaml = _scenario_to_json_yaml(scenario)
        return {"ok": True, "label": label, "config": clean_dict, "yamlText": clean_yaml}
    except (ValueError, KeyError, FileNotFoundError, yaml.YAMLError) as exc:
        return {"ok": False, "error": str(exc)}


def _build_simulation_result(scenario: ScenarioModel, label: str) -> dict[str, Any]:
    """Execute deterministic daily simulation and render chart URIs and ledger rows."""
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
    rows: list[dict[str, object]] = []
    if not ledger_df.empty:
        for rec in ledger_df.head(60).to_dict(orient="records"):
            rows.append({
                "date": str(rec.get("date", "")),
                "flow": str(rec.get("flow", "")),
                "account": str(rec.get("account", "")),
                "amount": float(rec.get("amount", 0.0)),
                "balance": float(rec.get("balance", 0.0)),
            })

    clean_dict, clean_yaml = _scenario_to_json_yaml(scenario)
    return {
        "ok": True,
        "message": f"Simulated {label} across {scenario.days} days.",
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
        "config": clean_dict,
        "yamlText": clean_yaml,
    }


def execute_simulation_payload(
    base_dir: Path,
    scenario_name: str,
    days_override: int | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run deterministic daily simulation from bundled file, YAML, or Studio config."""
    try:
        effective = dict(payload or {})
        effective.setdefault("scenario", scenario_name)
        if days_override is not None:
            effective["days"] = days_override
        scenario, label = _resolve_scenario_model(base_dir, effective)
        return _build_simulation_result(scenario, label)
    except (ValueError, KeyError, FileNotFoundError, yaml.YAMLError) as exc:
        return {"ok": False, "error": str(exc)}


def execute_monte_carlo_payload(
    base_dir: Path,
    scenario_name: str,
    days_override: int | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute 100 Monte Carlo runs and return base64 fan chart."""
    try:
        effective = dict(payload or {})
        effective.setdefault("scenario", scenario_name)
        if days_override is not None:
            effective["days"] = days_override
        scenario, label = _resolve_scenario_model(base_dir, effective)
    except (ValueError, KeyError, FileNotFoundError, yaml.YAMLError) as exc:
        return {"ok": False, "error": str(exc)}

    mc_result = run_monte_carlo(scenario, num_runs=100)
    with tempfile.TemporaryDirectory() as tmp_dir:
        mc_img = Path(tmp_dir) / "mc_fan.png"
        plot_monte_carlo_fan(mc_result, str(mc_img))
        chart_uri = encode_png_data_url(mc_img)
    return {
        "ok": True,
        "message": f"Completed {mc_result.num_runs} Monte Carlo trials for {label}.",
        "defaultChart": "analytics",
        "charts": {"analytics": chart_uri},
    }


def execute_sensitivity_payload(
    base_dir: Path,
    scenario_name: str,
    days_override: int | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute parameter sensitivity sweep and return base64 tornado chart."""
    try:
        effective = dict(payload or {})
        effective.setdefault("scenario", scenario_name)
        if days_override is not None:
            effective["days"] = days_override
        scenario, label = _resolve_scenario_model(base_dir, effective)
    except (ValueError, KeyError, FileNotFoundError, yaml.YAMLError) as exc:
        return {"ok": False, "error": str(exc)}

    sens_result = run_sensitivity_analysis(scenario)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tornado_img = Path(tmp_dir) / "tornado.png"
        plot_sensitivity_tornado(sens_result, str(tornado_img))
        chart_uri = encode_png_data_url(tornado_img)
    if not chart_uri:
        return {
            "ok": True,
            "message": f"No sweepable levers configured in {label} for tornado sensitivity.",
            "defaultChart": "balances",
        }
    return {
        "ok": True,
        "message": f"Completed sensitivity sweep for {label}.",
        "defaultChart": "analytics",
        "charts": {"analytics": chart_uri},
    }


def execute_compare_payload(base_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Compare multiple bundled and/or custom scenarios side by side."""
    try:
        selected_names = payload.get("scenarios", [])
        if not isinstance(selected_names, list):
            return {"ok": False, "error": "Field 'scenarios' must be a list of scenario filenames."}

        days_val = payload.get("days")
        days_override = int(days_val) if days_val is not None and int(days_val) > 0 else None
        named_scenarios: dict[str, ScenarioModel] = {}

        for raw_name in selected_names:
            safe_name = Path(str(raw_name)).name
            scenario_path = (base_dir / "scenarios" / safe_name).resolve()
            if not scenario_path.is_file():
                continue
            overrides = [f"days={days_override}"] if days_override is not None else None
            label = safe_name.replace(".yaml", "").replace("example_", "").replace("_", " ").title()
            named_scenarios[label] = load_scenario(str(scenario_path), overrides=overrides)

        custom_cfg = payload.get("customConfig")
        if isinstance(custom_cfg, dict):
            copied = dict(custom_cfg)
            if days_override is not None:
                copied["days"] = days_override
                copied.pop("end", None)
            custom_label = str(payload.get("customLabel") or "Custom Studio")
            named_scenarios[custom_label] = ScenarioModel.model_validate(copied)

        if len(named_scenarios) < 2:
            return {"ok": False, "error": "Select at least two scenarios to compare."}

        comp_result = compare_scenarios(named_scenarios)
        with tempfile.TemporaryDirectory() as tmp_dir:
            comp_img = Path(tmp_dir) / "comparison.png"
            plot_scenario_comparison(comp_result, str(comp_img))
            chart_uri = encode_png_data_url(comp_img)

        table_rows: list[dict[str, object]] = []
        for rec in comp_result.table.to_dict(orient="records"):
            table_rows.append({
                "scenario": str(rec.get("scenario", "")),
                "endingNetWorth": float(rec.get("ending_net_worth", 0.0)),
                "deltaVsBaseline": float(rec.get("delta_vs_baseline", 0.0)),
                "lowestChecking": float(rec.get("lowest_checking", 0.0)),
                "fiDate": str(rec.get("fi_date", "Not Reached")),
            })
        return {
            "ok": True,
            "message": f"Compared {len(named_scenarios)} scenarios.",
            "defaultChart": "comparison",
            "charts": {"comparison": chart_uri},
            "table": table_rows,
        }
    except (ValueError, KeyError, FileNotFoundError, yaml.YAMLError) as exc:
        return {"ok": False, "error": str(exc)}


class GuiHandler(BaseHTTPRequestHandler):
    """Serve Life Money Simulator WebView assets and simulation endpoints."""

    def __init__(self, base_dir: Path, *args: object, **kwargs: object) -> None:
        self.base_dir = base_dir
        self.static_dir = base_dir / "lifesim" / "gui_static"
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def log_message(self, format: str, *args: object) -> None:
        """Suppress HTTP server stderr logs."""
        del format, args

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
        """Handle static UI files, icon, scenario details, and GET APIs."""
        parsed = urlparse(self.path)
        req_path = parsed.path
        if req_path == "/api/health":
            self._send_json(HTTPStatus.OK, {"ok": True, "app": "TimeIsMoneySim"})
            return
        if req_path == "/api/scenarios":
            self._send_json(HTTPStatus.OK, {"ok": True, "scenarios": list_available_scenarios(self.base_dir)})
            return
        if req_path == "/api/scenario-detail":
            query = parse_qs(parsed.query)
            name = (query.get("name") or ["example_mvp.yaml"])[0]
            self._send_json(HTTPStatus.OK, load_scenario_detail_payload(self.base_dir, name))
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
        """Handle simulation, Monte Carlo, sensitivity, comparison, and validation APIs."""
        req_path = urlparse(self.path).path
        try:
            payload = self._read_json()
            scenario_name = str(payload.get("scenario", "example_mvp.yaml"))
            raw_days = payload.get("days")
            days_override = int(raw_days) if raw_days is not None else None
            if req_path in ("/api/simulate", "/api/simulate-custom"):
                self._send_json(
                    HTTPStatus.OK,
                    execute_simulation_payload(self.base_dir, scenario_name, days_override, payload=payload),
                )
                return
            if req_path == "/api/montecarlo":
                self._send_json(
                    HTTPStatus.OK,
                    execute_monte_carlo_payload(self.base_dir, scenario_name, days_override, payload=payload),
                )
                return
            if req_path == "/api/sensitivity":
                self._send_json(
                    HTTPStatus.OK,
                    execute_sensitivity_payload(self.base_dir, scenario_name, days_override, payload=payload),
                )
                return
            if req_path == "/api/compare":
                self._send_json(HTTPStatus.OK, execute_compare_payload(self.base_dir, payload))
                return
            if req_path == "/api/scenario-validate":
                self._send_json(HTTPStatus.OK, validate_scenario_payload(self.base_dir, payload))
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
    resolved = output_png.expanduser().resolve()
    target_png = resolved if resolved.suffix.lower() == ".png" else resolved / "01_main.png"
    target_png.parent.mkdir(parents=True, exist_ok=True)
    browser = find_chromium_browser()
    if not browser:
        raise RuntimeError("No Chromium or Edge executable available.")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile_dir:
        subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                "--virtual-time-budget=2500",
                f"--user-data-dir={profile_dir}",
                "--window-size=1440,900",
                f"--screenshot={target_png}",
                base_url,
            ],
            check=True,
            timeout=45,
        )
    if not target_png.is_file() or target_png.stat().st_size < 1000:
        raise RuntimeError(f"Screenshot output missing or empty: {target_png}")
    sys.stdout.write(f"SCREENSHOT_OK {target_png}\n")
    sys.stdout.flush()


def _launch_app_window(base_url: str, server: ThreadingHTTPServer, worker: threading.Thread) -> None:
    """Open standalone WebView app window and wait until user closes it."""
    browser = find_chromium_browser()
    if browser:
        profile_root = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "TimeIsMoneySim" / "WindowProfile"
        profile_root.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            [
                browser,
                f"--app={base_url}",
                f"--user-data-dir={profile_root}",
                "--new-window",
                "--window-size=1440,900",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )
        proc.wait()
        server.shutdown()
        return
    webbrowser.open(base_url)
    worker.join()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse desktop GUI launch arguments."""
    parser = argparse.ArgumentParser(description="Life Money Simulator Desktop GUI")
    parser.add_argument("--self-test", action="store_true", help="Run HTTP health and simulation check then exit")
    parser.add_argument("--headless-server", type=int, default=None, help="Bind local port without launching browser")
    parser.add_argument("--screenshot", default=None, help="Capture screenshot to output PNG path and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Launch Life Money Simulator loopback HTTP server and desktop UI."""
    _install_exception_hook()
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
        _launch_app_window(base_url, server, worker)
    except KeyboardInterrupt:
        sys.stderr.write("Shutting down TimeIsMoneySim GUI.\n")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
