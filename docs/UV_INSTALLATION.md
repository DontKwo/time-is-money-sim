# Developer `uv` Installation Guide

> **For Everyday Users**: You do **not** need `uv`, Python, or any command-line tool to use Life Money Simulator. Download the standalone desktop app directly from the [Download Table](../README.md#download).

Developers running simulation tests, building executables with PyInstaller, or running the strict repository linter use [Astral `uv`](https://docs.astral.sh/uv/) for deterministic Python environment management.

---

## Windows

Choose either the official standalone installer or a Windows package manager:

### Official Standalone Installer (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Package Managers (`winget` or `scoop`)

```powershell
winget install --id=astral-sh.uv -e
# or
scoop install main/uv
```

---

## macOS

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# or
brew install uv
```

---

## Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# or
pipx install uv
```

---

## Verification & Updating (All Platforms)

Open a new terminal window so `PATH` reloads, then verify:

```bash
uv --version
```

Always execute repository Python commands using `--no-project` with the project `.venv` as documented in [Developer Guide](DEVELOPMENT.md).

---

## Related Documentation

- [Project Overview](../README.md)
- [Developer Guide](DEVELOPMENT.md)
- [Desktop Installation Guide](INSTALLATION.md)
- [Security Policy](../SECURITY.md)
