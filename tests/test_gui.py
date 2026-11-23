"""Tests for Life Money Simulator desktop WebView server and simulation APIs."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from functools import partial

from lifesim.gui import GuiHandler, resolve_base_dir, run_self_test


def test_gui_server_endpoints_and_self_test() -> None:
    base_dir = resolve_base_dir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(GuiHandler, base_dir))
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}/"
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        run_self_test(base_url)

        mc_req = urllib.request.Request(
            f"{base_url}api/montecarlo",
            data=json.dumps({"scenario": "example_401k_match.yaml", "days": 90}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(mc_req, timeout=20) as resp:
            mc_data = json.loads(resp.read().decode("utf-8"))
            assert mc_data["ok"] is True
            assert mc_data["charts"]["analytics"].startswith("data:image/png;base64,")

        sens_req = urllib.request.Request(
            f"{base_url}api/sensitivity",
            data=json.dumps({"scenario": "example_401k_match.yaml", "days": 90}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(sens_req, timeout=20) as resp:
            sens_data = json.loads(resp.read().decode("utf-8"))
            assert sens_data["ok"] is True
            assert sens_data["charts"]["analytics"].startswith("data:image/png;base64,")
    finally:
        server.shutdown()
        server.server_close()
