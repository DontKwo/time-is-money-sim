# Developer Guide

Set up, test, lint, and package Life Money Simulator across Windows, macOS, and Linux.

## Prerequisites

- **Python 3.12+** and [`uv`](UV_INSTALLATION.md)

---

### Windows

```powershell
uv sync
.\.venv\Scripts\python.exe -m pytest -q
uv run --no-project --python ".\.venv\Scripts\python.exe" python -m lifesim.gui --self-test
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --icon=assets/icon.ico --name TimeIsMoneySim-Windows --workpath build/pyi-work --distpath build/pyi-dist --add-data "lifesim/gui_static;lifesim/gui_static" --add-data "scenarios;scenarios" --add-data "defaults;defaults" --add-data "assets;assets" lifesim/gui.py
```

---

### macOS

```bash
uv sync
.venv/bin/python -m pytest -q
uv run --no-project --python ".venv/bin/python" python -m lifesim.gui --self-test
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile --windowed --icon=assets/icon.ico --name TimeIsMoneySim --workpath build/pyi-work --distpath build/pyi-dist --add-data "lifesim/gui_static:lifesim/gui_static" --add-data "scenarios:scenarios" --add-data "defaults:defaults" --add-data "assets:assets" lifesim/gui.py
```

---

### Linux

```bash
uv sync
.venv/bin/python -m pytest -q
uv run --no-project --python ".venv/bin/python" python -m lifesim.gui --self-test
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile --name TimeIsMoneySim-Linux --workpath build/pyi-work --distpath build/pyi-dist --add-data "lifesim/gui_static:lifesim/gui_static" --add-data "scenarios:scenarios" --add-data "defaults:defaults" --add-data "assets:assets" lifesim/gui.py
```

---

## Verification & Linting

Run unit tests, GUI self-test, strict linter, and markdown link validation before pushing:

```bash
.\.venv\Scripts\python.exe -m pytest -q
uv run --no-project python ../ai-dev-tools/scripts/claudemd_linter.py . --level strict --full
uv run --no-project python ../ai-dev-tools/scripts/link_checker.py .
```

---

## Related Documentation

- [Project Overview](../README.md)
- [System Architecture](ARCHITECTURE.md)
- [User Guide](USER_GUIDE.md)
- [Desktop Installation Guide](INSTALLATION.md)
- [Developer uv Installation](UV_INSTALLATION.md)
- [Configuration Reference](CONFIG_REFERENCE.md)
- [AI Agent Reference](../AGENTS.md)
- [Security Policy](../SECURITY.md)
