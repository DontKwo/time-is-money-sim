"""Tests for Life Money Simulator desktop WebView server, Studio, comparison, and simulation APIs."""

from __future__ import annotations

from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import urllib.request

from lifesim.gui import GuiHandler, capture_screenshot, resolve_base_dir, run_self_test


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_gui_server_endpoints_and_self_test() -> None:
    base_dir = resolve_base_dir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(GuiHandler, base_dir))
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}/"
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        run_self_test(base_url)

        with urllib.request.urlopen(f"{base_url}api/scenario-detail?name=example_mvp.yaml", timeout=10) as resp:
            detail_data = json.loads(resp.read().decode("utf-8"))
            assert detail_data["ok"] is True
            assert "yamlText" in detail_data
            assert "checking" in detail_data["config"]["accounts"]

        custom_cfg = {
            "start": "2026-01-01",
            "days": 90,
            "seed": 7,
            "accounts": {
                "checking": {"kind": "checking", "balance": 2500.0},
                "hysa": {"kind": "hysa", "balance": 10000.0, "annual_growth_rate": 0.04},
            },
            "flows": [
                {
                    "name": "Pay",
                    "type": "income",
                    "to": "checking",
                    "schedule": {"monthly": 1},
                    "amount": {"fixed": 4000.0},
                },
                {
                    "name": "Rent",
                    "type": "expense",
                    "from": "checking",
                    "schedule": {"monthly": 5},
                    "amount": {"fixed": 1500.0},
                },
            ],
            "goals": [{"name": "Savings Target", "kind": "net_worth", "target_amount": 15000.0}],
        }
        val_data = _post_json(f"{base_url}api/scenario-validate", {"config": custom_cfg})
        assert val_data["ok"] is True
        assert "checking:" in str(val_data["yamlText"])

        custom_sim = _post_json(f"{base_url}api/simulate-custom", {"config": custom_cfg, "label": "Unit Test Studio"})
        assert custom_sim["ok"] is True
        assert custom_sim["kpis"]["endingNetWorth"] > 12500.0  # type: ignore[operator]
        assert str(custom_sim["charts"]["balances"]).startswith("data:image/png;base64,")

        mc_data = _post_json(f"{base_url}api/montecarlo", {"scenario": "example_401k_match.yaml", "days": 90})
        assert mc_data["ok"] is True
        assert str(mc_data["charts"]["analytics"]).startswith("data:image/png;base64,")

        sens_data = _post_json(f"{base_url}api/sensitivity", {"scenario": "example_401k_match.yaml", "days": 90})
        assert sens_data["ok"] is True
        assert str(sens_data["charts"]["analytics"]).startswith("data:image/png;base64,")

        comp_data = _post_json(
            f"{base_url}api/compare",
            {"scenarios": ["example_mvp.yaml", "example_401k_match.yaml"], "days": 90},
        )
        assert comp_data["ok"] is True
        assert len(comp_data["table"]) == 2
        assert str(comp_data["charts"]["comparison"]).startswith("data:image/png;base64,")

        with tempfile.TemporaryDirectory() as tmp_dir:
            shot_file = Path(tmp_dir) / "gui_shot.png"
            capture_screenshot(base_url, shot_file)
            assert shot_file.is_file() and shot_file.stat().st_size > 5000
    finally:
        server.shutdown()
        server.server_close()
