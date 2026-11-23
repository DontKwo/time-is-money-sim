<p align="center">
  <img src="assets/logo.png" alt="Life Money Simulator Logo" width="240" />
</p>

# Life Money Simulator

**Model your accounts, 401(k) matches, debt payoff, taxes, and Monte Carlo retirement odds on your computer.**

Life Money Simulator runs day-by-day personal finance projections locally in an interactive desktop window with zero accounts, zero subscriptions, and complete offline privacy. Test retirement strategies, waterfall transfers, and life milestones visually before making real-world plans.

---

## Download

| Platform | Download | How to Install |
| :--- | :--- | :--- |
| **Windows** | [TimeIsMoneySim-Windows.exe](https://github.com/DontKwo/time-is-money-sim/releases/latest/download/TimeIsMoneySim-Windows.exe) | [Windows Install Steps](docs/INSTALLATION.md#windows) |
| **macOS** | [TimeIsMoneySim-macOS.zip](https://github.com/DontKwo/time-is-money-sim/releases/latest/download/TimeIsMoneySim-macOS.zip) | [macOS Install Steps](docs/INSTALLATION.md#macos) |
| **Linux** | [TimeIsMoneySim-Linux.tar.gz](https://github.com/DontKwo/time-is-money-sim/releases/latest/download/TimeIsMoneySim-Linux.tar.gz) | [Linux Install Steps](docs/INSTALLATION.md#linux) |

Browse release notes on [All Releases](https://github.com/DontKwo/time-is-money-sim/releases/latest).

---

## Screenshots

<p align="center">
  <img src="assets/screenshots/01_main.png" alt="Life Money Simulator Scenario Studio" width="760" />
</p>

<p align="center">
  <img src="assets/screenshots/02_analytics.png" alt="Life Money Simulator Monte Carlo Fan Chart" width="760" />
</p>

---

## How to Use

1. **Download the app** from the table above for Windows, macOS, or Linux.
2. **Open the desktop window** following [Desktop Installation Guide](docs/INSTALLATION.md) if prompted by your operating system.
3. **Choose a scenario template** (MVP, 401k Match, Debt Payoff, or FIRE Lifecycle) and set your projection horizon in days.
4. **Click Run Simulation, Monte Carlo, or Sensitivity** to inspect balance curves, cashflows, fan charts, and downloadable transaction ledgers.

---

## Key Features

- **Daily Calendar Accuracy**: Processes paychecks, taxes, credit cycles, loans, and compound returns day by day.
- **Deterministic Reproducibility**: Isolated seed streams let you toggle individual cashflows cleanly without random noise shifts.
- **Monte Carlo & Sensitivity**: Visualize probability bands across market paths and identify high-leverage savings choices.
- **Offline CSV Exports**: Export transaction ledgers locally for spreadsheet analysis.
- **Open Source**: Transparent simulation code under the [MIT License](LICENSE).

---

## Safety & Disclaimers

- **Financial Disclaimer**: Life Money Simulator is an educational personal finance model. It does not provide financial, investment, tax, legal, or retirement advice. Verify outputs independently before making financial decisions.
- **Official `main` Releases Only**: Only download executables from [DontKwo/time-is-money-sim](https://github.com/DontKwo/time-is-money-sim/releases/latest) (`main` branch). Never download forked builds unless you have verified they contain no malware; only official `main` releases are maintained by the author, and I make no promises.
- **OS Security Warnings**: Windows SmartScreen and macOS Gatekeeper may flag unsigned open-source builds as unrecognized or unsafe. Bypassing prompts is strictly at your own discretion; see [Desktop Installation Guide](docs/INSTALLATION.md).
- **AS-IS Disclaimer**: Provided "AS IS" under the [MIT License](LICENSE) with zero warranty or liability. Use at your own risk.

---

## Documentation

### User Documentation
- [User Guide](docs/USER_GUIDE.md)
- [Desktop Installation Guide](docs/INSTALLATION.md)
- [Configuration Reference](docs/CONFIG_REFERENCE.md)
- [Frequently Asked Questions](docs/FAQ.md)

### Developer Documentation
- [Developer Guide](docs/DEVELOPMENT.md)
- [Developer uv Installation](docs/UV_INSTALLATION.md)

### AI, Mathematical Proof & Technical Documentation
- [AI Agent Rules](AGENTS.md)
- [System Architecture](docs/ARCHITECTURE.md)

### Legal & Security Policies
- [Security Policy](SECURITY.md)
- [Third-Party Notices](THIRD_PARTY_NOTICES.md)
- [MIT License](LICENSE)
