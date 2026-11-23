(function () {
  "use strict";

  const state = {
    charts: {},
    ledgerCsv: "",
    activeChartKey: "balances"
  };

  function setStatus(message) {
    const el = document.getElementById("statusBanner");
    if (el) el.textContent = message;
  }

  window.addEventListener("error", function (event) {
    setStatus("Unexpected interface error: " + (event.message || "Unknown failure"));
  });

  window.addEventListener("unhandledrejection", function (event) {
    setStatus("Request did not finish cleanly: " + (event.reason ? String(event.reason) : "Unknown error"));
  });

  function formatUsd(value) {
    const num = Number(value || 0);
    return "$" + num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  async function apiGet(url) {
    const resp = await fetch(url, { cache: "no-store" });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return resp.json();
  }

  async function apiPost(url, payload) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return resp.json();
  }

  function showChart(chartKey) {
    state.activeChartKey = chartKey;
    const map = {
      "balances": "charts.balances_tab",
      "networth": "charts.networth_tab",
      "cashflow": "charts.cashflow_tab",
      "analytics": "charts.analytics_tab"
    };
    Object.keys(map).forEach(function (key) {
      const btn = document.querySelector('[data-testid="' + map[key] + '"]');
      if (btn) btn.classList.toggle("active", key === chartKey);
    });

    const img = document.getElementById("chartImage");
    const empty = document.getElementById("chartEmptyState");
    const src = state.charts[chartKey];
    if (img && empty) {
      if (src) {
        img.src = src;
        img.hidden = false;
        empty.hidden = true;
      } else {
        img.hidden = true;
        empty.hidden = false;
      }
    }
  }

  function renderLedger(rows) {
    const host = document.getElementById("ledgerHost");
    if (!host) return;
    host.textContent = "";
    if (!rows || rows.length === 0) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "No transactions recorded in this scenario.";
      host.appendChild(p);
      return;
    }
    const table = document.createElement("table");
    table.innerHTML = "<thead><tr><th>Date</th><th>Flow</th><th>Account</th><th>Amount</th><th>Balance</th></tr></thead><tbody></tbody>";
    const tbody = table.querySelector("tbody");
    rows.slice(0, 50).forEach(function (row) {
      const tr = document.createElement("tr");
      [row.date, row.flow, row.account, formatUsd(row.amount), formatUsd(row.balance)].forEach(function (cellVal) {
        const td = document.createElement("td");
        td.textContent = String(cellVal);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    host.appendChild(table);
  }

  function applyResult(res) {
    if (!res.ok) {
      setStatus(res.error || "Simulation returned an error.");
      return;
    }
    if (res.kpis) {
      const kpi = res.kpis;
      document.getElementById("kpiNetWorth").textContent = formatUsd(kpi.endingNetWorth);
      document.getElementById("kpiLiquid").textContent = formatUsd(kpi.liquidNetWorth);
      document.getElementById("kpiDebt").textContent = formatUsd(kpi.totalDebt);
      document.getElementById("kpiGoals").textContent = String(kpi.goalsMet || "0 / 0");
    }

    if (res.charts) {
      Object.keys(res.charts).forEach(function (key) {
        state.charts[key] = res.charts[key];
      });
    }
    if (res.csv !== undefined) {
      state.ledgerCsv = res.csv;
    }
    if (res.ledger) {
      renderLedger(res.ledger);
    }
    showChart(res.defaultChart || state.activeChartKey);
    setStatus(res.message || "Completed simulation.");
  }

  function currentPayload() {
    return {
      scenario: document.getElementById("scenario.select").value,
      days: Number(document.getElementById("scenario.days_input").value || 365)
    };
  }

  async function initScenarios() {
    const data = await apiGet("/api/scenarios");
    const select = document.getElementById("scenario.select");
    select.textContent = "";
    (data.scenarios || []).forEach(function (item) {
      const opt = document.createElement("option");
      opt.value = item.name;
      opt.textContent = item.label;
      select.appendChild(opt);
    });
    if (data.scenarios && data.scenarios.length > 0) {
      document.getElementById("scenario.days_input").value = String(data.scenarios[0].days || 365);
      const res = await apiPost("/api/simulate", currentPayload());
      applyResult(res);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelector('[data-testid="charts.balances_tab"]').addEventListener("click", function () { showChart("balances"); });
    document.querySelector('[data-testid="charts.networth_tab"]').addEventListener("click", function () { showChart("networth"); });
    document.querySelector('[data-testid="charts.cashflow_tab"]').addEventListener("click", function () { showChart("cashflow"); });
    document.querySelector('[data-testid="charts.analytics_tab"]').addEventListener("click", function () { showChart("analytics"); });

    document.querySelector('[data-testid="header.theme_toggle"]').addEventListener("click", function (ev) {
      const root = document.documentElement;
      const isLight = root.getAttribute("data-theme") === "light";
      if (isLight) {
        root.removeAttribute("data-theme");
        ev.currentTarget.textContent = "Light Theme";
      } else {
        root.setAttribute("data-theme", "light");
        ev.currentTarget.textContent = "Dark Theme";
      }
    });

    document.querySelector('[data-testid="sim.run_btn"]').addEventListener("click", async function () {
      setStatus("Running daily-tick simulation...");
      const res = await apiPost("/api/simulate", currentPayload());
      applyResult(res);
    });

    document.querySelector('[data-testid="sim.montecarlo_btn"]').addEventListener("click", async function () {
      setStatus("Running 100 Monte Carlo trials...");
      const res = await apiPost("/api/montecarlo", currentPayload());
      applyResult(res);
    });

    document.querySelector('[data-testid="sim.sensitivity_btn"]').addEventListener("click", async function () {
      setStatus("Running parameter sensitivity sweep...");
      const res = await apiPost("/api/sensitivity", currentPayload());
      applyResult(res);
    });

    document.querySelector('[data-testid="sim.export_btn"]').addEventListener("click", function () {
      if (!state.ledgerCsv) {
        setStatus("Run a simulation before exporting CSV.");
        return;
      }
      const blob = new Blob([state.ledgerCsv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "lifesim_ledger.csv";
      link.click();
      URL.revokeObjectURL(url);
      setStatus("Downloaded lifesim_ledger.csv");
    });

    initScenarios().catch(function (err) {
      setStatus("Failed to initialize scenarios: " + String(err));
    });
  });
})();
