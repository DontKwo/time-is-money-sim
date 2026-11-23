(function () {
  "use strict";

  const state = {
    scenarios: [],
    charts: {},
    ledgerCsv: "",
    activeChartKey: "balances",
    studio: {
      start: "2026-01-01",
      days: 365,
      seed: 42,
      accounts: [
        { name: "checking", kind: "checking", balance: 4000, rate: 0.0 },
        { name: "hysa", kind: "hysa", balance: 15000, rate: 0.045 }
      ],
      paychecks: [
        { name: "Salary", annualSalary: 95000, frequency: "biweekly", matchPct: 0.04 }
      ],
      flows: [
        { name: "Rent", type: "expense", scheduleType: "monthly", amount: 1800, from: "checking", to: "" }
      ],
      events: [],
      policies: [],
      goals: [{ name: "Emergency Buffer", kind: "net_worth", target_amount: 25000 }],
      rawConfig: null
    }
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

  function switchWorkspace(targetTab) {
    const map = {
      dashboard: { btn: "workspace.dashboard_tab", panel: "panelDashboard" },
      studio: { btn: "workspace.studio_tab", panel: "panelStudio" },
      compare: { btn: "workspace.compare_tab", panel: "panelCompare" }
    };
    Object.keys(map).forEach(function (key) {
      const btn = document.querySelector('[data-testid="' + map[key].btn + '"]');
      const panel = document.getElementById(map[key].panel);
      const isSelected = key === targetTab;
      if (btn) btn.classList.toggle("active", isSelected);
      if (panel) panel.hidden = !isSelected;
    });
  }

  function showChart(chartKey) {
    state.activeChartKey = chartKey;
    const map = {
      balances: "charts.balances_tab",
      networth: "charts.networth_tab",
      cashflow: "charts.cashflow_tab",
      analytics: "charts.analytics_tab",
      comparison: "charts.comparison_tab"
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

  function makeCellInput(type, val, onChange, step) {
    const inp = document.createElement("input");
    inp.className = "studio-input";
    inp.type = type;
    inp.value = val !== undefined && val !== null ? String(val) : "";
    if (step) inp.step = step;
    inp.addEventListener("input", function () { onChange(inp.value); });
    return inp;
  }

  function makeCellSelect(options, selected, onChange) {
    const sel = document.createElement("select");
    sel.className = "studio-input";
    options.forEach(function (optVal) {
      const opt = document.createElement("option");
      opt.value = optVal;
      opt.textContent = optVal;
      sel.appendChild(opt);
    });
    sel.value = selected;
    sel.addEventListener("change", function () { onChange(sel.value); });
    return sel;
  }

  function makeRemoveBtn(onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-secondary";
    btn.textContent = "Remove";
    btn.addEventListener("click", onClick);
    return btn;
  }

  function renderStudioEditors() {
    document.getElementById("studio.start_input").value = state.studio.start;
    document.getElementById("studio.days_input").value = String(state.studio.days);
    document.getElementById("studio.seed_input").value = String(state.studio.seed);

    const accHost = document.getElementById("studioAccountsHost");
    accHost.textContent = "";
    const accTable = document.createElement("table");
    accTable.innerHTML = "<thead><tr><th>Account Name</th><th>Kind</th><th>Starting Balance / Principal ($)</th><th>Annual Rate / APR</th><th>Action</th></tr></thead><tbody></tbody>";
    const accBody = accTable.querySelector("tbody");
    const accKinds = ["checking", "hysa", "savings", "investment", "traditional_401k", "roth_ira", "credit_card", "loan", "mortgage"];
    state.studio.accounts.forEach(function (acc, idx) {
      const tr = document.createElement("tr");
      [
        makeCellInput("text", acc.name, function (v) { acc.name = v; }),
        makeCellSelect(accKinds, acc.kind, function (v) { acc.kind = v; }),
        makeCellInput("number", acc.balance, function (v) { acc.balance = Number(v || 0); }, "100"),
        makeCellInput("number", acc.rate, function (v) { acc.rate = Number(v || 0); }, "0.005"),
        makeRemoveBtn(function () { state.studio.accounts.splice(idx, 1); renderStudioEditors(); })
      ].forEach(function (el) { const td = document.createElement("td"); td.appendChild(el); tr.appendChild(td); });
      accBody.appendChild(tr);
    });
    accHost.appendChild(accTable);

    const payHost = document.getElementById("studioPaychecksHost");
    payHost.textContent = "";
    const payTable = document.createElement("table");
    payTable.innerHTML = "<thead><tr><th>Paycheck Name</th><th>Annual Salary ($)</th><th>Frequency</th><th>401(k) Contrib (%)</th><th>Action</th></tr></thead><tbody></tbody>";
    const payBody = payTable.querySelector("tbody");
    state.studio.paychecks.forEach(function (pay, idx) {
      const tr = document.createElement("tr");
      [
        makeCellInput("text", pay.name, function (v) { pay.name = v; }),
        makeCellInput("number", pay.annualSalary, function (v) { pay.annualSalary = Number(v || 0); }, "1000"),
        makeCellSelect(["biweekly", "semimonthly", "monthly", "weekly"], pay.frequency, function (v) { pay.frequency = v; }),
        makeCellInput("number", pay.matchPct, function (v) { pay.matchPct = Number(v || 0); }, "0.01"),
        makeRemoveBtn(function () { state.studio.paychecks.splice(idx, 1); renderStudioEditors(); })
      ].forEach(function (el) { const td = document.createElement("td"); td.appendChild(el); tr.appendChild(td); });
      payBody.appendChild(tr);
    });
    payHost.appendChild(payTable);

    const flowHost = document.getElementById("studioFlowsHost");
    flowHost.textContent = "";
    const flowTable = document.createElement("table");
    flowTable.innerHTML = "<thead><tr><th>Flow Name</th><th>Type</th><th>Cadence</th><th>Amount ($)</th><th>From Account</th><th>To Account</th><th>Action</th></tr></thead><tbody></tbody>";
    const flowBody = flowTable.querySelector("tbody");
    state.studio.flows.forEach(function (flow, idx) {
      const tr = document.createElement("tr");
      [
        makeCellInput("text", flow.name, function (v) { flow.name = v; }),
        makeCellSelect(["expense", "income", "transfer"], flow.type, function (v) { flow.type = v; }),
        makeCellSelect(["monthly", "biweekly", "weekly", "yearly"], flow.scheduleType, function (v) { flow.scheduleType = v; }),
        makeCellInput("number", flow.amount, function (v) { flow.amount = Number(v || 0); }, "50"),
        makeCellInput("text", flow.from, function (v) { flow.from = v; }),
        makeCellInput("text", flow.to, function (v) { flow.to = v; }),
        makeRemoveBtn(function () { state.studio.flows.splice(idx, 1); renderStudioEditors(); })
      ].forEach(function (el) { const td = document.createElement("td"); td.appendChild(el); tr.appendChild(td); });
      flowBody.appendChild(tr);
    });
    flowHost.appendChild(flowTable);

    const evHost = document.getElementById("studioEventsHost");
    evHost.textContent = "";
    const evTable = document.createElement("table");
    evTable.innerHTML = "<thead><tr><th>Event Name</th><th>Date</th><th>Disable Flows (comma list)</th><th>Enable Flows (comma list)</th><th>Action</th></tr></thead><tbody></tbody>";
    const evBody = evTable.querySelector("tbody");
    state.studio.events.forEach(function (ev, idx) {
      const tr = document.createElement("tr");
      [
        makeCellInput("text", ev.name, function (v) { ev.name = v; }),
        makeCellInput("date", ev.date, function (v) { ev.date = v; }),
        makeCellInput("text", ev.disableFlows, function (v) { ev.disableFlows = v; }),
        makeCellInput("text", ev.enableFlows, function (v) { ev.enableFlows = v; }),
        makeRemoveBtn(function () { state.studio.events.splice(idx, 1); renderStudioEditors(); })
      ].forEach(function (el) { const td = document.createElement("td"); td.appendChild(el); tr.appendChild(td); });
      evBody.appendChild(tr);
    });
    evHost.appendChild(evTable);

    const polHost = document.getElementById("studioPoliciesHost");
    polHost.textContent = "";
    const polTable = document.createElement("table");
    polTable.innerHTML = "<thead><tr><th>Policy Name</th><th>Kind</th><th>Priority</th><th>From Account</th><th>To / Targets</th><th>Action</th></tr></thead><tbody></tbody>";
    const polBody = polTable.querySelector("tbody");
    state.studio.policies.forEach(function (pol, idx) {
      const tr = document.createElement("tr");
      [
        makeCellInput("text", pol.name, function (v) { pol.name = v; }),
        makeCellSelect(["excess_sweep", "debt_payoff", "shortfall_cover"], pol.kind, function (v) { pol.kind = v; }),
        makeCellInput("number", pol.priority, function (v) { pol.priority = Number(v || 10); }, "1"),
        makeCellInput("text", pol.fromAccount, function (v) { pol.fromAccount = v; }),
        makeCellInput("text", pol.toAccount, function (v) { pol.toAccount = v; }),
        makeRemoveBtn(function () { state.studio.policies.splice(idx, 1); renderStudioEditors(); })
      ].forEach(function (el) { const td = document.createElement("td"); td.appendChild(el); tr.appendChild(td); });
      polBody.appendChild(tr);
    });
    polHost.appendChild(polTable);
  }

  function populateStudioFromConfig(cfg) {
    state.studio.rawConfig = cfg;
    state.studio.start = String(cfg.start || "2026-01-01");
    state.studio.days = Number(cfg.days || 365);
    state.studio.seed = Number(cfg.seed !== undefined ? cfg.seed : 42);

    const accounts = [];
    const rawAccs = cfg.accounts || {};
    Object.keys(rawAccs).forEach(function (accName) {
      const acc = rawAccs[accName] || {};
      const kind = String(acc.kind || "checking");
      const bal = acc.principal !== undefined && acc.principal !== null ? Number(acc.principal) : Number(acc.balance || 0);
      const rate = acc.expected_return !== undefined && acc.expected_return !== null
        ? Number(acc.expected_return)
        : Number(acc.apr || acc.annual_growth_rate || 0);
      accounts.push({ name: accName, kind: kind, balance: bal, rate: rate });
    });
    state.studio.accounts = accounts;

    state.studio.paychecks = (cfg.paychecks || []).map(function (p) {
      let freq = "biweekly";
      const sch = p.schedule || {};
      if (sch.monthly !== undefined) freq = "monthly";
      else if (sch.semimonthly !== undefined) freq = "semimonthly";
      else if (sch.weekly !== undefined) freq = "weekly";
      const contrib = p.retirement_401k ? Number(p.retirement_401k.traditional_pct || 0) : 0;
      return {
        name: String(p.name || "Paycheck"),
        annualSalary: Number(p.annual_salary || 80000),
        frequency: freq,
        matchPct: contrib
      };
    });

    state.studio.flows = (cfg.flows || []).map(function (fl) {
      const sch = fl.schedule || {};
      let scheduleType = "monthly";
      if (sch.biweekly !== undefined) scheduleType = "biweekly";
      else if (sch.weekly !== undefined) scheduleType = "weekly";
      else if (sch.yearly !== undefined) scheduleType = "yearly";
      const amt = fl.amount && fl.amount.fixed !== undefined ? Number(fl.amount.fixed) : 0;
      return {
        name: String(fl.name || "Flow"),
        type: String(fl.type || "expense"),
        scheduleType: scheduleType,
        amount: amt,
        from: String(fl.from || fl.from_account || ""),
        to: String(fl.to || fl.to_account || "")
      };
    });

    state.studio.events = (cfg.events || []).map(function (ev) {
      return {
        name: String(ev.name || "Event"),
        date: String(ev.date || state.studio.start),
        disableFlows: (ev.disable_flows || []).join(", "),
        enableFlows: (ev.enable_flows || []).join(", ")
      };
    });

    state.studio.policies = (cfg.policies || []).map(function (pol) {
      return {
        name: String(pol.name || "Policy"),
        kind: String(pol.kind || "excess_sweep"),
        priority: Number(pol.priority || 10),
        fromAccount: String(pol.from_account || ""),
        toAccount: String(pol.to_account || (pol.target_accounts || []).join(", "))
      };
    });

    state.studio.goals = Array.isArray(cfg.goals) ? cfg.goals : [];
    renderStudioEditors();
  }

  function buildStudioConfigDict() {
    const startVal = document.getElementById("studio.start_input").value || "2026-01-01";
    const daysVal = Number(document.getElementById("studio.days_input").value || 365);
    const seedVal = Number(document.getElementById("studio.seed_input").value || 42);
    const accountsObj = {};
    const debtKinds = { credit_card: true, loan: true, mortgage: true, student_loan: true, auto_loan: true };

    state.studio.accounts.forEach(function (acc) {
      const cleanName = (acc.name || "account").trim();
      if (!cleanName) return;
      if (debtKinds[acc.kind]) {
        accountsObj[cleanName] = { kind: acc.kind, principal: Number(acc.balance || 0), apr: Number(acc.rate || 0), term_months: 120 };
      } else if (acc.kind === "investment") {
        accountsObj[cleanName] = { kind: acc.kind, balance: Number(acc.balance || 0), expected_return: Number(acc.rate || 0) };
      } else {
        accountsObj[cleanName] = { kind: acc.kind, balance: Number(acc.balance || 0), annual_growth_rate: Number(acc.rate || 0) };
      }
    });

    const paychecksArr = state.studio.paychecks.map(function (p) {
      const sch = p.frequency === "monthly" ? { monthly: 1 }
        : (p.frequency === "semimonthly" ? { semimonthly: [1, 15] }
        : (p.frequency === "weekly" ? { weekly: "fri" } : { biweekly: "fri", anchor: startVal }));
      const entry = { name: p.name || "Salary", enabled: true, schedule: sch, annual_salary: Number(p.annualSalary || 0) };
      if (Number(p.matchPct || 0) > 0 && accountsObj.traditional_401k) {
        entry.retirement_401k = { enabled: true, traditional_pct: Number(p.matchPct), traditional_account: "traditional_401k" };
      }
      return entry;
    });

    const flowsArr = state.studio.flows.map(function (fl) {
      const sch = fl.scheduleType === "biweekly" ? { biweekly: "fri", anchor: startVal }
        : (fl.scheduleType === "weekly" ? { weekly: "fri" }
        : (fl.scheduleType === "yearly" ? { yearly: { month: 1, day: 15 } } : { monthly: 1 }));
      const obj = { name: fl.name || "Flow", type: fl.type, schedule: sch, amount: { fixed: Number(fl.amount || 0) }, enabled: true };
      if (fl.from && fl.from.trim()) obj.from = fl.from.trim();
      if (fl.to && fl.to.trim()) obj.to = fl.to.trim();
      return obj;
    });

    const eventsArr = state.studio.events.map(function (ev) {
      return {
        name: ev.name || "Event",
        enabled: true,
        date: ev.date || startVal,
        disable_flows: ev.disableFlows ? ev.disableFlows.split(",").map(function (s) { return s.trim(); }).filter(Boolean) : [],
        enable_flows: ev.enableFlows ? ev.enableFlows.split(",").map(function (s) { return s.trim(); }).filter(Boolean) : []
      };
    });

    const policiesArr = state.studio.policies.map(function (pol) {
      const item = { name: pol.name || "Policy", kind: pol.kind, enabled: true, priority: Number(pol.priority || 10) };
      if (pol.fromAccount && pol.fromAccount.trim()) item.from_account = pol.fromAccount.trim();
      if (pol.kind === "debt_payoff") {
        item.schedule = { monthly: 26 };
        item.target_accounts = pol.toAccount ? pol.toAccount.split(",").map(function (s) { return s.trim(); }).filter(Boolean) : [];
      } else if (pol.kind === "shortfall_cover") {
        item.to_account = pol.toAccount || "checking";
        item.from_accounts = pol.fromAccount ? pol.fromAccount.split(",").map(function (s) { return s.trim(); }).filter(Boolean) : [];
      } else {
        item.schedule = { monthly: 28 };
        if (pol.toAccount && pol.toAccount.trim()) item.to_account = pol.toAccount.trim();
      }
      return item;
    });

    return {
      start: startVal,
      days: daysVal,
      seed: seedVal,
      accounts: accountsObj,
      paychecks: paychecksArr,
      flows: flowsArr,
      events: eventsArr,
      policies: policiesArr,
      goals: state.studio.goals || []
    };
  }

  function renderCompareChecklist(scenarios) {
    const host = document.getElementById("compareScenariosHost");
    if (!host) return;
    host.textContent = "";
    scenarios.forEach(function (item, idx) {
      const label = document.createElement("label");
      label.className = "studio-check-label";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.className = "compare-scenario-check";
      box.value = item.name;
      box.checked = idx < 2;
      const span = document.createElement("span");
      span.textContent = item.label;
      label.appendChild(box);
      label.appendChild(span);
      host.appendChild(label);
    });
  }

  function renderComparisonTable(rows) {
    const host = document.getElementById("compareTableHost");
    if (!host) return;
    host.textContent = "";
    if (!rows || rows.length === 0) {
      host.innerHTML = "<p class='muted'>No comparison results returned.</p>";
      return;
    }
    const table = document.createElement("table");
    table.innerHTML = "<thead><tr><th>Scenario</th><th>Ending Net Worth</th><th>Delta vs Baseline</th><th>Lowest Checking</th><th>FI Target</th></tr></thead><tbody></tbody>";
    const tbody = table.querySelector("tbody");
    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      [
        row.scenario,
        formatUsd(row.endingNetWorth),
        formatUsd(row.deltaVsBaseline),
        formatUsd(row.lowestChecking),
        row.fiDate
      ].forEach(function (val) {
        const td = document.createElement("td");
        td.textContent = String(val);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    host.appendChild(table);
  }

  function currentPayload() {
    return {
      scenario: document.getElementById("scenario.select").value,
      days: Number(document.getElementById("scenario.days_input").value || 365)
    };
  }

  async function initScenarios() {
    const data = await apiGet("/api/scenarios");
    state.scenarios = data.scenarios || [];
    const select = document.getElementById("scenario.select");
    select.textContent = "";
    state.scenarios.forEach(function (item) {
      const opt = document.createElement("option");
      opt.value = item.name;
      opt.textContent = item.label;
      select.appendChild(opt);
    });
    renderCompareChecklist(state.scenarios);
    renderStudioEditors();
    if (state.scenarios.length > 0) {
      document.getElementById("scenario.days_input").value = String(state.scenarios[0].days || 365);
      const res = await apiPost("/api/simulate", currentPayload());
      applyResult(res);
      const detail = await apiGet("/api/scenario-detail?name=" + encodeURIComponent(state.scenarios[0].name));
      if (detail.ok && detail.config) populateStudioFromConfig(detail.config);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelector('[data-testid="workspace.dashboard_tab"]').addEventListener("click", function () { switchWorkspace("dashboard"); });
    document.querySelector('[data-testid="workspace.studio_tab"]').addEventListener("click", function () { switchWorkspace("studio"); });
    document.querySelector('[data-testid="workspace.compare_tab"]').addEventListener("click", function () { switchWorkspace("compare"); });

    document.querySelector('[data-testid="charts.balances_tab"]').addEventListener("click", function () { showChart("balances"); });
    document.querySelector('[data-testid="charts.networth_tab"]').addEventListener("click", function () { showChart("networth"); });
    document.querySelector('[data-testid="charts.cashflow_tab"]').addEventListener("click", function () { showChart("cashflow"); });
    document.querySelector('[data-testid="charts.analytics_tab"]').addEventListener("click", function () { showChart("analytics"); });
    document.querySelector('[data-testid="charts.comparison_tab"]').addEventListener("click", function () { showChart("comparison"); });

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
      applyResult(await apiPost("/api/simulate", currentPayload()));
    });

    document.querySelector('[data-testid="sim.montecarlo_btn"]').addEventListener("click", async function () {
      setStatus("Running 100 Monte Carlo trials...");
      applyResult(await apiPost("/api/montecarlo", currentPayload()));
    });

    document.querySelector('[data-testid="sim.sensitivity_btn"]').addEventListener("click", async function () {
      setStatus("Running parameter sensitivity sweep...");
      applyResult(await apiPost("/api/sensitivity", currentPayload()));
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

    document.querySelector('[data-testid="sim.export_png_btn"]').addEventListener("click", function () {
      const src = state.charts[state.activeChartKey];
      if (!src) {
        setStatus("No active chart available to export as PNG.");
        return;
      }
      const link = document.createElement("a");
      link.href = src;
      link.download = "lifesim_" + state.activeChartKey + ".png";
      link.click();
      setStatus("Downloaded lifesim_" + state.activeChartKey + ".png");
    });

    document.querySelector('[data-testid="studio.load_preset_btn"]').addEventListener("click", async function () {
      const name = document.getElementById("scenario.select").value || "example_mvp.yaml";
      const detail = await apiGet("/api/scenario-detail?name=" + encodeURIComponent(name));
      if (detail.ok && detail.config) {
        populateStudioFromConfig(detail.config);
        setStatus("Loaded " + name + " into Scenario Studio.");
      } else {
        setStatus(detail.error || "Unable to load selected preset.");
      }
    });

    document.querySelector('[data-testid="studio.import_yaml_btn"]').addEventListener("click", function () {
      document.getElementById("studio.yaml_file_input").click();
    });

    document.querySelector('[data-testid="studio.yaml_file_input"]').addEventListener("change", async function (ev) {
      const file = ev.target.files && ev.target.files[0];
      if (!file) return;
      const text = await file.text();
      const res = await apiPost("/api/scenario-validate", { yamlText: text });
      if (res.ok && res.config) {
        populateStudioFromConfig(res.config);
        setStatus("Imported " + file.name + " into Scenario Studio.");
      } else {
        setStatus(res.error || "Invalid YAML scenario file.");
      }
    });

    document.querySelector('[data-testid="studio.download_yaml_btn"]').addEventListener("click", async function () {
      const res = await apiPost("/api/scenario-validate", { config: buildStudioConfigDict() });
      if (!res.ok) {
        setStatus(res.error || "Scenario Studio validation error.");
        return;
      }
      const blob = new Blob([res.yamlText], { type: "text/yaml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "custom_scenario.yaml";
      link.click();
      URL.revokeObjectURL(url);
      setStatus("Downloaded custom_scenario.yaml");
    });

    document.querySelector('[data-testid="studio.run_custom_btn"]').addEventListener("click", async function () {
      setStatus("Validating and simulating Scenario Studio configuration...");
      const res = await apiPost("/api/simulate-custom", { config: buildStudioConfigDict(), label: "Custom Studio" });
      applyResult(res);
      if (res.ok) switchWorkspace("dashboard");
    });

    document.querySelector('[data-testid="studio.add_account_btn"]').addEventListener("click", function () {
      state.studio.accounts.push({ name: "savings_" + (state.studio.accounts.length + 1), kind: "hysa", balance: 5000, rate: 0.04 });
      renderStudioEditors();
    });
    document.querySelector('[data-testid="studio.add_paycheck_btn"]').addEventListener("click", function () {
      state.studio.paychecks.push({ name: "Income_" + (state.studio.paychecks.length + 1), annualSalary: 75000, frequency: "biweekly", matchPct: 0.05 });
      renderStudioEditors();
    });
    document.querySelector('[data-testid="studio.add_flow_btn"]').addEventListener("click", function () {
      const defAcc = state.studio.accounts[0] ? state.studio.accounts[0].name : "checking";
      state.studio.flows.push({ name: "Flow_" + (state.studio.flows.length + 1), type: "expense", scheduleType: "monthly", amount: 300, from: defAcc, to: "" });
      renderStudioEditors();
    });
    document.querySelector('[data-testid="studio.add_event_btn"]').addEventListener("click", function () {
      state.studio.events.push({ name: "Event_" + (state.studio.events.length + 1), date: state.studio.start, disableFlows: "", enableFlows: "" });
      renderStudioEditors();
    });
    document.querySelector('[data-testid="studio.add_policy_btn"]').addEventListener("click", function () {
      const defAcc = state.studio.accounts[0] ? state.studio.accounts[0].name : "checking";
      state.studio.policies.push({ name: "Policy_" + (state.studio.policies.length + 1), kind: "excess_sweep", priority: 10, fromAccount: defAcc, toAccount: defAcc });
      renderStudioEditors();
    });

    document.querySelector('[data-testid="compare.run_btn"]').addEventListener("click", async function () {
      const selected = [];
      document.querySelectorAll(".compare-scenario-check:checked").forEach(function (el) { selected.push(el.value); });
      const includeStudio = document.getElementById("compare.include_studio_toggle").checked;
      const body = { scenarios: selected, days: Number(document.getElementById("scenario.days_input").value || 365) };
      if (includeStudio) {
        body.customConfig = buildStudioConfigDict();
        body.customLabel = "Scenario Studio";
      }
      setStatus("Comparing selected scenarios...");
      const res = await apiPost("/api/compare", body);
      if (!res.ok) {
        setStatus(res.error || "Comparison failed.");
        return;
      }
      const compImg = document.getElementById("compareChartImage");
      const compEmpty = document.getElementById("compareEmptyState");
      if (res.charts && res.charts.comparison) {
        state.charts.comparison = res.charts.comparison;
        compImg.src = res.charts.comparison;
        compImg.hidden = false;
        compEmpty.hidden = true;
      }
      renderComparisonTable(res.table || []);
      setStatus(res.message || "Comparison complete.");
    });

    initScenarios().catch(function (err) {
      setStatus("Failed to initialize scenarios: " + String(err));
    });
  });
})();
